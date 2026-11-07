package transport

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"slices"
	"strings"
	"time"
)

// DefaultMaxResponseBytes bounds a response body when a plane names no bound.
const DefaultMaxResponseBytes = 4 << 20

// Credentials supplies bearer credentials by auth lane. The executor calls it
// immediately before every network attempt, including retries.
type Credentials struct {
	// ManagementToken is the management bearer for management lanes and the
	// management side of the either lane.
	ManagementToken string
	// HasDelegated reports whether delegated runtime credentials are configured.
	// The either lane prefers the delegated session when it returns true.
	HasDelegated func() bool
	// Delegated returns the current delegated access token, refreshing it when
	// needed. The agent lane requires it.
	Delegated func(context.Context) (string, error)
}

// Executor executes generated JSON operations under the contract's auth-lane,
// idempotency, signing, retry, response-bound and error-envelope rules. Plane
// differences are configuration fields, never copies of this loop.
type Executor struct {
	// Plane names the error prefix, as in "postgrip-worker: ...".
	Plane string
	// BaseURL is the validated plane base URL, including any reverse-proxy path.
	BaseURL *url.URL
	// HTTPClient is used as given. Build it with HTTPClient so it carries the
	// default 30-second lifetime, keeps positive caller timeouts and applies
	// the plane's redirect policy. The executor adds no shorter bound.
	HTTPClient  *http.Client
	Credentials Credentials
	// OverrideCallerAuthorization replaces a caller-supplied Authorization
	// header with the management bearer on management lanes. Without it an
	// explicit caller header keeps precedence there.
	OverrideCallerAuthorization bool
	// CallerHeadersReplace makes a caller header replace the executor's own
	// value for that name (such as Content-Type) instead of adding to it.
	CallerHeadersReplace bool
	Retry                RetryConfig
	// MaxResponseBytes bounds every response body; zero uses the default.
	MaxResponseBytes int64
	// SuccessResponseBytes overrides MaxResponseBytes for 2xx responses of the
	// named operation IDs. It never applies to an error body.
	SuccessResponseBytes map[string]int64
	// DefaultHeaders apply only when the caller has not set the same header.
	DefaultHeaders http.Header
	// Sign signs the final request of an operation that declares signing,
	// after the body bytes are encoded. The executor never holds the key.
	Sign func(request *http.Request, body []byte) error
	// PlaneError converts the decoded envelope into the plane's typed error, whose
	// formatter owns the default text. Nil returns the *APIError itself.
	PlaneError func(*APIError) error
}

// Call is one invocation of a resolved operation.
type Call struct {
	// Operation has its path parameters substituted and query appended.
	Operation Operation
	// Header holds caller headers, including Idempotency-Key.
	Header http.Header
	// Body is JSON-encoded once, as given; nil sends no body.
	Body any
	// AcceptedStatuses are non-2xx statuses the plane adapter handles itself.
	// Their bounded raw body is returned without envelope decoding.
	AcceptedStatuses []int
	// Lifetime raises the exchange's client timeout for this call, for example
	// a long poll whose server hold counts against it. It never lowers a
	// configured timeout, and an unbounded client stays unbounded.
	Lifetime time.Duration
	// NoRetryStatuses are otherwise retryable statuses this call never retries,
	// such as an answer the server does not keep against the idempotency key,
	// after which a resend repeats the operation's side effect.
	NoRetryStatuses []int
}

// Response is the bounded raw response of a successful or accepted exchange.
type Response struct {
	StatusCode int
	Header     http.Header
	Body       []byte
}

// ValidateIdempotencyKey enforces the contract's 1 to 128 visible ASCII
// character key.
func ValidateIdempotencyKey(plane, key string) error {
	if len(key) == 0 || len(key) > 128 {
		return fmt.Errorf("postgrip-%s: idempotency key must contain 1 to 128 visible ASCII characters", plane)
	}
	for _, value := range key {
		if value < 0x21 || value > 0x7e {
			return fmt.Errorf("postgrip-%s: idempotency key must contain visible ASCII only", plane)
		}
	}
	return nil
}

