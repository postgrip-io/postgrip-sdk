package client

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/postgrip-io/postgrip-agent-sdks/go/agent/failure"
	"github.com/postgrip-io/postgrip-agent-sdks/go/internal/transport"
	"github.com/postgrip-io/postgrip-agent-sdks/go/protocol"
)

const DefaultAddress = "https://agentorchestrator1.postgrip.io"

// Agent task results may contain a single signed event payload up to 32 MiB.
// Cursor pages are server-bounded to 36 MiB, leaving envelope headroom while
// keeping every ordinary response read finite.
const maxResponseBytes = 40 << 20

const defaultUploadTimeout = 30 * time.Minute

// ConnectionOptions configures the HTTP connection to the agent runtime
// service. Address is the base URL (defaults to DefaultAddress).
// AuthToken is the common tenant-bound bearer sent as
// `Authorization: Bearer <token>` on management endpoints. Global-
// administration APIs are not part of this SDK.
// AgentID + delegated AgentAccessToken / AgentRefreshToken /
// AgentSigningPrivateKey are used only when this connection is running inside
// a managed workflow runtime launched by a PostGrip host agent.
type ConnectionOptions struct {
	Address                string
	AuthToken              string
	HTTPClient             *http.Client
	Headers                map[string]string
	RequestTimeout         time.Duration
	InsecureDevelopment    bool
	AgentID                string
	AgentName              string
	AgentHost              string
	AgentNamespace         string
	AgentQueue             string
	AgentAccessToken       string
	AgentRefreshToken      string
	AgentAccessExpiresAt   time.Time
	AgentSigningPrivateKey string
	// EnableRetries opts in to bounded retries of contract-eligible operations:
	// annotated bounded reads, never signed, protocol or streaming requests.
	EnableRetries bool
}

// Connection is the HTTP transport layer. It is safe for concurrent use.
type Connection struct {
	address             string
	httpClient          *http.Client
	ownsHTTPClient      bool
	authHeader          string
	headers             map[string]string
	insecureDevelopment bool
	executor            *transport.Executor

	// Agent (worker-side) auth state. Mutated by ensureAgentSession; reads
	// must hold agentMu. Agent sessions must be delegated by a host agent and
	// injected into managed workflow runtimes.
	agentMu                sync.Mutex
	agentRefreshMu         sync.Mutex
	agentID                string
	agentName              string
	agentHost              string
	agentNamespace         string
	agentQueue             string
	agentAccessToken       string
	agentRefreshToken      string
	agentAccessExpiresUnix int64

	// Ed25519 keypair the managed runtime uses to sign requests to
	// agent-authed endpoints. It is injected by the host agent.
	agentSignPriv ed25519.PrivateKey
	agentSignPub  ed25519.PublicKey
}

