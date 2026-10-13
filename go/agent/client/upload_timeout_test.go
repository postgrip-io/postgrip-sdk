package client

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"testing"
	"testing/synctest"
	"time"
)

type uploadTimeoutTransport func(*http.Request) (*http.Response, error)

func (f uploadTimeoutTransport) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func TestUploadWorkspaceDeadline(t *testing.T) {
	for _, explicit := range []time.Duration{0, time.Second, time.Hour} {
		t.Run(explicit.String(), func(t *testing.T) {
			synctest.Test(t, func(t *testing.T) {
				source := &http.Client{Timeout: time.Millisecond, Transport: uploadTimeoutTransport(func(r *http.Request) (*http.Response, error) { <-r.Context().Done(); return nil, r.Context().Err() })}
				c, err := NewConnection(ConnectionOptions{Address: "https://example.test", HTTPClient: source})
				if err != nil {
					t.Fatal(err)
				}
				ctx := context.Background()
				want := defaultUploadTimeout
				if explicit > 0 {
					var cancel context.CancelFunc
					ctx, cancel = context.WithTimeout(ctx, explicit)
					defer cancel()
					want = explicit
				}
				start := time.Now()
				_, err = c.UploadWorkspace(ctx, strings.NewReader("archive"), "repo", "rev")
				if !errors.Is(err, context.DeadlineExceeded) || time.Since(start) != want {
					t.Fatalf("elapsed=%v error=%v", time.Since(start), err)
				}
				if source.Timeout != time.Millisecond || c.httpClient.Timeout != time.Millisecond {
					t.Fatal("upload mutated ordinary timeout")
				}
			})
		})
	}
}

func TestUploadWorkspacePreservesCancellation(t *testing.T) {
	c, err := NewConnection(ConnectionOptions{Address: "https://example.test", HTTPClient: &http.Client{Transport: uploadTimeoutTransport(func(r *http.Request) (*http.Response, error) { <-r.Context().Done(); return nil, r.Context().Err() })}})
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err = c.UploadWorkspace(ctx, strings.NewReader("archive"), "repo", "rev")
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("upload cancellation: %v", err)
	}
}
