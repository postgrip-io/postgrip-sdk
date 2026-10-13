// Package replay walks a workflow's durable history and serves persisted
// command results back to the workflow body so it can replay deterministically.
//
// The package is internal: it returns sentinel errors (ErrCancellationRequested,
// DeterminismError) that the SDK translates into the public CancelledFailure
// and WorkflowDeterminismViolation ApplicationFailure at the call boundary.
// This keeps the replay engine free of SDK error types and avoids an import
// cycle with the root sdk package.
package replay

import (
	"errors"
	"fmt"

	"github.com/postgrip-io/postgrip-agent-sdks/go/protocol"
)

// History event type strings the runtime service writes. Mirrors the
// strings the TypeScript SDK matches on (typescript/src/agent/agent.ts).
// Exported so SDK-side integration tests can construct realistic histories
// without copy-pasting the wire strings.
const (
	EventActivityTaskScheduled       = "ActivityTaskScheduled"
	EventActivityTaskRetryScheduled  = "ActivityTaskRetryScheduled"
	EventActivityTaskCanceled        = "ActivityTaskCanceled"
	EventTimerStarted                = "TimerStarted"
	EventTimerFired                  = "TimerFired"
	EventChildWorkflowStarted        = "ChildWorkflowExecutionStarted"
	EventWorkflowSignaled            = "WorkflowSignaled"
	EventWorkflowUpdateAccepted      = "WorkflowUpdateAccepted"
	EventWorkflowUpdateCompleted     = "WorkflowUpdateCompleted"
	EventWorkflowUpdateFailed        = "WorkflowUpdateFailed"
	EventWorkflowCancellationRequest = "WorkflowCancellationRequested"
)

// ErrCancellationRequested is the sentinel returned by Replay.CheckCancellation
// when the workflow's history contains a WorkflowCancellationRequested event.
// The SDK translates it to a CancelledFailure at the call boundary.
var ErrCancellationRequested = errors.New("workflow cancellation requested")

// DeterminismError is returned by Replay.NextActivity / NextTimer / NextChild
// when the workflow body's next command disagrees with the recorded history.
// The SDK wraps this in a non-retryable ApplicationFailure tagged
// "WorkflowDeterminismViolation" at the call boundary.
type DeterminismError struct {
	Message string
}

func (e *DeterminismError) Error() string { return e.Message }

// Replay walks a workflow's durable history. Each command type (activity,
// timer, child workflow) has its own cursor: every call from the workflow
// advances the cursor by one event in that type's filtered slice. Mismatches
// raise a DeterminismError; cursor exhaustion returns (nil, nil) so the
// caller knows to schedule a fresh command and suspend.
type Replay struct {
	history []protocol.WorkflowHistoryEvent

	activities []indexedEvent
	timers     []indexedEvent
	children   []indexedEvent
	updates    []Update

	activityCursor int
	timerCursor    int
	childCursor    int
	updateCursor   int

	cancellationRequested bool
	determinismErr        *DeterminismError
}

type indexedEvent struct {
	event protocol.WorkflowHistoryEvent
	index int
}

// Update is an accepted workflow update in its durable-history position.
// Completed is true only when the same update task has a completion event.
// Legacy histories that contain only a completion event are positioned at
// that event so they remain replayable without moving them ahead of commands.
type Update struct {
	TaskID    string
	Name      string
	Args      []any
	Completed bool
	Failed    bool
	index     int
}

// New builds a Replay from durable history. Worker.runWorkflow constructs
// one before each workflow body invocation so the body sees the same
// command results across replays.
func New(history []protocol.WorkflowHistoryEvent) *Replay {
	r := &Replay{history: history}
	completed := make(map[string]bool)
	failed := make(map[string]bool)
	accepted := make(map[string]bool)
	for i := range history {
		ev := &history[i]
		if ev.Type == EventWorkflowUpdateCompleted && ev.TaskID != "" {
			completed[ev.TaskID] = true
		}
		if ev.Type == EventWorkflowUpdateFailed && ev.TaskID != "" {
			failed[ev.TaskID] = true
		}
		if ev.Type == EventWorkflowUpdateAccepted && ev.TaskID != "" {
			accepted[ev.TaskID] = true
		}
	}
	for i := range history {
		ev := &history[i]
		switch ev.Type {
		case EventActivityTaskScheduled:
			r.activities = append(r.activities, indexedEvent{event: *ev, index: i})
		case EventTimerStarted:
			r.timers = append(r.timers, indexedEvent{event: *ev, index: i})
		case EventChildWorkflowStarted:
			r.children = append(r.children, indexedEvent{event: *ev, index: i})
		case EventWorkflowUpdateAccepted:
			update := updateFromEvent(*ev, i, completed[ev.TaskID])
			update.Failed = failed[ev.TaskID]
			r.updates = append(r.updates, update)
		case EventWorkflowUpdateCompleted:
			// Older runtimes did not always persist the accepted event. Keep
			// those histories replayable, but use the completion position.
			if ev.TaskID == "" || !accepted[ev.TaskID] {
				r.updates = append(r.updates, updateFromEvent(*ev, i, true))
			}
		case EventWorkflowUpdateFailed:
			if ev.TaskID == "" || !accepted[ev.TaskID] {
				update := updateFromEvent(*ev, i, false)
				update.Failed = true
				r.updates = append(r.updates, update)
			}
		case EventWorkflowCancellationRequest:
			r.cancellationRequested = true
		}
	}
	return r
}