// NewConnection constructs a Connection after validating its base URL and
// installing the shared redirect-safe HTTP policy.
func NewConnection(opts ConnectionOptions) (*Connection, error) {
	address := firstNonEmpty(opts.Address, os.Getenv("POSTGRIP_AGENT_URL"), os.Getenv("POSTGRIP_URL"))
	if address == "" {
		address = DefaultAddress
	}
	baseURL, err := transport.ParseBaseURL("agent", address, opts.InsecureDevelopment)
	if err != nil {
		return nil, err
	}
	address = strings.TrimRight(baseURL.String(), "/")
	httpClient := opts.HTTPClient
	if httpClient == nil {
		timeout := opts.RequestTimeout
		if timeout <= 0 {
			timeout = 30 * time.Second
		}
		httpClient = &http.Client{Timeout: timeout}
	}
	httpClient = transport.HTTPClient(httpClient)
	agentID := firstNonEmpty(opts.AgentID, os.Getenv("POSTGRIP_AGENT_ID"))
	namespace := firstNonEmpty(opts.AgentNamespace, os.Getenv("POSTGRIP_AGENT_NAMESPACE"), DefaultNamespace)
	queue := firstNonEmpty(opts.AgentQueue, os.Getenv("POSTGRIP_AGENT_TASK_QUEUE"), DefaultQueue)
	accessToken := firstNonEmpty(opts.AgentAccessToken, os.Getenv("POSTGRIP_AGENT_ACCESS_TOKEN"))
	refreshToken := firstNonEmpty(opts.AgentRefreshToken, os.Getenv("POSTGRIP_AGENT_REFRESH_TOKEN"))
	accessExpiresAt := opts.AgentAccessExpiresAt
	if accessExpiresAt.IsZero() {
		accessExpiresAt = parseAgentAccessExpiresAt(os.Getenv("POSTGRIP_AGENT_ACCESS_EXPIRES_AT"))
	}
	signingPrivateKey := firstNonEmpty(opts.AgentSigningPrivateKey, os.Getenv("POSTGRIP_AGENT_SIGNING_PRIVATE_KEY"))
	signPriv, signPub, err := decodeAgentSigningPrivateKey(signingPrivateKey)
	if err != nil {
		return nil, err
	}
	authHeader := ""
	managementToken := firstNonEmpty(opts.AuthToken, os.Getenv("POSTGRIP_TOKEN"))
	if managementToken != "" {
		authHeader = "Bearer " + managementToken
	}
	headers := make(map[string]string, len(opts.Headers))
	for k, v := range opts.Headers {
		headers[k] = v
	}
	connection := &Connection{
		address:                address,
		httpClient:             httpClient,
		ownsHTTPClient:         opts.HTTPClient == nil,
		authHeader:             authHeader,
		headers:                headers,
		insecureDevelopment:    opts.InsecureDevelopment,
		agentID:                agentID,
		agentName:              opts.AgentName,
		agentHost:              opts.AgentHost,
		agentNamespace:         namespace,
		agentQueue:             queue,
		agentAccessToken:       accessToken,
		agentRefreshToken:      refreshToken,
		agentAccessExpiresUnix: accessExpiresAt.Unix(),
		agentSignPriv:          signPriv,
		agentSignPub:           signPub,
	}
	connection.executor = &transport.Executor{
		Plane:      "agent",
		BaseURL:    baseURL,
		HTTPClient: httpClient,
		Credentials: transport.Credentials{
			ManagementToken: managementToken,
			HasDelegated:    connection.hasAgentRuntimeCredentials,
			Delegated:       connection.delegatedAccessToken,
		},
		CallerHeadersReplace: true,
		Retry: transport.RetryConfig{
			Enabled:       opts.EnableRetries,
			MaxAttempts:   3,
			MaxDelay:      2 * time.Second,
			RetryAfterMax: 30 * time.Second,
		},
		MaxResponseBytes: maxResponseBytes,
		Sign:             connection.signAgentRequest,
		PlaneError:       agentHTTPError,
	}
	return connection, nil
}

// Address returns the canonical base URL of the runtime service.
func (c *Connection) Address() string { return c.address }

// Health hits /healthz; returns the parsed JSON body. Useful as a smoke
// test at startup before consuming Client APIs.
func (c *Connection) Health(ctx context.Context) (map[string]any, error) {
	out, err := c.OpenAPI().Health(ctx)
	if err != nil {
		return nil, err
	}
	return map[string]any{"status": out.Status}, nil
}

// doOpenAPI runs one generated JSON operation through the shared executor,
// which applies the contract's auth lane, signing, retry, response bound and
// error envelope. The Agent adapter supplies the delegated-session and signing
// hooks and keeps long-poll and terminal-poll handling.
func (c *Connection) doOpenAPI(ctx context.Context, id openAPIOperationID, pathParameters map[string]string, query url.Values, body any, out any) error {
	operation, err := resolveOpenAPIOperation(id, pathParameters, query)
	if err != nil {
		return &failure.SDKError{Message: "resolve OpenAPI operation", Cause: err}
	}
	call := transport.Call{Operation: operation, Header: c.callerHeaders(), Body: body}
	if id == openAPIPollAgentTask {
		// Poll Gone is a successful terminal response handled below. A long
		// poll's server hold counts against the exchange, so give it headroom.
		call.AcceptedStatuses = []int{http.StatusGone}
		// A caller-supplied http.Client keeps its Timeout as given; only the
		// connection's own client gets the long-poll headroom.
		if wait, err := strconv.Atoi(query.Get("wait_seconds")); err == nil && wait > 0 && c.ownsHTTPClient {
			call.Lifetime = time.Duration(wait)*time.Second + 30*time.Second
		}
	}
	response, err := c.executor.Do(ctx, call, out)
	if err != nil {
		var sdkErr *failure.SDKError
		if errors.As(err, &sdkErr) {
			return err
		}
		var local *transport.Error
		if errors.As(err, &local) {
			return agentLocalError(operation, local)
		}
		return &failure.SDKError{Message: "http request", Cause: err}
	}
	if response.StatusCode != http.StatusGone {
		// The executor treats a whitespace-only success body as empty. Agent
		// decodes every non-empty body, so such a body stays malformed here.
		if out != nil && len(response.Body) > 0 && len(bytes.TrimSpace(response.Body)) == 0 {
			return agentLocalError(operation, &transport.Error{Plane: "agent", Op: "decode response", Err: json.Unmarshal(response.Body, out)})
		}
		return nil
	}
	// Decode any directive fields the server supplied, but retain terminal
	// semantics if an intermediary returned an empty or malformed body.
	if terminal, ok := out.(*OpenAPIPollAgentTaskResponseBody); ok {
		_ = json.Unmarshal(response.Body, terminal)
		if terminal.Directive == nil {
			terminal.Directive = &AgentPollDirective{Type: AgentPollDirectiveTypeShutdown}
		} else {
			terminal.Directive.Type = AgentPollDirectiveTypeShutdown
		}
	}
	return nil
}

