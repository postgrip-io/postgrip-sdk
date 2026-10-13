package postgrip

import (
	"fmt"
	"net/http"
	"os"

	agent "github.com/postgrip-io/postgrip-agent-sdks/go/agent/client"
	"github.com/postgrip-io/postgrip-agent-sdks/go/internal/transport"
	"github.com/postgrip-io/postgrip-agent-sdks/go/service"
	"github.com/postgrip-io/postgrip-agent-sdks/go/worker"
)

// Config configures all public PostGrip planes with one tenant token.
// Explicit plane URLs override BaseURL.
type Config struct {
	BaseURL             string
	AgentURL            string
	WorkerURL           string
	ServiceURL          string
	Token               string
	HTTPClient          *http.Client
	InsecureDevelopment bool
	EnableRetries       bool
}

// Client is the unified facade. Agent contains application and managed-runtime
// facilities; Workers and Services are the management collections.
type Client struct {
	Agent    *agent.Client
	Workers  *worker.Client
	Services *service.Client
}

// New constructs all three plane clients without exchanging or copying token
// authority between them.
func New(config Config) (*Client, error) {
	token, err := transport.ManagementToken("sdk", config.Token)
	if err != nil {
		return nil, err
	}
	baseURL := transport.FirstNonEmpty(config.BaseURL)
	agentURL := transport.FirstNonEmpty(config.AgentURL, baseURL)
	workerURL := transport.FirstNonEmpty(config.WorkerURL, baseURL)
	serviceURL := transport.FirstNonEmpty(config.ServiceURL, baseURL)
	if agentURL == "" || workerURL == "" || serviceURL == "" {
		return nil, fmt.Errorf("postgrip: configure POSTGRIP_URL or every plane URL")
	}
	if _, err := transport.ParseBaseURL("agent", agentURL, config.InsecureDevelopment); err != nil {
		return nil, err
	}
	agentConnection, err := agent.NewConnection(agent.ConnectionOptions{
		Address: agentURL, AuthToken: token, HTTPClient: config.HTTPClient,
		InsecureDevelopment: config.InsecureDevelopment, EnableRetries: config.EnableRetries,
	})
	if err != nil {
		return nil, err
	}
	workers, err := worker.New(worker.Config{
		BaseURL: workerURL, Token: token, HTTPClient: config.HTTPClient,
		InsecureDevelopment: config.InsecureDevelopment, EnableRetries: config.EnableRetries,
	})
	if err != nil {
		return nil, err
	}
	services, err := service.New(service.Config{
		BaseURL: serviceURL, Token: token, HTTPClient: config.HTTPClient,
		InsecureDevelopment: config.InsecureDevelopment, EnableRetries: config.EnableRetries,
	})
	if err != nil {
		return nil, err
	}
	return &Client{Agent: agent.New(agentConnection), Workers: workers, Services: services}, nil
}

// NewFromEnv resolves the common token and URL using the documented
// explicit-plane-over-common precedence.
func NewFromEnv() (*Client, error) {
	return New(Config{
		BaseURL:    os.Getenv("POSTGRIP_URL"),
		AgentURL:   os.Getenv("POSTGRIP_AGENT_URL"),
		WorkerURL:  os.Getenv("POSTGRIP_WORKER_URL"),
		ServiceURL: os.Getenv("POSTGRIP_SERVICE_URL"),
		Token:      os.Getenv("POSTGRIP_TOKEN"),
	})
}
