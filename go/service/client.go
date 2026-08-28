// Package service provides the public PostGrip Service management client.
package service

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
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/postgrip-io/postgrip-agent-sdks/go/internal/transport"
)

const (
	maxResponseBytes          = 4 << 20
	defaultRetryMaxAttempts   = 3
	maximumRetryMaxAttempts   = 3
	defaultRetryMaxDelay      = 2 * time.Second
	maximumRetryMaxDelay      = 2 * time.Second
	defaultRetryAfterMaxDelay = 30 * time.Second
	maximumRetryAfterMaxDelay = 30 * time.Second
)

type Config struct {
	BaseURL             string
	Token               string
	HTTPClient          *http.Client
	InsecureDevelopment bool
	EnableRetries       bool
	RetryMaxAttempts    int
	RetryMaxDelay       time.Duration
	RetryAfterMaxDelay  time.Duration
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
	retryPolicy    serviceRetryLimits
	followInterval time.Duration
}

type serviceRetryLimits struct {
	maxAttempts   int
	maxDelay      time.Duration
	retryAfterMax time.Duration
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
		return fmt.Sprintf("postgrip-service: HTTP %d: %s", e.StatusCode, e.Message)
	}
	return fmt.Sprintf("postgrip-service: %s (HTTP %d): %s", e.Code, e.StatusCode, e.Message)
}

func New(config Config) (*Client, error) {
	baseURL, err := transport.ParseBaseURL("service", config.BaseURL, config.InsecureDevelopment)
	if err != nil {
		return nil, err
	}
	token, err := transport.ManagementToken("service", config.Token)
	if err != nil {
		return nil, err
	}
	httpClient := transport.HTTPClient(config.HTTPClient)
	interval := config.FollowInterval
	if interval <= 0 {
		interval = 2 * time.Second
	}
	retries, err := configuredRetryPolicy(config)
	if err != nil {
		return nil, err
	}
	return &Client{connection: &Connection{
		baseURL: baseURL, token: token, httpClient: httpClient,
		retriesEnabled: config.EnableRetries, retryPolicy: retries, followInterval: interval,
	}}, nil
}

// NewFromEnv fills empty values from the unified PostGrip environment while
// preserving explicit plane configuration.
func NewFromEnv(config Config) (*Client, error) {
	if strings.TrimSpace(config.BaseURL) == "" {
		config.BaseURL = transport.FirstNonEmpty(os.Getenv("POSTGRIP_SERVICE_URL"), os.Getenv("POSTGRIP_URL"))
	}
	if strings.TrimSpace(config.Token) == "" {
		config.Token = os.Getenv("POSTGRIP_TOKEN")
	}
	return New(config)
}

func configuredRetryPolicy(config Config) (serviceRetryLimits, error) {
	policy := serviceRetryLimits{
		maxAttempts:   config.RetryMaxAttempts,
		maxDelay:      config.RetryMaxDelay,
		retryAfterMax: config.RetryAfterMaxDelay,
	}
	if policy.maxAttempts == 0 {
		policy.maxAttempts = defaultRetryMaxAttempts
	}
	if policy.maxDelay == 0 {
		policy.maxDelay = defaultRetryMaxDelay
	}
	if policy.retryAfterMax == 0 {
		policy.retryAfterMax = defaultRetryAfterMaxDelay
	}
	if policy.maxAttempts < 1 || policy.maxAttempts > maximumRetryMaxAttempts {
		return serviceRetryLimits{}, fmt.Errorf("postgrip-service: retry max attempts must be between 1 and %d", maximumRetryMaxAttempts)
	}
	if policy.maxDelay < 0 || policy.maxDelay > maximumRetryMaxDelay {
		return serviceRetryLimits{}, fmt.Errorf("postgrip-service: retry max delay must be between 0 and %s", maximumRetryMaxDelay)
	}
	if policy.retryAfterMax < 0 || policy.retryAfterMax > maximumRetryAfterMaxDelay {
		return serviceRetryLimits{}, fmt.Errorf("postgrip-service: Retry-After max delay must be between 0 and %s", maximumRetryAfterMaxDelay)
	}
	return policy, nil
}

func (c *Client) OpenAPI() *OpenAPIClient { return c.connection.OpenAPI() }

type openAPIHeadersContextKey struct{}

func withOpenAPIHeaders(ctx context.Context, headers http.Header) context.Context {
	return context.WithValue(ctx, openAPIHeadersContextKey{}, headers.Clone())
}

