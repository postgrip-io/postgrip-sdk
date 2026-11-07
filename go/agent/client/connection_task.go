package client

import (
	"context"
	"errors"
	"fmt"
	"strings"
)

// HistoryPageOptions selects one stable page of an Agent event history.
// Cursor is opaque and must be passed back unchanged. Limit defaults on the
// server and may be reduced there to honor the serialized response-size bound.
type HistoryPageOptions struct {
	Cursor string
	Limit  int64
}

// EnqueueTask enqueues a single task. Use TaskClient.Enqueue / ShellExec /
// ContainerExec / Noop helpers for ergonomic construction; this is the raw
// transport call. A ctx from WithIdempotencyKey sends its Idempotency-Key.
func (c *Connection) EnqueueTask(ctx context.Context, req EnqueueTaskRequest) (*Task, error) {
	if runtimeOnlyTaskType(req.Type) && !c.hasAgentRuntimeCredentials() {
		return nil, errors.New("postgrip-agent: workflow tasks can only be enqueued from a managed runtime; submit workflow.runtime to an agent pool")
	}
	out, err := c.OpenAPI().EnqueueTask(ctx, req)
	if err != nil {
		return nil, err
	}
	return &out, nil
}

func runtimeOnlyTaskType(taskType string) bool {
	switch strings.TrimSpace(taskType) {
	case TaskTypeTimer:
		return true
	}
	return strings.HasPrefix(taskType, TaskTypePrefixWorkflow) ||
		strings.HasPrefix(taskType, TaskTypePrefixActivity) ||
		strings.HasPrefix(taskType, TaskTypePrefixQuery) ||
		strings.HasPrefix(taskType, TaskTypePrefixUpdate)
}

// ListTasks returns tasks matching the optional filters.
func (c *Connection) ListTasks(ctx context.Context, params map[string]string) ([]Task, error) {
	var out []Task
	if err := c.doOpenAPI(ctx, openAPIListTasks, nil, queryValues(params), nil, &out); err != nil {
		return nil, err
	}
	return out, nil
}

// GetTask fetches a single task by id.
func (c *Connection) GetTask(ctx context.Context, taskID string) (*Task, error) {
	out, err := c.OpenAPI().GetTask(ctx, taskID)
	if err != nil {
		return nil, err
	}
	return &out, nil
}

// CancelTask ends a task that has not finished: it becomes failed, with
// result.failure.type "TaskCancelled" and reason, when not empty, in its
// error. A queued task is never leased; a leased task's Agent stops it on its
// next heartbeat. Cancelling a task already cancelled returns it unchanged,
// so a resend is safe. A task that already finished fails with 409
// TASK_TERMINAL, and a workflow's own task with 409 TASK_OWNED_BY_WORKFLOW:
// cancel its workflow instead.
func (c *Connection) CancelTask(ctx context.Context, taskID, reason string) (*Task, error) {
	out, err := c.OpenAPI().CancelTask(ctx, taskID, CancelTaskRequest{Reason: reason})
	if err != nil {
		return nil, err
	}
	return &out, nil
}

// GetTaskEventsPage returns one stable cursor page of the task event log.
func (c *Connection) GetTaskEventsPage(ctx context.Context, taskID string, opts HistoryPageOptions) (TaskEventPage, error) {
	query := OpenAPIListTaskEventsQuery{}
	if opts.Cursor != "" {
		query.Cursor = &opts.Cursor
	}
	if opts.Limit > 0 {
		query.Limit = &opts.Limit
	}
	return c.OpenAPI().ListTaskEvents(ctx, taskID, query)
}

// GetTaskEvents returns the full event log for a task by following stable,
// individually bounded response pages.
func (c *Connection) GetTaskEvents(ctx context.Context, taskID string) ([]TaskEvent, error) {
	return collectHistoryPages(ctx, func(ctx context.Context, opts HistoryPageOptions) ([]TaskEvent, *string, error) {
		page, err := c.GetTaskEventsPage(ctx, taskID, opts)
		return page.Items, page.NextCursor, err
	})
}

// WalkTaskEvents visits the task event log incrementally without assembling
// the complete history in SDK memory.
func (c *Connection) WalkTaskEvents(ctx context.Context, taskID string, visit func(TaskEvent) error) error {
	return walkHistoryPages(ctx, func(ctx context.Context, opts HistoryPageOptions) ([]TaskEvent, *string, error) {
		page, err := c.GetTaskEventsPage(ctx, taskID, opts)
		return page.Items, page.NextCursor, err
	}, visit)
}

func collectHistoryPages[T any](
	ctx context.Context,
	fetch func(context.Context, HistoryPageOptions) ([]T, *string, error),
) ([]T, error) {
	items := make([]T, 0)
	err := walkHistoryPages(ctx, fetch, func(item T) error {
		items = append(items, item)
		return nil
	})
	return items, err
}

