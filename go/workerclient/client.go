// Package workerclient provides the public PostGrip Worker management client.
package workerclient

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math/rand"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

const maxResponseBytes = 4 << 20

type Config struct {
	BaseURL             string
	Token               string
	HTTPClient          *http.Client
	InsecureDevelopment bool
	EnableRetries       bool
	FollowInterval      time.Duration
}

type Client struct {
	connection *Connection
}

type Connection struct {
	baseURL        *url.URL
	token          string
	httpClient     *http.Client
	retriesEnabled bool
	followInterval time.Duration
}

type APIError struct {
	StatusCode int
	Code       string
	Message    string
	RequestID  string
	Details    map[string]any
	RetryAfter time.Duration
}

func (e *APIError) Error() string {
	if e == nil {
		return ""
	}
	if e.Code == "" {
		return fmt.Sprintf("postgrip-worker: HTTP %d: %s", e.StatusCode, e.Message)
	}
	return fmt.Sprintf("postgrip-worker: %s (HTTP %d): %s", e.Code, e.StatusCode, e.Message)
}

func New(config Config) (*Client, error) {
	baseURL, err := url.Parse(strings.TrimSpace(config.BaseURL))
	if err != nil || baseURL.Host == "" || (baseURL.Scheme != "https" && !(config.InsecureDevelopment && baseURL.Scheme == "http")) {
		return nil, errors.New("postgrip-worker: base URL must use HTTPS (or explicitly enable insecure development for HTTP)")
	}
	if baseURL.RawQuery != "" || baseURL.Fragment != "" {
		return nil, errors.New("postgrip-worker: base URL must not contain a query or fragment")
	}
	token := strings.TrimSpace(config.Token)
	if !strings.HasPrefix(token, "pgwm_") {
		return nil, errors.New("postgrip-worker: token must be a pgwm_ worker management token")
	}
	httpClient := config.HTTPClient
	if httpClient == nil {
		httpClient = http.DefaultClient
	}
	clientCopy := *httpClient
	priorRedirect := clientCopy.CheckRedirect
	clientCopy.CheckRedirect = func(req *http.Request, via []*http.Request) error {
		if len(via) == 0 {
			return nil
		}
		origin := via[0].URL
		if !strings.EqualFold(req.URL.Scheme, origin.Scheme) || !strings.EqualFold(req.URL.Host, origin.Host) {
			return http.ErrUseLastResponse
		}
		if priorRedirect != nil {
			return priorRedirect(req, via)
		}
		if len(via) >= 10 {
			return errors.New("stopped after 10 redirects")
		}
		return nil
	}
	interval := config.FollowInterval
	if interval <= 0 {
		interval = 2 * time.Second
	}
	return &Client{connection: &Connection{
		baseURL: baseURL, token: token, httpClient: &clientCopy,
		retriesEnabled: config.EnableRetries, followInterval: interval,
	}}, nil
}

func (c *Client) OpenAPI() *OpenAPIClient { return c.connection.OpenAPI() }

func (c *Client) Health(ctx context.Context) (HealthResponse, error) {
	return c.OpenAPI().WorkerOrchestratorHealth(ctx)
}

type idempotencyKeyContextKey struct{}
type openAPIHeadersContextKey struct{}

func withOpenAPIHeaders(ctx context.Context, headers http.Header) context.Context {
	return context.WithValue(ctx, openAPIHeadersContextKey{}, headers.Clone())
}

func withIdempotencyKey(ctx context.Context, key string) (context.Context, error) {
	if len(key) == 0 || len(key) > 128 {
		return nil, errors.New("postgrip-worker: idempotency key must contain 1 to 128 visible ASCII characters")
	}
	for _, value := range key {
		if value < 0x21 || value > 0x7e {
			return nil, errors.New("postgrip-worker: idempotency key must contain visible ASCII only")
		}
	}
	return context.WithValue(ctx, idempotencyKeyContextKey{}, key), nil
}

