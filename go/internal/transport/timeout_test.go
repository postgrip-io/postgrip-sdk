package transport

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"testing/synctest"
	"time"
)

type timeoutTransport func(*http.Request) (*http.Response, error)

func (f timeoutTransport) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func TestHTTPClientTimeoutPolicy(t *testing.T) {
	for _, original := range []time.Duration{0, -time.Second, 2 * time.Minute} {
		t.Run(original.String(), func(t *testing.T) {
			synctest.Test(t, func(t *testing.T) {
				source := &http.Client{Timeout: original, Transport: timeoutTransport(func(r *http.Request) (*http.Response, error) { <-r.Context().Done(); return nil, r.Context().Err() })}
				c := HTTPClient(source)
				want := original
				if want <= 0 {
					want = 30 * time.Second
				}
				start := time.Now()
				_, err := c.Get("https://example.test")
				if !errors.Is(err, context.DeadlineExceeded) || time.Since(start) != want {
					t.Fatalf("elapsed=%v error=%v", time.Since(start), err)
				}
				if source.Timeout != original {
					t.Fatal("custom client configuration changed")
				}
			})
		})
	}
	if got := HTTPClient(nil).Timeout; got <= 0 {
		t.Fatalf("default client timeout=%v", got)
	}
}

func TestHTTPClientBoundsResponseBody(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.(http.Flusher).Flush()
		<-r.Context().Done()
	}))
	defer s.Close()
	c := HTTPClient(&http.Client{Timeout: 50 * time.Millisecond})
	resp, err := c.Get(s.URL)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if _, err = io.ReadAll(resp.Body); !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("body read: %v", err)
	}
}

func TestHTTPClientPreservesEarlierContextDeadline(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		c := HTTPClient(&http.Client{Transport: timeoutTransport(func(r *http.Request) (*http.Response, error) { <-r.Context().Done(); return nil, r.Context().Err() })})
		ctx, cancel := context.WithTimeout(context.Background(), time.Second)
		defer cancel()
		req, _ := http.NewRequestWithContext(ctx, http.MethodGet, "https://example.test", nil)
		start := time.Now()
		_, err := c.Do(req)
		if !errors.Is(err, context.DeadlineExceeded) || time.Since(start) != time.Second {
			t.Fatalf("elapsed=%v error=%v", time.Since(start), err)
		}
	})
}