func validateIdempotencyKey(key string) error {
	if len(key) == 0 || len(key) > 128 {
		return errors.New("postgrip-service: idempotency key must contain 1 to 128 visible ASCII characters")
	}
	for _, value := range key {
		if value < 0x21 || value > 0x7e {
			return errors.New("postgrip-service: idempotency key must contain visible ASCII only")
		}
	}
	return nil
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
			return fmt.Errorf("postgrip-service: encode request: %w", err)
		}
	}
	headers := http.Header{}
	if configured, ok := ctx.Value(openAPIHeadersContextKey{}).(http.Header); ok {
		headers = configured.Clone()
	}
	idempotencyKey := headers.Get("Idempotency-Key")
	maxAttempts := 1
	retrySafe := operation.Retry == "bounded" && (operation.Safety == "read-only" || idempotencyKey != "")
	if c.retriesEnabled && retrySafe {
		maxAttempts = c.retryPolicy.maxAttempts
	}
	for attempt := 1; attempt <= maxAttempts; attempt++ {
		response, requestErr := c.send(ctx, operation, bodyBytes, headers)
		if requestErr != nil {
			if attempt < maxAttempts && ctx.Err() == nil {
				if err := waitRetry(ctx, retryDelay(attempt, 0, false, c.retryPolicy)); err != nil {
					return err
				}
				continue
			}
			return requestErr
		}
		responseBody, readErr := io.ReadAll(io.LimitReader(response.Body, maxResponseBytes+1))
		_ = response.Body.Close()
		if readErr != nil || len(responseBody) > maxResponseBytes {
			return errors.New("postgrip-service: response is invalid or too large")
		}
		if response.StatusCode >= 200 && response.StatusCode < 300 {
			if out == nil || len(bytes.TrimSpace(responseBody)) == 0 {
				return nil
			}
			if err := json.Unmarshal(responseBody, out); err != nil {
				return fmt.Errorf("postgrip-service: decode response: %w", err)
			}
			return nil
		}
		apiErr, retryAfterSet := decodeAPIError(response, responseBody, c.retryPolicy.retryAfterMax)
		if attempt < maxAttempts && retryableStatus(operation, idempotencyKey, response.StatusCode) {
			retryAfter, retryAfterSet := retryAfterForStatus(response.StatusCode, apiErr.RetryAfter, retryAfterSet)
			if err := waitRetry(ctx, retryDelay(attempt, retryAfter, retryAfterSet, c.retryPolicy)); err != nil {
				return err
			}
			continue
		}
		return apiErr
	}
	return errors.New("postgrip-service: request attempts exhausted")
}