func (c *Connection) doOpenAPI(ctx context.Context, id openAPIOperationID, pathParameters map[string]string, query url.Values, body, out any) error {
	operation, err := resolveOpenAPIOperation(id, pathParameters, query)
	if err != nil {
		return err
	}
	var bodyBytes []byte
	if body != nil {
		bodyBytes, err = json.Marshal(body)
		if err != nil {
			return fmt.Errorf("postgrip-worker: encode request: %w", err)
		}
	}
	idempotencyKey, _ := ctx.Value(idempotencyKeyContextKey{}).(string)
	if headers, ok := ctx.Value(openAPIHeadersContextKey{}).(http.Header); ok {
		idempotencyKey = headers.Get("Idempotency-Key")
	}
	maxAttempts := 1
	if c.retriesEnabled && (operation.Method == http.MethodGet || idempotencyKey != "") {
		maxAttempts = 3
	}
	for attempt := 1; attempt <= maxAttempts; attempt++ {
		response, requestErr := c.send(ctx, operation, bodyBytes, idempotencyKey)
		if requestErr != nil {
			if attempt < maxAttempts && ctx.Err() == nil {
				if err := waitRetry(ctx, retryDelay(attempt, 0)); err != nil {
					return err
				}
				continue
			}
			return requestErr
		}
		responseBody, readErr := io.ReadAll(io.LimitReader(response.Body, maxResponseBytes+1))
		_ = response.Body.Close()
		if readErr != nil || len(responseBody) > maxResponseBytes {
			return errors.New("postgrip-worker: response is invalid or too large")
		}
		if response.StatusCode >= 200 && response.StatusCode < 300 {
			if out == nil || len(bytes.TrimSpace(responseBody)) == 0 {
				return nil
			}
			if err := json.Unmarshal(responseBody, out); err != nil {
				return fmt.Errorf("postgrip-worker: decode response: %w", err)
			}
			return nil
		}
		apiErr := decodeAPIError(response, responseBody)
		if attempt < maxAttempts && retryableStatus(operation.Method, idempotencyKey, response.StatusCode) {
			if err := waitRetry(ctx, retryDelay(attempt, retryAfterForStatus(response.StatusCode, apiErr.RetryAfter))); err != nil {
				return err
			}
			continue
		}
		return apiErr
	}
	return errors.New("postgrip-worker: request attempts exhausted")
}

