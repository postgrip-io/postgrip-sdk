// Package worker provides the public PostGrip Worker management client.
package worker

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

// Worker execution policy: a 4 MiB response bound, three attempts for eligible
// operations when retries are enabled, 2-second backoff and a fixed 30-second
// Retry-After cap.
const (
	maxResponseBytes  = 4 << 20
	retryMaxAttempts  = 3
	retryMaxDelay     = 2 * time.Second
	retryAfterMaxWait = 30 * time.Second
)

// snapshotRunLifetime bounds createWorkerSnapshot. The server waits up to 5
// minutes for the run before it answers, so the call needs longer than the
// default 30-second exchange; a shorter caller context deadline still wins.
const snapshotRunLifetime = 6 * time.Minute

// operationCallPolicy holds the Worker plane's per-operation exchange policy.
// createWorkerSnapshot's 502 and 504 answers are not kept against the
// Idempotency-Key, so an automatic resend, even with the same key, would take
// another snapshot; the caller reads the snapshot status first instead.
var operationCallPolicy = map[openAPIOperationID]struct {
	lifetime time.Duration
	noRetry  []int
}{
	openAPICreateWorkerSnapshot: {lifetime: snapshotRunLifetime, noRetry: []int{http.StatusBadGateway, http.StatusGatewayTimeout}},
}

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
	followInterval time.Duration
	executor       *transport.Executor
}

// APIError is a Worker management failure decoded from the common error
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
		return fmt.Sprintf("postgrip-worker: HTTP %d: %s", e.StatusCode, e.Message)
	}
	return fmt.Sprintf("postgrip-worker: %s (HTTP %d): %s", e.Code, e.StatusCode, e.Message)
}

// newAPIError converts the shared decoded envelope into the Worker error type.
func newAPIError(err *transport.APIError) error {
	return &APIError{StatusCode: err.StatusCode, Code: err.Code, Message: err.Message,
		RequestID: err.RequestID, Details: err.Details, RetryAfter: err.RetryAfter}
}

func New(config Config) (*Client, error) {
	baseURL, err := transport.ParseBaseURL("worker", config.BaseURL, config.InsecureDevelopment)
	if err != nil {
		return nil, err
	}
	token, err := transport.ManagementToken("worker", config.Token)
	if err != nil {
		return nil, err
	}
	interval := config.FollowInterval
	if interval <= 0 {
		interval = 2 * time.Second
	}
	executor := &transport.Executor{
		Plane: "worker", BaseURL: baseURL, HTTPClient: transport.HTTPClient(config.HTTPClient),
		Credentials: transport.Credentials{ManagementToken: token},
		Retry: transport.RetryConfig{
			Enabled: config.EnableRetries, MaxAttempts: retryMaxAttempts,
			MaxDelay: retryMaxDelay, RetryAfterMax: retryAfterMaxWait,
		},
		MaxResponseBytes: maxResponseBytes,
		PlaneError:       newAPIError,
	}
	return &Client{connection: &Connection{
		baseURL: baseURL, token: token, followInterval: interval, executor: executor,
	}}, nil
}

// NewFromEnv fills empty values from the unified PostGrip environment.
func NewFromEnv(config Config) (*Client, error) {
	if strings.TrimSpace(config.BaseURL) == "" {
		config.BaseURL = transport.FirstNonEmpty(os.Getenv("POSTGRIP_WORKER_URL"), os.Getenv("POSTGRIP_URL"))
	}
	if strings.TrimSpace(config.Token) == "" {
		config.Token = os.Getenv("POSTGRIP_TOKEN")
	}
	return New(config)
}

func (c *Client) OpenAPI() *OpenAPIClient { return c.connection.OpenAPI() }

func (c *Client) Health(ctx context.Context) (HealthResponse, error) {
	return c.OpenAPI().WorkerOrchestratorHealth(ctx)
}

type openAPIHeadersContextKey struct{}

func withOpenAPIHeaders(ctx context.Context, headers http.Header) context.Context {
	return context.WithValue(ctx, openAPIHeadersContextKey{}, headers.Clone())
}

