package client

import (
	"time"

	"github.com/postgrip-io/postgrip-agent-sdks/go/agent/workflow"
)

// EnqueueInput is the SDK-side input to TaskClient.Enqueue. Payload may be
// any JSON-serializable value; the SDK marshals it for you.
type EnqueueInput struct {
	Namespace           string
	Queue               string
	Type                string
	Payload             any
	LeaseTimeoutSeconds int
	// IdempotencyKey, when set, makes the send safe to repeat for 24 hours: a
	// resend with the same key and input answers the first task instead of
	// enqueueing another. See WithIdempotencyKey.
	IdempotencyKey string
}

// ShellExecInput is the SDK-side input to TaskClient.ShellExec — same as
// the protocol.ShellExecPayload but with a Queue field for routing and
// JSON-tag-free naming.
type ShellExecInput struct {
	Queue          string
	Command        string
	Args           []string
	Env            map[string]string
	WorkingDir     string
	TimeoutSeconds int
}

// ContainerExecInput is the SDK-side input to TaskClient.ContainerExec.
type ContainerExecInput struct {
	Queue          string
	Image          string
	Command        string
	Args           []string
	Env            map[string]string
	WorkingDir     string
	PullPolicy     string
	TimeoutSeconds int
}

// WorkflowRuntimeInput enqueues a managed SDK workflow runtime onto an
// existing host-agent pool. The host agent leases the workflow.runtime task,
// delegates credentials, then launches Command with Args. If Image is set, the
// host agent asks its lifecycle helper to run the command in that image instead
// of requiring the agent image to contain the SDK runtime. The launched process
// should start a SDK Agent using the injected POSTGRIP_AGENT_* environment.
type WorkflowRuntimeInput struct {
	Namespace           string
	Queue               string
	RuntimeID           string
	Image               string
	Command             string
	Args                []string
	Env                 map[string]string
	WorkingDir          string
	PullPolicy          string
	RuntimeNamespace    string
	RuntimeQueue        string
	TimeoutSeconds      int
	LeaseTimeoutSeconds int
	// Isolation is the isolation floor the runtime requires, one of
	// IsolationTierContainer (the default) or IsolationTierMicroVM. It is a
	// floor, not an exact match: container work may be scheduled onto a
	// stronger tier, microvm work is never downgraded and only leases to
	// agents advertising that tier.
	//
	// Requires Image. The orchestrator rejects an isolation floor on a
	// command-only runtime, which would execute directly on the agent host
	// and honor no floor at all.
	Isolation string
}

// WorkflowStartOptions is the SDK-side input to WorkflowClient.Start. It
// carries the durable identity, queue routing, payload args, and the retry
// / memo / search-attribute metadata the runtime service persists.
//
// SearchAttributes names that start with `postgrip.` are reserved for
// attributes PostGrip sets; a start that sets one is refused with 400
// INVALID_REQUEST.
type WorkflowStartOptions struct {
	Namespace             string
	WorkflowID            string
	WorkflowIDReusePolicy workflow.IDReusePolicy
	TaskQueue             string
	Args                  []any
	LeaseTimeoutSeconds   int
	WorkflowRunTimeoutMs  int
	Retry                 *RetryPolicy
	Memo                  map[string]any
	SearchAttributes      map[string]any
	UI                    *WorkflowUIMetadata
}

// WorkflowUIMetadata is optional display metadata for PostGrip console
// workflow views. The SDK stores it in memo["postgrip.ui"], so existing
// runtime services persist it without requiring a protocol change.
type WorkflowUIMetadata struct {
	DisplayName string         `json:"displayName,omitempty"`
	Description string         `json:"description,omitempty"`
	Details     map[string]any `json:"details,omitempty"`
	Tags        []string       `json:"tags,omitempty"`
}

// SignalWithStartOptions is the SDK-side input to WorkflowClient.SignalWithStart.
type SignalWithStartOptions struct {
	WorkflowStartOptions
	SignalName string
	SignalArgs []any
	// IdempotencyKey, when set, makes the request safe to repeat for 24 hours:
	// a resend with the same key and options answers the first request's
	// result instead of signalling again or starting another run. See
	// WithIdempotencyKey.
	IdempotencyKey string
}

// ScheduleActionInput is accepted by ScheduleClient APIs for create/update;
// mirrors the TS/Python shape.
//
// SearchAttributes are copied to every run the schedule emits, and PostGrip
// adds `postgrip.scheduleId` with the schedule's id, so the runs can be listed
// with the `search.postgrip.scheduleId` filter. Names that start with
// `postgrip.` are reserved; setting one is refused with 400 INVALID_REQUEST.
type ScheduleActionInput struct {
	Namespace             string
	Queue                 string
	WorkflowType          string
	WorkflowID            string
	WorkflowIDReusePolicy workflow.IDReusePolicy
	RunTimeoutMs          int
	Retry                 *RetryPolicy
	Memo                  map[string]any
	SearchAttributes      map[string]any
	UI                    *WorkflowUIMetadata
	Args                  []any
}

// CreateScheduleInput is the SDK-side input to ScheduleClient.Create.
type CreateScheduleInput struct {
	ID            string
	Namespace     string
	OverlapPolicy string
	Spec          ScheduleSpec
	Action        ScheduleActionInput
}

// UpdateScheduleInput is the SDK-side input to ScheduleClient.Update; nil
// fields are treated as "no change" by the runtime service.
type UpdateScheduleInput struct {
	OverlapPolicy *string
	Spec          *ScheduleSpec
	Action        *ScheduleActionInput
}

// WorkflowExecutionDescription mirrors the TS WorkflowExecutionDescription
// returned by WorkflowHandle.Describe. SearchAttributes of a run a schedule
// emitted include the system attribute `postgrip.scheduleId`.
type WorkflowExecutionDescription struct {
	WorkflowID           string         `json:"workflowId"`
	RunID                string         `json:"runId,omitempty"`
	TaskID               string         `json:"taskId"`
	Namespace            string         `json:"namespace"`
	TaskQueue            string         `json:"taskQueue"`
	WorkflowType         string         `json:"workflowType"`
	Status               string         `json:"status"`
	Attempt              int            `json:"attempt,omitempty"`
	LeaseTimeoutSeconds  int            `json:"leaseTimeoutSeconds,omitempty"`
	WorkflowRunTimeoutMs int            `json:"workflowRunTimeoutMs,omitempty"`
	Retry                *RetryPolicy   `json:"retry,omitempty"`
	Memo                 map[string]any `json:"memo,omitempty"`
	SearchAttributes     map[string]any `json:"searchAttributes,omitempty"`
	Result               any            `json:"result,omitempty"`
	Error                string         `json:"error,omitempty"`
	StartedAt            time.Time      `json:"startedAt"`
	UpdatedAt            time.Time      `json:"updatedAt"`
}