func updateFromEvent(ev protocol.WorkflowHistoryEvent, index int, completed bool) Update {
	name, _ := ev.Attributes["update_name"].(string)
	if name == "" {
		name, _ = ev.Attributes["name"].(string)
	}
	args, _ := ev.Attributes["args"].([]any)
	return Update{TaskID: ev.TaskID, Name: name, Args: args, Completed: completed, index: index}
}

// NextActivity returns the next ActivityTaskScheduled event when it is the
// earliest unconsumed command and its recorded activity_type matches name.
// Returns (nil, nil) when no recorded command remains, so the caller schedules
// a new one; returns a DeterminismError when history disagrees.
func (r *Replay) NextActivity(name string) (*protocol.WorkflowHistoryEvent, error) {
	ev, err := r.nextCommand(EventActivityTaskScheduled)
	if err != nil || ev == nil {
		return nil, err
	}
	recorded, _ := ev.event.Attributes["activity_type"].(string)
	if recorded != "" && recorded != name {
		return nil, r.fail(fmt.Sprintf("activity command changed at index %d: history=%q replay=%q", r.activityCursor, recorded, name))
	}
	r.activityCursor++
	return &ev.event, nil
}

// NextTimer mirrors NextActivity for timers. duration_ms in the recorded
// event must match what the workflow asked for (rounded to int) — workflow
// code that varies sleep duration across replays is non-deterministic.
func (r *Replay) NextTimer(durationMs int64) (*protocol.WorkflowHistoryEvent, error) {
	ev, err := r.nextCommand(EventTimerStarted)
	if err != nil || ev == nil {
		return nil, err
	}
	if recorded, ok := ev.event.Attributes["duration_ms"]; ok {
		recordedMs, ok := numberAsInt64(recorded)
		if ok && recordedMs != durationMs {
			return nil, r.fail(fmt.Sprintf("timer command changed at index %d: history=%dms replay=%dms", r.timerCursor, recordedMs, durationMs))
		}
	}
	r.timerCursor++
	return &ev.event, nil
}

// NextChild mirrors NextActivity for child workflows.
func (r *Replay) NextChild(workflowType string) (*protocol.WorkflowHistoryEvent, error) {
	ev, err := r.nextCommand(EventChildWorkflowStarted)
	if err != nil || ev == nil {
		return nil, err
	}
	recorded, _ := ev.event.Attributes["workflow_type"].(string)
	if recorded != "" && recorded != workflowType {
		return nil, r.fail(fmt.Sprintf("child workflow command changed at index %d: history=%q replay=%q", r.childCursor, recorded, workflowType))
	}
	r.childCursor++
	return &ev.event, nil
}

// nextCommand returns the earliest unconsumed command event without consuming
// it. It returns (nil, nil) when no recorded command remains, and a
// DeterminismError when the earliest one is not of the requested kind; that
// covers reordering and a kind whose events are exhausted while others remain.
func (r *Replay) nextCommand(kind string) (*indexedEvent, error) {
	index, recordedKind, ok := r.earliestCommand()
	if !ok {
		return nil, nil
	}
	if recordedKind != kind {
		return nil, r.fail(fmt.Sprintf("command changed at history index %d: history=%q replay=%q", index, recordedKind, kind))
	}
	switch kind {
	case EventActivityTaskScheduled:
		return &r.activities[r.activityCursor], nil
	case EventTimerStarted:
		return &r.timers[r.timerCursor], nil
	default:
		return &r.children[r.childCursor], nil
	}
}

// fail records the first determinism error. Once recorded, the worker fails
// the workflow task with it whatever the workflow code does afterwards.
func (r *Replay) fail(message string) error {
	err := &DeterminismError{Message: message}
	if r.determinismErr == nil {
		r.determinismErr = err
	}
	return err
}

// DeterminismErr returns the first determinism error this replay raised, if
// any, so a caught error still fails the workflow task.
func (r *Replay) DeterminismErr() error {
	if r == nil || r.determinismErr == nil {
		return nil
	}
	return r.determinismErr
}