func walkHistoryPages[T any](
	ctx context.Context,
	fetch func(context.Context, HistoryPageOptions) ([]T, *string, error),
	visit func(T) error,
) error {
	cursor := ""
	seen := make(map[string]struct{})
	for {
		items, next, err := fetch(ctx, HistoryPageOptions{Cursor: cursor, Limit: historyPageMaximumLimit})
		if err != nil {
			return err
		}
		for _, item := range items {
			if err := visit(item); err != nil {
				return err
			}
		}
		if next == nil {
			return nil
		}
		cursor = strings.TrimSpace(*next)
		if cursor == "" {
			return errors.New("postgrip-agent: history page returned an empty next cursor")
		}
		if _, exists := seen[cursor]; exists {
			return fmt.Errorf("postgrip-agent: history page repeated its next cursor")
		}
		seen[cursor] = struct{}{}
	}
}

const historyPageMaximumLimit int64 = 500

// PollTask leases the next task for the given namespace+queue for this
// agent. Returns nil task when the queue is empty (HTTP 204 / empty body
// equivalent). The agent_id is required by the runtime service.
func (c *Connection) PollTask(ctx context.Context, namespace, queue, agentID string) (*PollTaskResponse, error) {
	if err := c.ensureAgentSession(ctx, agentID, namespace, queue); err != nil {
		return nil, err
	}
	taskTypes := TaskTypePrefixWorkflow + "," + TaskTypePrefixActivity + "," + TaskTypePrefixQuery + "," + TaskTypePrefixUpdate
	out, err := c.OpenAPI().PollAgentTask(ctx, OpenAPIPollAgentTaskQuery{
		Namespace: &namespace,
		Queue:     queue,
		AgentId:   &agentID,
		TaskTypes: &taskTypes,
	})
	if err != nil {
		return nil, err
	}
	return &out, nil
}

// HeartbeatTask emits a heartbeat for a leased task. Workers call this on
// a timer derived from the task's lease_timeout_seconds.
func (c *Connection) HeartbeatTask(ctx context.Context, taskID, agentID string, ev *TaskEventInput) error {
	if err := c.ensureAgentSession(ctx, agentID, "", ""); err != nil {
		return err
	}
	body := OpenAPIHeartbeatAgentTaskRequestBody{Event: ev}
	_, err := c.OpenAPI().HeartbeatAgentTask(ctx, taskID, OpenAPIHeartbeatAgentTaskQuery{AgentId: &agentID}, body)
	return err
}

// EmitTaskEvent appends an arbitrary task event (progress/stdout/stderr/
// milestone). Used by the Worker dispatch path and exposed for activity
// helpers (Heartbeat, Milestone).
func (c *Connection) EmitTaskEvent(ctx context.Context, taskID, agentID string, ev TaskEventInput) error {
	if err := c.ensureAgentSession(ctx, agentID, "", ""); err != nil {
		return err
	}
	_, err := c.OpenAPI().AppendAgentTaskEvent(
		ctx, taskID, OpenAPIAppendAgentTaskEventQuery{AgentId: &agentID},
		OpenAPIAppendAgentTaskEventRequestBody{Event: ev},
	)
	return err
}

// CompleteTask marks a leased task succeeded with the given result.
func (c *Connection) CompleteTask(ctx context.Context, taskID, agentID string, result TaskResult) (*Task, error) {
	if err := c.ensureAgentSession(ctx, agentID, "", ""); err != nil {
		return nil, err
	}
	out, err := c.OpenAPI().CompleteAgentTask(
		ctx, taskID, OpenAPICompleteAgentTaskQuery{AgentId: &agentID},
		OpenAPICompleteAgentTaskRequestBody{Result: result},
	)
	if err != nil {
		return nil, err
	}
	return &out, nil
}

// FailTask marks a leased task failed with the given reason.
func (c *Connection) FailTask(ctx context.Context, taskID, agentID, reason string, result *TaskResult) (*Task, error) {
	if err := c.ensureAgentSession(ctx, agentID, "", ""); err != nil {
		return nil, err
	}
	out, err := c.OpenAPI().FailAgentTask(
		ctx, taskID, OpenAPIFailAgentTaskQuery{AgentId: &agentID},
		OpenAPIFailAgentTaskRequestBody{Error: reason, Result: result},
	)
	if err != nil {
		return nil, err
	}
	return &out, nil
}

// BlockTask marks a leased task blocked (waiting on a signal). Workflow
// runtime uses this when a workflow yields without a terminal result.
func (c *Connection) BlockTask(ctx context.Context, taskID, agentID, reason string) (*Task, error) {
	if err := c.ensureAgentSession(ctx, agentID, "", ""); err != nil {
		return nil, err
	}
	body := OpenAPIBlockAgentTaskRequestBody{Reason: reason}
	out, err := c.OpenAPI().BlockAgentTask(
		ctx, taskID, OpenAPIBlockAgentTaskQuery{AgentId: &agentID}, body,
	)
	if err != nil {
		return nil, err
	}
	return &out, nil
}