func (c *Connection) send(ctx context.Context, operation openAPIOperation, body []byte, idempotencyKey string) (*http.Response, error) {
	endpoint, err := url.Parse(strings.TrimRight(c.baseURL.String(), "/") + operation.Path)
	if err != nil {
		return nil, fmt.Errorf("postgrip-worker: resolve operation URL: %w", err)
	}
	request, err := http.NewRequestWithContext(ctx, operation.Method, endpoint.String(), bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	request.Header.Set("Accept", "application/json")
	if len(body) > 0 {
		request.Header.Set("Content-Type", "application/json")
	}
	if operation.AuthLane == "worker-management" {
		request.Header.Set("Authorization", "Bearer "+c.token)
	}
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	return c.httpClient.Do(request)
}

func decodeAPIError(response *http.Response, body []byte) *APIError {
	payload := OpenAPIErrorResponse{}
	if err := json.Unmarshal(body, &payload); err != nil {
		payload = OpenAPIErrorResponse{}
	}
	code := strings.TrimSpace(payload.Code)
	if code == "" {
		code = "HTTP_ERROR"
	}
	message := strings.TrimSpace(payload.Message)
	if message == "" {
		message = http.StatusText(response.StatusCode)
	}
	requestID := strings.TrimSpace(payload.RequestId)
	if requestID == "" {
		requestID = strings.TrimSpace(response.Header.Get("X-Request-ID"))
	}
	return &APIError{StatusCode: response.StatusCode, Code: code, Message: message,
		RequestID: requestID, Details: payload.Details, RetryAfter: parseRetryAfter(response.Header.Get("Retry-After"))}
}

func parseRetryAfter(value string) time.Duration {
	value = strings.TrimSpace(value)
	if seconds, err := strconv.Atoi(value); err == nil && seconds >= 0 {
		return min(time.Duration(seconds)*time.Second, 30*time.Second)
	}
	if when, err := http.ParseTime(value); err == nil {
		return min(max(time.Until(when), 0), 30*time.Second)
	}
	return 0
}

func retryableStatus(method, key string, status int) bool {
	if method != http.MethodGet && key == "" {
		return false
	}
	return status == 408 || status == 429 || status == 502 || status == 503 || status == 504
}

func retryAfterForStatus(status int, retryAfter time.Duration) time.Duration {
	if status == http.StatusTooManyRequests || status == http.StatusServiceUnavailable {
		return retryAfter
	}
	return 0
}

func retryDelay(attempt int, retryAfter time.Duration) time.Duration {
	if retryAfter > 0 {
		return min(retryAfter, 30*time.Second)
	}
	capDelay := min(200*time.Millisecond*time.Duration(1<<(attempt-1)), 2*time.Second)
	return time.Duration(rand.Int63n(max(int64(capDelay), 1)))
}

func waitRetry(ctx context.Context, delay time.Duration) error {
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

type ListWorkersOptions struct {
	PageSize                      *int64
	PageToken, Status, TrustState *string
}

func (c *Client) List(ctx context.Context, options ListWorkersOptions) (WorkerList, error) {
	query := OpenAPIListWorkersQuery{PageSize: options.PageSize, PageToken: options.PageToken, Status: options.Status, TrustState: options.TrustState}
	return c.OpenAPI().ListWorkers(ctx, query)
}

func (c *Client) Get(ctx context.Context, workerID string) (Worker, error) {
	return c.OpenAPI().GetWorker(ctx, workerID)
}

func (c *Client) Assignments(ctx context.Context, workerID string) (AssignmentList, error) {
	return c.OpenAPI().ListWorkerAssignments(ctx, workerID)
}

func (c *Client) Jobs(ctx context.Context, workerID string, query OpenAPIListWorkerJobsQuery) (JobList, error) {
	return c.OpenAPI().ListWorkerJobs(ctx, workerID, query)
}

func (c *Client) Job(ctx context.Context, workerID, jobID string) (Job, error) {
	return c.OpenAPI().GetWorkerJob(ctx, workerID, jobID)
}

func (c *Client) OperationalLogs(ctx context.Context, workerID string, query OpenAPIListWorkerOperationalLogsQuery) (OperationalLogList, error) {
	return c.OpenAPI().ListWorkerOperationalLogs(ctx, workerID, query)
}

func (c *Client) SecurityLogs(ctx context.Context, workerID string, query OpenAPIListWorkerSecurityLogsQuery) (SecurityLogList, error) {
	return c.OpenAPI().ListWorkerSecurityLogs(ctx, workerID, query)
}

func (c *Client) Check(ctx context.Context, workerID, idempotencyKey string) (CheckWorkerResponse, error) {
	ctx, err := withIdempotencyKey(ctx, idempotencyKey)
	if err != nil {
		return CheckWorkerResponse{}, err
	}
	return c.OpenAPI().CheckWorker(ctx, workerID, OpenAPICheckWorkerHeaders{IdempotencyKey: idempotencyKey})
}

func (c *Client) Maintenance(ctx context.Context, workerID, idempotencyKey string) (WorkerOperationResponse, error) {
	ctx, err := withIdempotencyKey(ctx, idempotencyKey)
	if err != nil {
		return WorkerOperationResponse{}, err
	}
	return c.OpenAPI().PlaceWorkerInMaintenance(ctx, workerID, OpenAPIPlaceWorkerInMaintenanceHeaders{IdempotencyKey: idempotencyKey})
}

func (c *Client) Resume(ctx context.Context, workerID, idempotencyKey string) (WorkerOperationResponse, error) {
	ctx, err := withIdempotencyKey(ctx, idempotencyKey)
	if err != nil {
		return WorkerOperationResponse{}, err
	}
	return c.OpenAPI().ResumeWorkerFromMaintenance(ctx, workerID, OpenAPIResumeWorkerFromMaintenanceHeaders{IdempotencyKey: idempotencyKey})
}

func (c *Client) Upgrade(ctx context.Context, workerID, idempotencyKey string) (UpgradeWorkerResponse, error) {
	ctx, err := withIdempotencyKey(ctx, idempotencyKey)
	if err != nil {
		return UpgradeWorkerResponse{}, err
	}
	return c.OpenAPI().UpgradeWorker(ctx, workerID, OpenAPIUpgradeWorkerHeaders{IdempotencyKey: idempotencyKey})
}
