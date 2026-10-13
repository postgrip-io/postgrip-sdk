package main

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"flag"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"sort"
	"time"

	agent "github.com/postgrip-io/postgrip-agent-sdks/go/agent/client"
	"github.com/postgrip-io/postgrip-agent-sdks/go/service"
	"github.com/postgrip-io/postgrip-agent-sdks/go/worker"
)

type requestFixture struct {
	PathParameters   map[string]string `json:"pathParameters"`
	Query            map[string]any    `json:"query"`
	Headers          map[string]string `json:"headers"`
	Body             json.RawMessage   `json:"body"`
	StreamBodyBase64 *string           `json:"streamBodyBase64"`
}

type responseFixture struct {
	Body json.RawMessage `json:"body"`
}

type fixture struct {
	OperationID string          `json:"operationId"`
	Plane       string          `json:"plane"`
	Request     requestFixture  `json:"request"`
	Response    responseFixture `json:"response"`
}

func main() {
	baseURL := flag.String("base-url", "", "recording server URL")
	fixtureRoot := flag.String("fixture-root", "", "recorded fixture root")
	plane := flag.String("plane", "all", "agent, worker, service, or all")
	flag.Parse()
	if *baseURL == "" || *fixtureRoot == "" {
		fatalf("base-url and fixture-root are required")
	}
	token := os.Getenv("POSTGRIP_TOKEN")
	accessToken := os.Getenv("POSTGRIP_AGENT_ACCESS_TOKEN")
	seed := os.Getenv("POSTGRIP_AGENT_SIGNING_PRIVATE_KEY")
	agentConnection, err := agent.NewConnection(agent.ConnectionOptions{
		Address: *baseURL, InsecureDevelopment: true, AuthToken: token, AgentID: "recorded-agent",
		AgentAccessToken: accessToken, AgentAccessExpiresAt: time.Now().Add(time.Hour),
		AgentSigningPrivateKey: seed,
	})
	if err != nil {
		fatalf("agent client: %v", err)
	}
	workerClient, err := worker.New(worker.Config{
		BaseURL: *baseURL, Token: token, InsecureDevelopment: true,
	})
	if err != nil {
		fatalf("worker client: %v", err)
	}
	serviceClient, err := service.New(service.Config{
		BaseURL: *baseURL, Token: token, InsecureDevelopment: true,
	})
	if err != nil {
		fatalf("service client: %v", err)
	}

	// Recorded operation fixtures live in one directory per plane; other
	// directories under the fixture root belong to other suites.
	planes := []string{"agent", "worker", "service"}
	if *plane != "all" {
		planes = []string{*plane}
	}
	var paths []string
	for _, name := range planes {
		matches, err := filepath.Glob(filepath.Join(*fixtureRoot, name, "*.json"))
		if err != nil {
			fatalf("fixtures: %v", err)
		}
		paths = append(paths, matches...)
	}
	sort.Strings(paths)
	completed := make([]string, 0, len(paths))
	for _, path := range paths {
		data, readErr := os.ReadFile(path)
		if readErr != nil {
			fatalf("read %s: %v", path, readErr)
		}
		var item fixture
		if err := json.Unmarshal(data, &item); err != nil {
			fatalf("decode %s: %v", path, err)
		}
		if item.OperationID == "connectSandboxSession" {
			continue
		}
		ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		var callErr error
		if item.OperationID == "uploadWorkspace" {
			archive, decodeErr := base64.StdEncoding.DecodeString(valueOrEmpty(item.Request.StreamBodyBase64))
			if decodeErr != nil {
				cancel()
				fatalf("decode upload fixture: %v", decodeErr)
			}
			_, callErr = agentConnection.UploadWorkspace(
				ctx,
				bytes.NewReader(archive),
				item.Request.Headers[agent.OpenAPIUploadWorkspaceHeaderXPostGripRepository],
				item.Request.Headers[agent.OpenAPIUploadWorkspaceHeaderXPostGripRevision],
			)
		} else {
			body := decodeJSON(item.Request.Body)
			var decoded any
			var out any
			if string(item.Response.Body) != "null" {
				out = &decoded
			}
			query := url.Values{}
			for name, value := range item.Request.Query {
				addQuery(query, name, value)
			}
			headers := http.Header{}
			for name, value := range item.Request.Headers {
				headers.Set(name, value)
			}
			switch item.Plane {
			case "agent":
				callErr = agentConnection.OpenAPI().Do(ctx, item.OperationID, item.Request.PathParameters, query, headers, body, out)
			case "worker":
				callErr = workerClient.OpenAPI().Do(ctx, item.OperationID, item.Request.PathParameters, query, headers, body, out)
			case "service":
				callErr = serviceClient.OpenAPI().Do(ctx, item.OperationID, item.Request.PathParameters, query, headers, body, out)
			default:
				callErr = fmt.Errorf("unknown plane %q", item.Plane)
			}
		}
		cancel()
		if callErr != nil {
			fatalf("%s/%s: %v", item.Plane, item.OperationID, callErr)
		}
		completed = append(completed, item.OperationID)
	}
	if err := json.NewEncoder(os.Stdout).Encode(map[string]any{
		"language": "go", "operations": completed,
	}); err != nil {
		fatalf("encode result: %v", err)
	}
}

func decodeJSON(raw json.RawMessage) any {
	if len(raw) == 0 || string(raw) == "null" {
		return nil
	}
	var value any
	if err := json.Unmarshal(raw, &value); err != nil {
		fatalf("decode request body: %v", err)
	}
	return value
}

func addQuery(values url.Values, name string, value any) {
	switch typed := value.(type) {
	case []any:
		for _, item := range typed {
			values.Add(name, fmt.Sprint(item))
		}
	case bool:
		values.Add(name, fmt.Sprintf("%t", typed))
	default:
		values.Add(name, fmt.Sprint(typed))
	}
}

func valueOrEmpty(value *string) string {
	if value == nil {
		return ""
	}
	return *value
}

func fatalf(format string, args ...any) {
	fmt.Fprintf(os.Stderr, format+"\n", args...)
	os.Exit(1)
}
