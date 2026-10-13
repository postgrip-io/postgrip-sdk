package service

import (
	"context"
	"net/url"
	"testing"
)

// recordingExecutor implements only the generated operation contract.
type recordingExecutor struct {
	id             openAPIOperationID
	pathParameters map[string]string
}

func (r *recordingExecutor) doOpenAPI(_ context.Context, id openAPIOperationID, pathParameters map[string]string, _ url.Values, _, _ any) error {
	r.id = id
	r.pathParameters = pathParameters
	return nil
}

// The generated client depends on the executor contract, not a concrete
// Connection, so a contract-only fake can drive it.
func TestGeneratedClientRunsThroughExecutorContract(t *testing.T) {
	executor := &recordingExecutor{}
	if _, err := (&OpenAPIClient{executor: executor}).GetService(context.Background(), "projects", "service-1"); err != nil {
		t.Fatal(err)
	}
	if executor.id != openAPIGetService || executor.pathParameters["serviceId"] != "service-1" {
		t.Fatalf("executor received %q %v", executor.id, executor.pathParameters)
	}
}

var _ openAPIOperationExecutor = (*Connection)(nil)
