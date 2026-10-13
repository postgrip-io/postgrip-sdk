package postgrip

import (
	"context"
	"errors"
	"github.com/postgrip-io/postgrip-agent-sdks/go/service"
	"github.com/postgrip-io/postgrip-agent-sdks/go/worker"
	"net/http"
	"testing"
	"testing/synctest"
	"time"
)

type planeTimeoutTransport func(*http.Request) (*http.Response, error)

func (f planeTimeoutTransport) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }
func TestUnifiedPlanesBoundZeroTimeoutClient(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		source := &http.Client{Transport: planeTimeoutTransport(func(r *http.Request) (*http.Response, error) { <-r.Context().Done(); return nil, r.Context().Err() })}
		c, err := New(Config{BaseURL: "https://example.test", Token: "synthetic", HTTPClient: source})
		if err != nil {
			t.Fatal(err)
		}
		calls := map[string]func() error{
			"agent":  func() error { _, err := c.Agent.Connection.Health(context.Background()); return err },
			"worker": func() error { _, err := c.Workers.List(context.Background(), worker.ListWorkersOptions{}); return err },
			"service": func() error {
				_, err := c.Services.List(context.Background(), service.OpenAPIListServicesQuery{})
				return err
			},
		}
		for name, call := range calls {
			start := time.Now()
			err := call()
			if !errors.Is(err, context.DeadlineExceeded) || time.Since(start) != 30*time.Second {
				t.Fatalf("%s elapsed=%v error=%v", name, time.Since(start), err)
			}
		}
		if source.Timeout != 0 {
			t.Fatal("mutated caller's client")
		}
	})
}