// doOpenAPI runs a generated operation through the shared executor. Worker
// forwards only the caller's Idempotency-Key and If-Match; other caller headers
// are not sent, and the executor drops If-Match where the operation does not
// declare it.
func (c *Connection) doOpenAPI(ctx context.Context, id openAPIOperationID, pathParameters map[string]string, query url.Values, body, out any) error {
	operation, err := resolveOpenAPIOperation(id, pathParameters, query)
	if err != nil {
		return err
	}
	header := http.Header{}
	if headers, ok := ctx.Value(openAPIHeadersContextKey{}).(http.Header); ok {
		for _, name := range []string{"Idempotency-Key", "If-Match"} {
			if value := headers.Get(name); value != "" {
				header.Set(name, value)
			}
		}
	}
	policy := operationCallPolicy[id]
	_, err = c.executor.Do(ctx, transport.Call{Operation: operation, Header: header, Body: body,
		Lifetime: policy.lifetime, NoRetryStatuses: policy.noRetry}, out)
	return err
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

// Create registers a pending Worker using caller-owned, write-only bootstrap
// material. Persist the request values and idempotency key durably before
// calling Create so a lost response can be replayed without creating a second
// Worker.
func (c *Client) Create(ctx context.Context, request CreateWorkerRequest, idempotencyKey string) (CreateWorkerResponse, error) {
	return c.OpenAPI().CreateWorker(ctx, OpenAPICreateWorkerHeaders{IdempotencyKey: idempotencyKey}, request)
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
	return c.OpenAPI().CheckWorker(ctx, workerID, OpenAPICheckWorkerHeaders{IdempotencyKey: idempotencyKey})
}

func (c *Client) Maintenance(ctx context.Context, workerID, idempotencyKey string) (WorkerOperationResponse, error) {
	return c.OpenAPI().PlaceWorkerInMaintenance(ctx, workerID, OpenAPIPlaceWorkerInMaintenanceHeaders{IdempotencyKey: idempotencyKey})
}

func (c *Client) Resume(ctx context.Context, workerID, idempotencyKey string) (WorkerOperationResponse, error) {
	return c.OpenAPI().ResumeWorkerFromMaintenance(ctx, workerID, OpenAPIResumeWorkerFromMaintenanceHeaders{IdempotencyKey: idempotencyKey})
}

func (c *Client) Upgrade(ctx context.Context, workerID, idempotencyKey string) (UpgradeWorkerResponse, error) {
	return c.OpenAPI().UpgradeWorker(ctx, workerID, OpenAPIUpgradeWorkerHeaders{IdempotencyKey: idempotencyKey})
}

// SnapshotStatus reads the Worker's snapshot schedule and last run. It answers
// with Enabled false when snapshots are off.
func (c *Client) SnapshotStatus(ctx context.Context, workerID string) (WorkerSnapshotStatus, error) {
	return c.OpenAPI().GetWorkerSnapshotStatus(ctx, workerID)
}

// Snapshots lists the Worker's archives in its storage destination, newest
// first. The list is not paged.
func (c *Client) Snapshots(ctx context.Context, workerID string) (WorkerSnapshotList, error) {
	return c.OpenAPI().ListWorkerSnapshots(ctx, workerID)
}

// TakeSnapshot runs a snapshot on the Worker and waits for it. The server
// waits up to 5 minutes, so the exchange is allowed 6 minutes, and its 502 and
// 504 answers are never retried automatically: a 504 SNAPSHOT_UNCONFIRMED run
// may still land, so read SnapshotStatus before resending with a new key.
func (c *Client) TakeSnapshot(ctx context.Context, workerID, idempotencyKey string) (CreateWorkerSnapshotResponse, error) {
	return c.OpenAPI().CreateWorkerSnapshot(ctx, workerID, OpenAPICreateWorkerSnapshotHeaders{IdempotencyKey: idempotencyKey})
}

// SnapshotSettings reads the Worker's snapshot settings. The signing key is
// never answered; HasSigningKey reports whether one is stored.
func (c *Client) SnapshotSettings(ctx context.Context, workerID string) (WorkerSnapshotSettings, error) {
	return c.OpenAPI().GetWorkerSnapshotSettings(ctx, workerID)
}

// UpdateSnapshotSettings replaces the Worker's whole snapshot settings record:
// every field but Enabled takes its zero value when omitted. SigningKey is
// write-only; leave it nil to keep the stored key.
func (c *Client) UpdateSnapshotSettings(ctx context.Context, workerID string, request UpdateWorkerSnapshotSettingsRequest, idempotencyKey string) (UpdateWorkerSnapshotSettingsResponse, error) {
	return c.OpenAPI().UpdateWorkerSnapshotSettings(ctx, workerID, OpenAPIUpdateWorkerSnapshotSettingsHeaders{IdempotencyKey: idempotencyKey}, request)
}

// StorageDestinations lists the organization's storage destinations, ordered
// by name; the list is not paged. A destination's Id is the
// StorageDestinationId that UpdateSnapshotSettings takes. No credential is
// answered: the access key and secret stay on the Workers.
func (c *Client) StorageDestinations(ctx context.Context) (StorageDestinationList, error) {
	return c.OpenAPI().ListStorageDestinations(ctx)
}

// RemoveOptions carries the two fences a Worker removal requires: the
// idempotency key and the removal impact's etag, sent as If-Match.
type RemoveOptions struct {
	IdempotencyKey string
	IfMatch        string
}

func (o RemoveOptions) validate() error {
	if err := transport.ValidateIdempotencyKey("worker", o.IdempotencyKey); err != nil {
		return err
	}
	if strings.TrimSpace(o.IfMatch) == "" || strings.ContainsAny(o.IfMatch, "\r\n") {
		return errors.New("postgrip-worker: If-Match ETag must be non-empty and contain no line breaks")
	}
	return nil
}

// RemovalImpact reads what removing the Worker would delete or change. Its
// Etag, equal to the ETag header, is the fence Remove sends as If-Match. A
// ManagedVolumeCount above zero means the removal will be refused.
func (c *Client) RemovalImpact(ctx context.Context, workerID string) (WorkerRemovalImpact, error) {
	return c.OpenAPI().GetWorkerRemovalImpact(ctx, workerID)
}

// Remove removes the Worker, its services and its exclusive deploy projects.
// options.IfMatch must be the Etag of a RemovalImpact read: a changed impact
// answers 412 PRECONDITION_FAILED and nothing is changed. Both fences are
// validated before any request. The key does not cover If-Match, so after a
// refusal read the impact again and send the removal with a new key.
func (c *Client) Remove(ctx context.Context, workerID string, options RemoveOptions) (RemoveWorkerResponse, error) {
	if err := options.validate(); err != nil {
		return RemoveWorkerResponse{}, err
	}
	return c.OpenAPI().RemoveWorker(ctx, workerID, OpenAPIRemoveWorkerHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch})
}