// callerHeaders returns the connection's configured headers for one request.
func (c *Connection) callerHeaders() http.Header {
	header := make(http.Header, len(c.headers))
	for k, v := range c.headers {
		header.Set(k, v)
	}
	return header
}

// delegatedAccessToken is the executor's credential hook for the agent lane:
// it refreshes the delegated session when needed before every attempt.
func (c *Connection) delegatedAccessToken(ctx context.Context) (string, error) {
	if err := c.ensureAgentSession(ctx, "", "", ""); err != nil {
		return "", err
	}
	c.agentMu.Lock()
	defer c.agentMu.Unlock()
	return c.agentAccessToken, nil
}

// signAgentRequest applies the agent-task-v1 signature to the final request,
// over the exact encoded body. Without an injected signing key the request is
// sent unsigned, as before.
func (c *Connection) signAgentRequest(req *http.Request, body []byte) error {
	c.agentMu.Lock()
	priv := c.agentSignPriv
	pub := c.agentSignPub
	c.agentMu.Unlock()
	if len(priv) != ed25519.PrivateKeySize {
		return nil
	}
	ts := time.Now().UTC()
	payload := protocol.AgentRequestSignaturePayload{
		Method:    req.Method,
		Path:      req.URL.Path,
		Query:     req.URL.RawQuery,
		Timestamp: ts,
		Body:      body,
	}
	req.Header.Set(protocol.HeaderAgentSignatureTimestamp, fmt.Sprintf("%d", ts.Unix()))
	req.Header.Set(protocol.HeaderAgentSignatureKeyID, protocol.AgentSigningKeyID(pub))
	req.Header.Set(protocol.HeaderAgentSignature, protocol.SignAgentRequest(priv, payload))
	return nil
}

// agentLocalError keeps the Agent's existing messages for executor-local
// failures, including the request context of a decode failure.
func agentLocalError(operation transport.Operation, local *transport.Error) error {
	switch local.Op {
	case "encode request":
		return &failure.SDKError{Message: "encode request body", Cause: local.Err}
	case "response is invalid or too large":
		if local.Err != nil {
			return &failure.SDKError{Message: "read response body", Cause: local.Err}
		}
		return &failure.SDKError{Message: "read response body", Cause: errors.New("postgrip-agent: response is invalid or too large")}
	case "decode response":
		return &failure.SDKError{Message: fmt.Sprintf("decode response from %s %s", operation.Method, operation.Path), Cause: local.Err}
	default:
		return &failure.SDKError{Message: local.Op, Cause: local.Err}
	}
}

// agentHTTPError converts the decoded envelope into the Agent's SDKError. The
// default text holds only the method, quoted route, status and standard status
// text; server content stays in the explicit fields.
func agentHTTPError(apiErr *transport.APIError) error {
	err := httpStatusError(apiErr.Method, apiErr.Route, apiErr.StatusCode, apiErr.Body)
	err.Code = apiErr.Code
	err.RequestID = apiErr.RequestID
	err.Details = apiErr.Details
	return err
}

func queryValues(params map[string]string) url.Values {
	values := url.Values{}
	for k, v := range params {
		if v == "" {
			continue
		}
		values.Set(k, v)
	}
	return values
}

