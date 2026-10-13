package transport

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
)

// APIError is the decoded common error envelope. Planes convert it into their
// own distinct public error types, which own the default error text.
type APIError struct {
	StatusCode int
	Code       string
	Message    string
	RequestID  string
	Details    map[string]any
	RetryAfter time.Duration
	// Method and Route identify the request; Body is the bounded raw response,
	// which is untrusted server content for planes that expose it explicitly.
	Method string
	Route  string
	Body   []byte
}

// Error returns text without server-provided content. Plane error types
// replace it with their own formatter.
func (e *APIError) Error() string {
	if e == nil {
		return ""
	}
	return fmt.Sprintf("postgrip: HTTP %d %s", e.StatusCode, http.StatusText(e.StatusCode))
}

// errorEnvelope mirrors the common contract ErrorResponse schema. Transport
// imports no plane, so it cannot use a plane's generated type.
type errorEnvelope struct {
	Code      string         `json:"code"`
	Message   string         `json:"message"`
	RequestID string         `json:"requestId"`
	Details   map[string]any `json:"details,omitempty"`
}

// decodeAPIError decodes the envelope, falling back to HTTP_ERROR, the status
// text and the X-Request-ID header. The boolean reports whether Retry-After
// carried a usable value.
func decodeAPIError(response *http.Response, body []byte, retryAfterMax time.Duration) (*APIError, bool) {
	payload := errorEnvelope{}
	if err := json.Unmarshal(body, &payload); err != nil {
		payload = errorEnvelope{}
	}
	code := strings.TrimSpace(payload.Code)
	if code == "" {
		code = "HTTP_ERROR"
	}
	message := strings.TrimSpace(payload.Message)
	if message == "" {
		message = http.StatusText(response.StatusCode)
	}
	requestID := strings.TrimSpace(payload.RequestID)
	if requestID == "" {
		requestID = strings.TrimSpace(response.Header.Get("X-Request-ID"))
	}
	retryAfter, retryAfterSet := ParseRetryAfter(response.Header.Get("Retry-After"), retryAfterMax)
	return &APIError{StatusCode: response.StatusCode, Code: code, Message: message,
		RequestID: requestID, Details: payload.Details, RetryAfter: retryAfter}, retryAfterSet
}

// Error is an executor-local failure that is not an HTTP status, such as an
// encoding, response-bound or decoding failure. Its text keeps the plane prefix
// planes already expose, and planes may map Op and Err to their own types.
type Error struct {
	Plane string
	Op    string
	Err   error
}

func (e *Error) Error() string {
	if e.Err == nil {
		return fmt.Sprintf("postgrip-%s: %s", e.Plane, e.Op)
	}
	return fmt.Sprintf("postgrip-%s: %s: %v", e.Plane, e.Op, e.Err)
}

func (e *Error) Unwrap() error { return e.Err }