// Do executes call. For a 2xx response with a non-empty body it decodes JSON
// into out when out is non-nil.
func (e *Executor) Do(ctx context.Context, call Call, out any) (*Response, error) {
	operation := call.Operation
	if operation.StreamingRequest || operation.WebSocket {
		return nil, fmt.Errorf("postgrip-%s: operation %q requires its protocol adapter", e.Plane, operation.ID)
	}
	idempotencyKey := call.Header.Get("Idempotency-Key")
	if operation.Idempotency == "required" {
		if err := ValidateIdempotencyKey(e.Plane, idempotencyKey); err != nil {
			return nil, err
		}
	}
	if operation.Signing != "" && e.Sign == nil {
		return nil, fmt.Errorf("postgrip-%s: operation %q requires request signing", e.Plane, operation.ID)
	}
	var body []byte
	if call.Body != nil {
		encoded, err := json.Marshal(call.Body)
		if err != nil {
			return nil, &Error{Plane: e.Plane, Op: "encode request", Err: err}
		}
		body = encoded
	}
	delegated, err := e.delegatedLane(operation.AuthLane)
	if err != nil {
		return nil, err
	}
	maxAttempts := e.Retry.attempts(operation, idempotencyKey)
	for attempt := 1; attempt <= maxAttempts; attempt++ {
		response, requestErr := e.send(ctx, operation, call.Header, body, delegated, call.Lifetime)
		var credential *credentialError
		if errors.As(requestErr, &credential) {
			// The request was never sent, so retrying would only repeat the
			// credential work (such as a session refresh) that just failed.
			return nil, credential.err
		}
		if requestErr != nil {
			if attempt < maxAttempts && ctx.Err() == nil {
				if err := waitRetry(ctx, e.Retry.delay(attempt, 0, 0, false)); err != nil {
					return nil, err
				}
				continue
			}
			return nil, requestErr
		}
		success := response.StatusCode >= 200 && response.StatusCode < 300
		limit := e.MaxResponseBytes
		if limit <= 0 {
			limit = DefaultMaxResponseBytes
		}
		if override, ok := e.SuccessResponseBytes[operation.ID]; ok && success {
			limit = override
		}
		responseBody, readErr := io.ReadAll(io.LimitReader(response.Body, limit+1))
		_ = response.Body.Close()
		if readErr != nil || int64(len(responseBody)) > limit {
			// Keep a read failure, such as cancellation or a truncated body, as
			// the cause so callers can still inspect it with errors.Is.
			return nil, &Error{Plane: e.Plane, Op: "response is invalid or too large", Err: readErr}
		}
		result := &Response{StatusCode: response.StatusCode, Header: response.Header, Body: responseBody}
		if slices.Contains(call.AcceptedStatuses, response.StatusCode) {
			return result, nil
		}
		if success {
			if out == nil || len(bytes.TrimSpace(responseBody)) == 0 {
				return result, nil
			}
			if err := json.Unmarshal(responseBody, out); err != nil {
				return nil, &Error{Plane: e.Plane, Op: "decode response", Err: err}
			}
			return result, nil
		}
		apiErr, retryAfterSet := decodeAPIError(response, responseBody, e.Retry.RetryAfterMax)
		apiErr.Method, apiErr.Route, apiErr.Body = operation.Method, operation.Path, responseBody
		if attempt < maxAttempts && RetryableStatus(response.StatusCode) &&
			!slices.Contains(call.NoRetryStatuses, response.StatusCode) {
			if err := waitRetry(ctx, e.Retry.delay(attempt, response.StatusCode, apiErr.RetryAfter, retryAfterSet)); err != nil {
				return nil, err
			}
			continue
		}
		if e.PlaneError != nil {
			return nil, e.PlaneError(apiErr)
		}
		return nil, apiErr
	}
	return nil, fmt.Errorf("postgrip-%s: request attempts exhausted", e.Plane)
}

