// Package service provides the public PostGrip Service management client.
package service

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	"github.com/postgrip-io/postgrip-agent-sdks/go/internal/transport"
)

// Service execution policy: a 4 MiB response bound with a 24 MiB bound for
// successful getServiceDeploymentScreenshot responses, and configurable retry
// ceilings that default to and never exceed three attempts, 2-second backoff
// and a 30-second Retry-After cap.
const (
	maxResponseBytes           = 4 << 20
	maxScreenshotResponseBytes = 24 << 20
	defaultRetryMaxAttempts    = 3
	maximumRetryMaxAttempts    = 3
	defaultRetryMaxDelay       = 2 * time.Second
	maximumRetryMaxDelay       = 2 * time.Second
	defaultRetryAfterMaxDelay  = 30 * time.Second
	maximumRetryAfterMaxDelay  = 30 * time.Second
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
	followInterval time.Duration
	executor       *transport.Executor
}

// APIError is a Service management failure decoded from the common error
// envelope. It is distinct from other planes' error types.
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

// newAPIError converts the shared decoded envelope into the Service error type.
func newAPIError(err *transport.APIError) error {
	return &APIError{StatusCode: err.StatusCode, Code: err.Code, Message: err.Message,
		RequestID: err.RequestID, Details: err.Details, RetryAfter: err.RetryAfter}
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
	interval := config.FollowInterval
	if interval <= 0 {
		interval = 2 * time.Second
	}
	retries, err := configuredRetryPolicy(config)
	if err != nil {
		return nil, err
	}
	// The Service management bearer replaces any caller-supplied Authorization.
	executor := &transport.Executor{
		Plane: "service", BaseURL: baseURL, HTTPClient: transport.HTTPClient(config.HTTPClient),
		Credentials:                 transport.Credentials{ManagementToken: token},
		OverrideCallerAuthorization: true,
		Retry:                       retries,
		MaxResponseBytes:            maxResponseBytes,
		SuccessResponseBytes: map[string]int64{
			string(openAPIGetServiceDeploymentScreenshot): maxScreenshotResponseBytes,
		},
		PlaneError: newAPIError,
	}
	return &Client{connection: &Connection{
		baseURL: baseURL, token: token, followInterval: interval, executor: executor,
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

// configuredRetryPolicy applies the Service defaults to zero values and
// rejects ceilings above the Service maximums.
func configuredRetryPolicy(config Config) (transport.RetryConfig, error) {
	policy := transport.RetryConfig{
		Enabled:       config.EnableRetries,
		MaxAttempts:   config.RetryMaxAttempts,
		MaxDelay:      config.RetryMaxDelay,
		RetryAfterMax: config.RetryAfterMaxDelay,
	}
	if policy.MaxAttempts == 0 {
		policy.MaxAttempts = defaultRetryMaxAttempts
	}
	if policy.MaxDelay == 0 {
		policy.MaxDelay = defaultRetryMaxDelay
	}
	if policy.RetryAfterMax == 0 {
		policy.RetryAfterMax = defaultRetryAfterMaxDelay
	}
	if policy.MaxAttempts < 1 || policy.MaxAttempts > maximumRetryMaxAttempts {
		return transport.RetryConfig{}, fmt.Errorf("postgrip-service: retry max attempts must be between 1 and %d", maximumRetryMaxAttempts)
	}
	if policy.MaxDelay < 0 || policy.MaxDelay > maximumRetryMaxDelay {
		return transport.RetryConfig{}, fmt.Errorf("postgrip-service: retry max delay must be between 0 and %s", maximumRetryMaxDelay)
	}
	if policy.RetryAfterMax < 0 || policy.RetryAfterMax > maximumRetryAfterMaxDelay {
		return transport.RetryConfig{}, fmt.Errorf("postgrip-service: Retry-After max delay must be between 0 and %s", maximumRetryAfterMaxDelay)
	}
	return policy, nil
}

func (c *Client) OpenAPI() *OpenAPIClient { return c.connection.OpenAPI() }

type openAPIHeadersContextKey struct{}

func withOpenAPIHeaders(ctx context.Context, headers http.Header) context.Context {
	return context.WithValue(ctx, openAPIHeadersContextKey{}, headers.Clone())
}

func validateIdempotencyKey(key string) error {
	return transport.ValidateIdempotencyKey("service", key)
}

// doOpenAPI runs a generated operation through the shared executor. Service
// forwards the caller's headers; the executor applies the management bearer
// and forwards If-Match only where the operation declares it.
func (c *Connection) doOpenAPI(ctx context.Context, id openAPIOperationID, pathParameters map[string]string, query url.Values, body, out any) error {
	operation, err := resolveOpenAPIOperation(id, pathParameters, query)
	if err != nil {
		return err
	}
	header := http.Header{}
	if configured, ok := ctx.Value(openAPIHeadersContextKey{}).(http.Header); ok {
		header = configured.Clone()
	}
	_, err = c.executor.Do(ctx, transport.Call{Operation: operation, Header: header, Body: body}, out)
	return err
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