func (r *Replay) earliestCommand() (int, string, bool) {
	index := len(r.history)
	typeName := ""
	if r.activityCursor < len(r.activities) && r.activities[r.activityCursor].index < index {
		index = r.activities[r.activityCursor].index
		typeName = EventActivityTaskScheduled
	}
	if r.timerCursor < len(r.timers) && r.timers[r.timerCursor].index < index {
		index = r.timers[r.timerCursor].index
		typeName = EventTimerStarted
	}
	if r.childCursor < len(r.children) && r.children[r.childCursor].index < index {
		index = r.children[r.childCursor].index
		typeName = EventChildWorkflowStarted
	}
	return index, typeName, typeName != ""
}

// NextUpdateBeforeCommand returns the next accepted update when it precedes
// the next unconsumed durable command. The caller must call ConsumeUpdate
// before invoking its handler. This lets handler commands consume the command
// events immediately following that update instead of letting the workflow
// body consume them out of order.
func (r *Replay) NextUpdateBeforeCommand() (*Update, bool) {
	if r == nil || r.updateCursor >= len(r.updates) {
		return nil, false
	}
	update := &r.updates[r.updateCursor]
	commandIndex, _, hasCommand := r.earliestCommand()
	if hasCommand && update.index > commandIndex {
		return nil, false
	}
	return update, true
}

// ConsumeUpdate advances the ordered update cursor. It returns false when
// taskID is non-empty and does not identify the next update boundary.
func (r *Replay) ConsumeUpdate(taskID string) bool {
	if r == nil || r.updateCursor >= len(r.updates) {
		return false
	}
	if taskID != "" && r.updates[r.updateCursor].TaskID != taskID {
		return false
	}
	r.updateCursor++
	return true
}

// IsTimerFired reports whether a TimerFired event keyed on the same task_id
// as the supplied TimerStarted event exists in history.
func (r *Replay) IsTimerFired(timerStarted *protocol.WorkflowHistoryEvent) bool {
	if timerStarted == nil || timerStarted.TaskID == "" {
		return false
	}
	for i := range r.history {
		ev := &r.history[i]
		if ev.Type == EventTimerFired && ev.TaskID == timerStarted.TaskID {
			return true
		}
	}
	return false
}

// IsActivityCanceled reports whether the activity scheduled at this index
// was cancelled before completing.
func (r *Replay) IsActivityCanceled(scheduled *protocol.WorkflowHistoryEvent) bool {
	if scheduled == nil || scheduled.TaskID == "" {
		return false
	}
	for i := range r.history {
		ev := &r.history[i]
		if ev.Type == EventActivityTaskCanceled && ev.TaskID == scheduled.TaskID {
			return true
		}
	}
	return false
}

// HasActivityRetryScheduled reports whether the runtime queued a retry for
// the failed activity. Workflow code that wants a clean retry semantic
// recurses into ExecuteActivity when this returns true.
func (r *Replay) HasActivityRetryScheduled(scheduled *protocol.WorkflowHistoryEvent) bool {
	if scheduled == nil || scheduled.TaskID == "" {
		return false
	}
	for i := range r.history {
		ev := &r.history[i]
		if ev.Type != EventActivityTaskRetryScheduled {
			continue
		}
		prev, _ := ev.Attributes["previous_task"].(string)
		if prev == scheduled.TaskID {
			return true
		}
	}
	return false
}

// CheckCancellation returns ErrCancellationRequested if the workflow has a
// recorded WorkflowCancellationRequested event. Workflow context methods
// call this before scheduling new commands so cancellation propagates
// promptly during replay.
func (r *Replay) CheckCancellation() error {
	if r == nil || !r.cancellationRequested {
		return nil
	}
	return ErrCancellationRequested
}

// SignalsByName returns the ordered args lists for every WorkflowSignaled
// event whose recorded name matches. workflowContext.GetSignalChannel uses
// this to seed each replay's signal channel with the durable signal stream.
func (r *Replay) SignalsByName(name string) [][]any {
	var out [][]any
	for i := range r.history {
		ev := &r.history[i]
		if ev.Type != EventWorkflowSignaled {
			continue
		}
		recordedName, _ := ev.Attributes["signal_name"].(string)
		if recordedName == "" {
			recordedName, _ = ev.Attributes["name"].(string)
		}
		if recordedName != name {
			continue
		}
		args, _ := ev.Attributes["args"].([]any)
		out = append(out, args)
	}
	return out
}

// numberAsInt64 normalizes JSON's float64 / int / int64 numeric decodings
// down to int64. Necessary because Attributes is map[string]any and JSON
// decodes numeric fields as float64 by default.
func numberAsInt64(v any) (int64, bool) {
	switch t := v.(type) {
	case int64:
		return t, true
	case int:
		return int64(t), true
	case int32:
		return int64(t), true
	case float64:
		return int64(t), true
	case float32:
		return int64(t), true
	}
	return 0, false
}
