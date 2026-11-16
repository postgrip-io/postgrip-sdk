package worker

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"

	"github.com/postgrip-io/postgrip-agent-sdks/go/agent/client"
	"github.com/postgrip-io/postgrip-agent-sdks/go/agent/workflow"
)

// continueWorkflow coordinates the existing enqueue and completion operations.
// They are separate requests, not an atomic server-side continuation primitive.
func (w *Worker) continueWorkflow(ctx context.Context, task *client.Task, opts workflow.ContinueAsNewOptions, result *client.TaskResult) error {
	_, currentWorkflowID, err := decodeWorkflowPayload(task)
	if err != nil {
		return err
	}
	digest := sha256.Sum256([]byte(task.ID))
	key := "continue-" + hex.EncodeToString(digest[:])
	workflowID := opts.WorkflowID
	if workflowID == "" {
		workflowID = key
	}
	args, err := json.Marshal(opts.Args)
	if err != nil {
		return fmt.Errorf("encode continuation args: %w", err)
	}
	payload, err := json.Marshal(client.WorkflowPayload{
		Namespace: task.Namespace, WorkflowType: opts.WorkflowType,
		WorkflowID: workflowID, ContinuedFromWorkflowID: currentWorkflowID,
		RunTimeoutMs: int64(opts.WorkflowRunTimeoutMs), RetryPolicy: opts.Retry,
		Args: args,
	})
	if err != nil {
		return fmt.Errorf("encode continuation payload: %w", err)
	}
	nextTask, err := w.opts.Connection.EnqueueTask(client.WithIdempotencyKey(ctx, key), client.EnqueueTaskRequest{
		Namespace: task.Namespace, Queue: opts.TaskQueue,
		Type: client.TaskTypePrefixWorkflow + opts.WorkflowType, Payload: payload,
		LeaseTimeoutSeconds: opts.LeaseTimeoutSeconds,
	})
	if err != nil {
		return fmt.Errorf("enqueue continuation: %w", err)
	}
	result.ContinueAsNew = &client.ContinueAsNewResult{
		WorkflowID: workflowID, WorkflowType: opts.WorkflowType,
		TaskQueue: opts.TaskQueue, TaskID: nextTask.ID,
	}
	_, err = w.opts.Connection.CompleteTask(ctx, task.ID, w.opts.AgentID, *result)
	return err
}
