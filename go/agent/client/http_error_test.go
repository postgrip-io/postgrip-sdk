package client

import (
	"context"
	"errors"
	"github.com/postgrip-io/postgrip-agent-sdks/go/agent/failure"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestHTTPFailuresDoNotLogResponseBodies(t *testing.T) {
	for _, body := range []string{"synthetic-secret\nFORGED entry\r\x1b[31m", `{"message":"synthetic-secret","token":"synthetic-secret"}`, ""} {
		for _, upload := range []bool{false, true} {
			s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(http.StatusBadRequest)
				_, _ = io.WriteString(w, body)
			}))
			c, err := NewConnection(ConnectionOptions{Address: s.URL, InsecureDevelopment: true})
			if err != nil {
				t.Fatal(err)
			}
			if upload {
				_, err = c.UploadWorkspace(context.Background(), strings.NewReader("archive"), "repo", "rev")
			} else {
				_, err = c.Health(context.Background())
			}
			s.Close()
			var sdk *failure.SDKError
			if !errors.As(err, &sdk) {
				t.Fatalf("expected SDKError: %v", err)
			}
			if sdk.StatusCode != 400 || string(sdk.ResponseBody) != body {
				t.Fatalf("lost structured response: %#v", sdk)
			}
			if strings.ContainsAny(err.Error(), "\r\n\x1b") || strings.Contains(err.Error(), "synthetic-secret") || strings.Contains(err.Error(), "FORGED") {
				t.Fatalf("unsafe error text: %q", err.Error())
			}
			if !strings.Contains(err.Error(), "400 Bad Request") {
				t.Fatalf("lost status: %v", err)
			}
		}
	}
}
func TestHTTPStatusErrorQuotesRequestAndCopiesBody(t *testing.T) {
	body := []byte("secret")
	err := httpStatusError("GET\n", "/path\n\x1b", 599, body)
	body[0] = 'X'
	if string(err.ResponseBody) != "secret" || strings.ContainsAny(err.Error(), "\n\x1b") || strings.Contains(err.Error(), "secret") {
		t.Fatalf("unsafe status error: %q", err.Error())
	}
	if !strings.Contains(err.Error(), "599") {
		t.Fatal("lost nonstandard status")
	}
}

func TestHTTPErrorBodyPreservesTerminalPollDirective(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusGone)
		_, _ = io.WriteString(w, `{"directive":{"type":"shutdown","subject":"agent","expectedVersion":7}}`)
	}))
	defer s.Close()
	c, err := NewConnection(ConnectionOptions{Address: s.URL, InsecureDevelopment: true})
	if err != nil {
		t.Fatal(err)
	}
	c.SeedAgentSession("agent-1", "synthetic-delegated-token", time.Now().Add(time.Hour))
	out, err := c.OpenAPI().PollAgentTask(context.Background(), OpenAPIPollAgentTaskQuery{Queue: "queue"})
	if err != nil || out.Directive == nil || out.Directive.Type != "shutdown" || out.Directive.Subject != "agent" || out.Directive.ExpectedVersion != 7 {
		t.Fatalf("terminal poll lost response: %#v, %v", out, err)
	}
}