func (c *Connection) send(ctx context.Context, operation openAPIOperation, body []byte, headers http.Header) (*http.Response, error) {
	endpoint, err := url.Parse(strings.TrimRight(c.baseURL.String(), "/") + operation.Path)
	if err != nil {
		return nil, fmt.Errorf("postgrip-service: resolve operation URL: %w", err)
	}
	request, err := http.NewRequestWithContext(ctx, operation.Method, endpoint.String(), bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	request.Header.Set("Accept", "application/json")
	if len(body) > 0 {
		request.Header.Set("Content-Type", "application/json")
	}
	for name, values := range headers {
		for _, value := range values {
			request.Header.Add(name, value)
		}
	}
	if operation.AuthLane == "service-management" {
		request.Header.Set("Authorization", "Bearer "+c.token)
	}
	return c.httpClient.Do(request)
}

func decodeAPIError(response *http.Response, body []byte, retryAfterMax time.Duration) (*APIError, bool) {
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
	retryAfter, retryAfterSet := parseRetryAfter(response.Header.Get("Retry-After"), retryAfterMax)
	return &APIError{StatusCode: response.StatusCode, Code: code, Message: message,
		RequestID: requestID, Details: payload.Details, RetryAfter: retryAfter}, retryAfterSet
}

func parseRetryAfter(value string, maximum time.Duration) (time.Duration, bool) {
	value = strings.TrimSpace(value)
	if value == "" {
		return 0, false
	}
	if seconds, err := strconv.ParseUint(value, 10, 64); err == nil {
		if maximum <= 0 || seconds > uint64(maximum/time.Second) {
			return maximum, true
		}
		return time.Duration(seconds) * time.Second, true
	} else if errors.Is(err, strconv.ErrRange) && strings.IndexFunc(value, func(value rune) bool {
		return value < '0' || value > '9'
	}) == -1 {
		return maximum, true
	}
	if when, err := http.ParseTime(value); err == nil {
		return min(max(time.Until(when), 0), maximum), true
	}
	return 0, false
}

func retryableStatus(operation openAPIOperation, key string, status int) bool {
	if operation.Retry != "bounded" || operation.Safety != "read-only" && key == "" {
		return false
	}
	return status == 408 || status == 429 || status == 502 || status == 503 || status == 504
}

func retryAfterForStatus(status int, retryAfter time.Duration, retryAfterSet bool) (time.Duration, bool) {
	if (status == http.StatusTooManyRequests || status == http.StatusServiceUnavailable) && retryAfterSet {
		return retryAfter, true
	}
	return 0, false
}

func retryDelay(attempt int, retryAfter time.Duration, retryAfterSet bool, policy serviceRetryLimits) time.Duration {
	if retryAfterSet {
		return min(max(retryAfter, 0), policy.retryAfterMax)
	}
	capDelay := min(200*time.Millisecond*time.Duration(1<<(attempt-1)), policy.maxDelay)
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

type Reference struct {
	Source ServiceSource
	ID     string
}

func ReferenceFor(service Service) Reference {
	return Reference{Source: service.Source, ID: service.Id}
}

func (r Reference) validate() error {
	if r.Source != OpenAPIServiceSourceTarget && r.Source != OpenAPIServiceSourceProject {
		return errors.New("postgrip-service: source must be target or project")
	}
	if strings.TrimSpace(r.ID) == "" {
		return errors.New("postgrip-service: service ID is required")
	}
	return nil
}

func (c *Client) List(ctx context.Context, query OpenAPIListServicesQuery) (ServiceList, error) {
	return c.OpenAPI().ListServices(ctx, query)
}

func (c *Client) Resolve(ctx context.Context, value string) (Service, error) {
	return c.OpenAPI().ResolveService(ctx, OpenAPIResolveServiceQuery{Value: value})
}

func (c *Client) Get(ctx context.Context, ref Reference) (Service, error) {
	if err := ref.validate(); err != nil {
		return Service{}, err
	}
	return c.OpenAPI().GetService(ctx, string(ref.Source), ref.ID)
}

func (c *Client) Status(ctx context.Context, ref Reference, query OpenAPIGetServiceStatusQuery) (ServiceStatus, error) {
	if err := ref.validate(); err != nil {
		return ServiceStatus{}, err
	}
	return c.OpenAPI().GetServiceStatus(ctx, string(ref.Source), ref.ID, query)
}

func (c *Client) Environments(ctx context.Context, ref Reference, query OpenAPIListServiceEnvironmentsQuery) (EnvironmentList, error) {
	if err := ref.validate(); err != nil {
		return EnvironmentList{}, err
	}
	return c.OpenAPI().ListServiceEnvironments(ctx, string(ref.Source), ref.ID, query)
}

func (c *Client) ResolveEnvironment(ctx context.Context, projectID, value string) (Environment, error) {
	return c.OpenAPI().ResolveServiceEnvironment(ctx, projectID, OpenAPIResolveServiceEnvironmentQuery{Value: value})
}

func (c *Client) Deployments(ctx context.Context, ref Reference, query OpenAPIListServiceDeploymentsQuery) (DeploymentList, error) {
	if err := ref.validate(); err != nil {
		return DeploymentList{}, err
	}
	return c.OpenAPI().ListServiceDeployments(ctx, string(ref.Source), ref.ID, query)
}

func (c *Client) Deployment(ctx context.Context, projectID, deploymentID string) (Deployment, error) {
	return c.OpenAPI().GetServiceDeployment(ctx, projectID, deploymentID)
}

func (c *Client) Logs(ctx context.Context, ref Reference, query OpenAPIListServiceLogsQuery) (LogList, error) {
	if err := ref.validate(); err != nil {
		return LogList{}, err
	}
	return c.OpenAPI().ListServiceLogs(ctx, string(ref.Source), ref.ID, query)
}

func (c *Client) Check(ctx context.Context, ref Reference, environmentID *string, idempotencyKey string) (ServiceOperationResponse, error) {
	if err := ref.validate(); err != nil {
		return ServiceOperationResponse{}, err
	}
	if err := validateIdempotencyKey(idempotencyKey); err != nil {
		return ServiceOperationResponse{}, err
	}
	body := &OpenAPICheckServiceRequestBody{EnvironmentId: environmentID}
	return c.OpenAPI().CheckService(ctx, string(ref.Source), ref.ID, OpenAPICheckServiceHeaders{IdempotencyKey: idempotencyKey}, body)
}

func (c *Client) PreviewDeploy(ctx context.Context, projectID string, query OpenAPIPreviewServiceDeployQuery) (DeployPreview, error) {
	return c.OpenAPI().PreviewServiceDeploy(ctx, projectID, query)
}

func (c *Client) Deploy(ctx context.Context, projectID string, body DeployServiceRequest, idempotencyKey string) (DeploymentOperationResponse, error) {
	if err := validateIdempotencyKey(idempotencyKey); err != nil {
		return DeploymentOperationResponse{}, err
	}
	return c.OpenAPI().DeployService(ctx, projectID, OpenAPIDeployServiceHeaders{IdempotencyKey: idempotencyKey}, body)
}

func (c *Client) Redeploy(ctx context.Context, projectID string, body RedeployServiceRequest, idempotencyKey string) (DeploymentOperationResponse, error) {
	if err := validateIdempotencyKey(idempotencyKey); err != nil {
		return DeploymentOperationResponse{}, err
	}
	return c.OpenAPI().RedeployService(ctx, projectID, OpenAPIRedeployServiceHeaders{IdempotencyKey: idempotencyKey}, body)
}

func (c *Client) Cancel(ctx context.Context, projectID, deploymentID, idempotencyKey string) (DeploymentOperationResponse, error) {
	if err := validateIdempotencyKey(idempotencyKey); err != nil {
		return DeploymentOperationResponse{}, err
	}
	return c.OpenAPI().CancelServiceDeployment(ctx, projectID, deploymentID, OpenAPICancelServiceDeploymentHeaders{IdempotencyKey: idempotencyKey})
}

func (c *Client) Rollback(ctx context.Context, projectID, deploymentID, idempotencyKey string) (DeploymentOperationResponse, error) {
	if err := validateIdempotencyKey(idempotencyKey); err != nil {
		return DeploymentOperationResponse{}, err
	}
	return c.OpenAPI().RollbackServiceDeployment(ctx, projectID, deploymentID, OpenAPIRollbackServiceDeploymentHeaders{IdempotencyKey: idempotencyKey})
}

func (c *Client) Start(ctx context.Context, projectID, environmentID, expectedDeploymentID, idempotencyKey string) (ServiceOperationResponse, error) {
	if err := validateIdempotencyKey(idempotencyKey); err != nil {
		return ServiceOperationResponse{}, err
	}
	return c.OpenAPI().StartServiceRuntime(ctx, projectID, environmentID, OpenAPIStartServiceRuntimeHeaders{IdempotencyKey: idempotencyKey}, RuntimeOperationRequest{ExpectedDeploymentId: expectedDeploymentID})
}

func (c *Client) Stop(ctx context.Context, projectID, environmentID, expectedDeploymentID, idempotencyKey string) (ServiceOperationResponse, error) {
	if err := validateIdempotencyKey(idempotencyKey); err != nil {
		return ServiceOperationResponse{}, err
	}
	return c.OpenAPI().StopServiceRuntime(ctx, projectID, environmentID, OpenAPIStopServiceRuntimeHeaders{IdempotencyKey: idempotencyKey}, RuntimeOperationRequest{ExpectedDeploymentId: expectedDeploymentID})
}

func (c *Client) Restart(ctx context.Context, projectID, environmentID, expectedDeploymentID, idempotencyKey string) (ServiceOperationResponse, error) {
	if err := validateIdempotencyKey(idempotencyKey); err != nil {
		return ServiceOperationResponse{}, err
	}
	return c.OpenAPI().RestartServiceRuntime(ctx, projectID, environmentID, OpenAPIRestartServiceRuntimeHeaders{IdempotencyKey: idempotencyKey}, RuntimeOperationRequest{ExpectedDeploymentId: expectedDeploymentID})
}

type ScopedClient struct {
	client *Client
	ref    Reference
}

func (c *Client) ForService(ref Reference) (*ScopedClient, error) {
	if err := ref.validate(); err != nil {
		return nil, err
	}
	return &ScopedClient{client: c, ref: ref}, nil
}

func (c *ScopedClient) Reference() Reference { return c.ref }
func (c *ScopedClient) Get(ctx context.Context) (Service, error) {
	return c.client.Get(ctx, c.ref)
}
func (c *ScopedClient) Status(ctx context.Context, query OpenAPIGetServiceStatusQuery) (ServiceStatus, error) {
	return c.client.Status(ctx, c.ref, query)
}
func (c *ScopedClient) Environments(ctx context.Context, query OpenAPIListServiceEnvironmentsQuery) (EnvironmentList, error) {
	return c.client.Environments(ctx, c.ref, query)
}
func (c *ScopedClient) Deployments(ctx context.Context, query OpenAPIListServiceDeploymentsQuery) (DeploymentList, error) {
	return c.client.Deployments(ctx, c.ref, query)
}
func (c *ScopedClient) Logs(ctx context.Context, query OpenAPIListServiceLogsQuery) (LogList, error) {
	return c.client.Logs(ctx, c.ref, query)
}
func (c *ScopedClient) Check(ctx context.Context, environmentID *string, idempotencyKey string) (ServiceOperationResponse, error) {
	return c.client.Check(ctx, c.ref, environmentID, idempotencyKey)
}
