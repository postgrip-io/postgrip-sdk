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
	"sort"

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

// Owners maps a command event's task_id to the task that issued the command:
// the workflow task for body commands, or an update task. The Agent reads it
// from each command task's payload before replay; a command missing from the
// map belongs to the body.
type Owners map[string]string

// Replay walks a workflow's durable history. The body and each update entry
// have their own ordered cursor over the command events they own; a command
// must match the earliest unconsumed event of its executing owner.
// Mismatches raise a DeterminismError; cursor exhaustion returns (nil, nil)
// so the caller knows to schedule a fresh command and suspend.
type Replay struct {
	history []protocol.WorkflowHistoryEvent

	body    cursor
	owned   map[string]*cursor
	updates []Update

	// owner is the executing update task, or "" while the body runs. A
	// replayed handler already finished, so it never schedules new commands.
	owner     string
	ownerLive bool

	updateCursor int

	cancellationRequested bool
	determinismErr        *DeterminismError
}

type indexedEvent struct {
	event protocol.WorkflowHistoryEvent
	index int
}

// cursor is one owner's ordered position over its command events, with the
// count consumed of each kind for error messages.
type cursor struct {
	events     []indexedEvent
	next       int
	activities int
	timers     int
	children   int
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

// New builds a Replay from durable history and the command owners the Agent
// read for it. Worker.runWorkflow constructs one before each workflow body
// invocation so the body sees the same command results across replays.
func New(history []protocol.WorkflowHistoryEvent, owners Owners) *Replay {
	r := &Replay{history: history, owned: make(map[string]*cursor)}
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
	updateTasks := make(map[string]bool)
	for i := range history {
		switch ev := &history[i]; ev.Type {
		case EventWorkflowUpdateAccepted, EventWorkflowUpdateCompleted, EventWorkflowUpdateFailed:
			if ev.TaskID != "" {
				updateTasks[ev.TaskID] = true
			}
		}
	}
	for i := range history {
		ev := &history[i]
		switch ev.Type {
		case EventActivityTaskScheduled, EventTimerStarted, EventChildWorkflowStarted:
			event := indexedEvent{event: *ev, index: i}
			if owner := owners[ev.TaskID]; ev.TaskID != "" && updateTasks[owner] {
				if r.owned[owner] == nil {
					r.owned[owner] = &cursor{}
				}
				r.owned[owner].events = append(r.owned[owner].events, event)
				continue
			}
			r.body.events = append(r.body.events, event)
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
	// A legacy entry has no accepted event. It is positioned at its earliest
	// owned command so its handler replays through the commands it issued.
	for i := range r.updates {
		update := &r.updates[i]
		if accepted[update.TaskID] {
			continue
		}
		if owned := r.owned[update.TaskID]; owned != nil && owned.events[0].index < update.index {
			update.index = owned.events[0].index
		}
	}
	sort.SliceStable(r.updates, func(i, j int) bool { return r.updates[i].index < r.updates[j].index })
	return r
}

// OwnershipCandidates returns the task IDs of the command events that could
// belong to an update: those between an accepted update event and its terminal
// event, or the end of history while it is pending, and those before the
// terminal event of a legacy entry that has no accepted event. The Agent reads
// each one's owner before building a Replay.
func OwnershipCandidates(history []protocol.WorkflowHistoryEvent) []string {
	acceptedAt := make(map[string]int)
	terminalAt := make(map[string]int)
	for i := range history {
		ev := &history[i]
		if ev.TaskID == "" {
			continue
		}
		switch ev.Type {
		case EventWorkflowUpdateAccepted:
			if _, ok := acceptedAt[ev.TaskID]; !ok {
				acceptedAt[ev.TaskID] = i
			}
		case EventWorkflowUpdateCompleted, EventWorkflowUpdateFailed:
			if _, ok := terminalAt[ev.TaskID]; !ok {
				terminalAt[ev.TaskID] = i
			}
		}
	}
	inWindow := func(index int) bool {
		for taskID, terminal := range terminalAt {
			start, accepted := acceptedAt[taskID]
			if !accepted {
				start = -1
			}
			if index > start && index < terminal {
				return true
			}
		}
		for taskID, start := range acceptedAt {
			if _, done := terminalAt[taskID]; !done && index > start {
				return true
			}
		}
		return false
	}
	var candidates []string
	seen := make(map[string]bool)
	for i := range history {
		ev := &history[i]
		switch ev.Type {
		case EventActivityTaskScheduled, EventTimerStarted, EventChildWorkflowStarted:
			if ev.TaskID != "" && !seen[ev.TaskID] && inWindow(i) {
				seen[ev.TaskID] = true
				candidates = append(candidates, ev.TaskID)
			}
		}
	}
	return candidates
}

// EnterOwner makes the update task the executing owner until the returned
// function restores the previous one. A live owner schedules new commands
// once its recorded ones are consumed; a replayed owner already finished, so
// a further command is a determinism error.
func (r *Replay) EnterOwner(taskID string, live bool) func() {
	previous, previousLive := r.owner, r.ownerLive
	r.owner, r.ownerLive = taskID, live
	return func() { r.owner, r.ownerLive = previous, previousLive }
}

func (r *Replay) current() *cursor {
	if r.owner == "" {
		return &r.body
	}
	c := r.owned[r.owner]
	if c == nil {
		c = &cursor{}
		r.owned[r.owner] = c
	}
	return c
}

// CheckBodyConsumed is the completion check's leftover test: a body-owned
// command event left unconsumed when the workflow completes, continues as new
// or, in query replay, returns, is a recorded determinism error.
func (r *Replay) CheckBodyConsumed() error {
	return r.checkConsumed(&r.body, "workflow")
}

// CheckOwnerConsumed reports a replayed update handler that returned or raised
// with its own command events left unconsumed.
func (r *Replay) CheckOwnerConsumed(taskID string) error {
	c := r.owned[taskID]
	if c == nil {
		return nil
	}
	return r.checkConsumed(c, fmt.Sprintf("update %s handler", taskID))
}

func (r *Replay) checkConsumed(c *cursor, who string) error {
	if c.next >= len(c.events) {
		return nil
	}
	left := c.events[c.next]
	return r.fail(fmt.Sprintf("%s finished before replaying recorded command at history index %d: history=%q", who, left.index, left.event.Type))
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
	c := r.current()
	recorded, _ := ev.event.Attributes["activity_type"].(string)
	if recorded != "" && recorded != name {
		return nil, r.fail(fmt.Sprintf("activity command changed at index %d: history=%q replay=%q", c.activities, recorded, name))
	}
	c.activities++
	c.next++
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
	c := r.current()
	if recorded, ok := ev.event.Attributes["duration_ms"]; ok {
		recordedMs, ok := numberAsInt64(recorded)
		if ok && recordedMs != durationMs {
			return nil, r.fail(fmt.Sprintf("timer command changed at index %d: history=%dms replay=%dms", c.timers, recordedMs, durationMs))
		}
	}
	c.timers++
	c.next++
	return &ev.event, nil
}

// NextChild mirrors NextActivity for child workflows.
func (r *Replay) NextChild(workflowType string) (*protocol.WorkflowHistoryEvent, error) {
	ev, err := r.nextCommand(EventChildWorkflowStarted)
	if err != nil || ev == nil {
		return nil, err
	}
	c := r.current()
	recorded, _ := ev.event.Attributes["workflow_type"].(string)
	if recorded != "" && recorded != workflowType {
		return nil, r.fail(fmt.Sprintf("child workflow command changed at index %d: history=%q replay=%q", c.children, recorded, workflowType))
	}
	c.children++
	c.next++
	return &ev.event, nil
}

// nextCommand returns the executing owner's earliest unconsumed command event
// without consuming it. It returns (nil, nil) when no recorded command remains,
// and a DeterminismError when the earliest one is not of the requested kind;
// that covers reordering and a kind whose events are exhausted while others
// remain. A replayed update handler with no recorded command left has already
// finished, so a further command is a DeterminismError, never a new one.
func (r *Replay) nextCommand(kind string) (*indexedEvent, error) {
	c := r.current()
	if c.next >= len(c.events) {
		if r.owner != "" && !r.ownerLive {
			return nil, r.fail(fmt.Sprintf("update %s handler issued %q after its recorded commands", r.owner, kind))
		}
		return nil, nil
	}
	ev := &c.events[c.next]
	if ev.event.Type != kind {
		return nil, r.fail(fmt.Sprintf("command changed at history index %d: history=%q replay=%q", ev.index, ev.event.Type, kind))
	}
	return ev, nil
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

// earliestBodyCommand returns the history index of the earliest unconsumed
// body-owned command event; update boundaries apply only before it.
func (r *Replay) earliestBodyCommand() (int, bool) {
	if r.body.next >= len(r.body.events) {
		return 0, false
	}
	return r.body.events[r.body.next].index, true
}

// NextUpdateBeforeCommand returns the next update boundary when it precedes
// the earliest unconsumed body-owned command event, or when none remains. The
// caller must call ConsumeUpdate before invoking its handler, which consumes
// its own command events under EnterOwner.
func (r *Replay) NextUpdateBeforeCommand() (*Update, bool) {
	if r == nil || r.updateCursor >= len(r.updates) {
		return nil, false
	}
	update := &r.updates[r.updateCursor]
	commandIndex, hasCommand := r.earliestBodyCommand()
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