// doStream sends a raw request body rather than JSON-encoding a value, for
// endpoints whose payload is a byte stream — today only the workspace archive
// upload, which takes the gzipped tar directly rather than as multipart.
//
// Always management-authenticated: no streaming endpoint is on the agent lane,
// and the agent request signature covers the body, which would mean buffering
// an archive that can reach 512 MiB just to sign it.
func (c *Connection) doStream(ctx context.Context, method, path string, body io.Reader, headers map[string]string, out any) error {
	if _, bounded := ctx.Deadline(); !bounded {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, defaultUploadTimeout)
		defer cancel()
	}
	req, err := http.NewRequestWithContext(ctx, method, c.address+path, body)
	if err != nil {
		return &failure.SDKError{Message: "build request", Cause: err}
	}
	for k, v := range c.headers {
		req.Header.Set(k, v)
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	if c.authHeader != "" && !hasAuthorizationHeader(req.Header) {
		req.Header.Set("Authorization", c.authHeader)
	}
	// Archives can reach 512 MiB, so use the upload context's deadline instead
	// of the ordinary request timeout. A caller deadline takes precedence over
	// the generous default above, including when a slower link needs longer.
	streamClient := *c.httpClient
	streamClient.Timeout = 0
	resp, err := streamClient.Do(req)
	if err != nil {
		return &failure.SDKError{Message: "http request", Cause: err}
	}
	defer resp.Body.Close()
	raw, err := readResponseBody(resp.Body, maxResponseBytes)
	if err != nil {
		return &failure.SDKError{Message: "read response body", Cause: err}
	}
	if resp.StatusCode >= 400 {
		return httpStatusError(method, path, resp.StatusCode, raw)
	}
	if out == nil || len(raw) == 0 {
		return nil
	}
	if err := json.Unmarshal(raw, out); err != nil {
		return &failure.SDKError{Message: fmt.Sprintf("decode response from %s %s", method, path), Cause: err}
	}
	return nil
}

// httpStatusError keeps untrusted response content out of default log messages.
// Preserve the raw body for explicit inspection and terminal polling directives.
func httpStatusError(method, path string, status int, body []byte) *failure.SDKError {
	return &failure.SDKError{
		Message:      fmt.Sprintf("%q %q -> %d %s", method, path, status, http.StatusText(status)),
		StatusCode:   status,
		ResponseBody: append([]byte(nil), body...),
	}
}

func readResponseBody(body io.Reader, limit int64) ([]byte, error) {
	if limit <= 0 {
		return io.ReadAll(body)
	}
	raw, err := io.ReadAll(io.LimitReader(body, limit+1))
	if err != nil {
		return nil, err
	}
	if int64(len(raw)) > limit {
		return nil, errors.New("postgrip-agent: response is invalid or too large")
	}
	return raw, nil
}

func hasAuthorizationHeader(headers http.Header) bool {
	for name := range headers {
		if strings.EqualFold(name, "Authorization") {
			return true
		}
	}
	return false
}

func (c *Connection) doStreamOpenAPI(ctx context.Context, id openAPIOperationID, body io.Reader, headers map[string]string, out any) error {
	operation, err := resolveOpenAPIOperation(id, nil, nil)
	if err != nil {
		return &failure.SDKError{Message: "resolve OpenAPI operation", Cause: err}
	}
	if !operation.StreamingRequest {
		return &failure.SDKError{Message: fmt.Sprintf("OpenAPI operation %q is not a streaming request", id)}
	}
	return c.doStream(ctx, operation.Method, operation.Path, body, headers, out)
}

// AuthHeader returns the management Authorization header value, empty when the
// connection has no management token. The sandbox relay dial needs it: the
// session ticket authorizes the session, but the request is still
// authenticated normally.
func (c *Connection) AuthHeader() string { return c.authHeader }

// ConfiguredHeaders returns a copy of the headers set on the connection.
//
// Callers that reach the API over something other than the plain HTTP client
// need these too. The sandbox relay dials a WebSocket, and a gateway that
// authenticates on a header will reject that upgrade without them — while
// every preceding sandbox request succeeds, because those go through the HTTP
// client that does send them.
func (c *Connection) ConfiguredHeaders() map[string]string {
	out := make(map[string]string, len(c.headers))
	for k, v := range c.headers {
		out[k] = v
	}
	return out
}