// delegatedLane fixes the credential class for every attempt of one call.
func (e *Executor) delegatedLane(lane string) (bool, error) {
	switch lane {
	case LanePublic, LaneManagement, LaneWorkerManagement, LaneServiceManagement:
		return false, nil
	case LaneAgent:
		if e.Credentials.Delegated == nil {
			return false, fmt.Errorf("postgrip-%s: operation requires delegated runtime credentials", e.Plane)
		}
		return true, nil
	case LaneEither:
		return e.Credentials.Delegated != nil && e.Credentials.HasDelegated != nil && e.Credentials.HasDelegated(), nil
	default:
		return false, fmt.Errorf("postgrip-%s: unsupported auth lane %q", e.Plane, lane)
	}
}

func (e *Executor) send(ctx context.Context, operation Operation, header http.Header, body []byte, delegated bool, lifetime time.Duration) (*http.Response, error) {
	endpoint, err := url.Parse(strings.TrimRight(e.BaseURL.String(), "/") + operation.Path)
	if err != nil {
		return nil, fmt.Errorf("postgrip-%s: resolve operation URL: %w", e.Plane, err)
	}
	request, err := http.NewRequestWithContext(ctx, operation.Method, endpoint.String(), bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	request.Header.Set("Accept", "application/json")
	if len(body) > 0 {
		request.Header.Set("Content-Type", "application/json")
	}
	for name, values := range header {
		if e.CallerHeadersReplace {
			request.Header.Del(name)
		}
		for _, value := range values {
			request.Header.Add(name, value)
		}
	}
	for name, values := range e.DefaultHeaders {
		if _, set := request.Header[http.CanonicalHeaderKey(name)]; set {
			continue
		}
		for _, value := range values {
			request.Header.Add(name, value)
		}
	}
	if !operation.DeclaresHeader("If-Match") {
		// Header.Add canonicalizes names, so this removes every spelling.
		request.Header.Del("If-Match")
	}
	if err := e.authorize(ctx, request, operation.AuthLane, delegated); err != nil {
		return nil, &credentialError{err: err}
	}
	if operation.Signing != "" {
		if err := e.Sign(request, body); err != nil {
			return nil, err
		}
	}
	client := e.HTTPClient
	if lifetime > 0 && client.Timeout > 0 && lifetime > client.Timeout {
		extended := *client
		extended.Timeout = lifetime
		client = &extended
	}
	return client.Do(request)
}

func (e *Executor) authorize(ctx context.Context, request *http.Request, lane string, delegated bool) error {
	if lane == LanePublic {
		// Header.Add canonicalizes names, so this removes every spelling.
		request.Header.Del("Authorization")
		return nil
	}
	token := e.Credentials.ManagementToken
	if delegated {
		var err error
		if token, err = e.Credentials.Delegated(ctx); err != nil {
			return err
		}
		if token == "" {
			return errors.New("postgrip-" + e.Plane + ": delegated runtime credential is empty")
		}
	}
	if token == "" {
		return nil
	}
	// A caller-supplied header keeps its precedence on management lanes unless
	// the plane overrides it; the delegated session always replaces it.
	// Presence, not value, decides precedence: an explicitly empty caller
	// header still withholds the management bearer.
	if _, set := request.Header["Authorization"]; set && !delegated && !e.OverrideCallerAuthorization {
		return nil
	}
	request.Header.Set("Authorization", "Bearer "+token)
	return nil
}

// credentialError marks a failure of the credential hook before a request was
// sent, so the retry loop returns it instead of retrying.
type credentialError struct{ err error }

func (e *credentialError) Error() string { return e.err.Error() }
func (e *credentialError) Unwrap() error { return e.err }
