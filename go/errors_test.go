package postgrip

import (
	"errors"
	"fmt"
	"testing"
	"time"

	"github.com/postgrip-io/postgrip-agent-sdks/go/service"
	"github.com/postgrip-io/postgrip-agent-sdks/go/worker"
)

func TestPlaneAPIErrorsStayDistinctKeyedTypes(t *testing.T) {
	workerErr := worker.APIError{StatusCode: 429, Code: "RATE_LIMITED", Message: "slow down",
		RequestID: "req-worker", Details: map[string]any{"plane": "worker"}, RetryAfter: time.Second}
	serviceErr := service.APIError{StatusCode: 503, Code: "UNAVAILABLE", Message: "later",
		RequestID: "req-service", Details: map[string]any{"plane": "service"}, RetryAfter: 2 * time.Second}

	var workerTarget *worker.APIError
	if errors.As(fmt.Errorf("wrapped: %w", &serviceErr), &workerTarget) {
		t.Fatal("a Worker error target matched a Service error")
	}
	var serviceTarget *service.APIError
	if errors.As(fmt.Errorf("wrapped: %w", &workerErr), &serviceTarget) {
		t.Fatal("a Service error target matched a Worker error")
	}
	if !errors.As(fmt.Errorf("wrapped: %w", &workerErr), &workerTarget) || workerTarget.RequestID != "req-worker" {
		t.Fatal("a Worker error target did not match a Worker error")
	}
	if got, want := workerErr.Error(), "postgrip-worker: RATE_LIMITED (HTTP 429): slow down"; got != want {
		t.Fatalf("Worker error text = %q, want %q", got, want)
	}
}
