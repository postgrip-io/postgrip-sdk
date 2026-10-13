package replay

import (
	"errors"
	"testing"

	"github.com/postgrip-io/postgrip-agent-sdks/go/protocol"
)

func TestNewSplitsByType(t *testing.T) {
	t.Parallel()
	r := newBody([]protocol.WorkflowHistoryEvent{
		{ID: "1", Type: EventActivityTaskScheduled, TaskID: "act-1", Attributes: map[string]any{"activity_type": "Greet"}},
		{ID: "2", Type: EventTimerStarted, TaskID: "tmr-1", Attributes: map[string]any{"duration_ms": float64(1000)}},
		{ID: "3", Type: EventTimerFired, TaskID: "tmr-1"},
		{ID: "4", Type: EventChildWorkflowStarted, TaskID: "wf-child-1", Attributes: map[string]any{"workflow_type": "Sub"}},
		{ID: "5", Type: EventWorkflowCancellationRequest},
		{ID: "6", Type: EventWorkflowSignaled, Attributes: map[string]any{"name": "ping", "args": []any{1}}},
		{ID: "7", Type: EventWorkflowSignaled, Attributes: map[string]any{"name": "ping", "args": []any{2}}},
		{ID: "8", Type: EventWorkflowSignaled, Attributes: map[string]any{"name": "other", "args": []any{}}},
		{ID: "9", Type: EventWorkflowUpdateAccepted, TaskID: "update-1", Attributes: map[string]any{"update_name": "rename", "args": []any{"Grace"}}},
		{ID: "10", Type: EventWorkflowUpdateCompleted, TaskID: "update-1", Attributes: map[string]any{"update_name": "rename", "args": []any{"Grace"}}},
	})
	if len(r.body.events) != 3 {
		t.Fatalf("body command events = %d, want activity, timer and child", len(r.body.events))
	}
	if !r.cancellationRequested {
		t.Fatal("cancellation flag not set")
	}
	pings := r.SignalsByName("ping")
	if len(pings) != 2 {
		t.Fatalf("ping signals = %d, want 2", len(pings))
	}
	if pings[0][0].(int) != 1 || pings[1][0].(int) != 2 {
		t.Fatalf("signal args order wrong: %#v", pings)
	}
	_, _ = r.NextActivity("Greet")
	_, _ = r.NextTimer(1000)
	_, _ = r.NextChild("Sub")
	update, ok := r.NextUpdateBeforeCommand()
	if !ok || update.Name != "rename" || !update.Completed || update.Args[0] != "Grace" {
		t.Fatalf("completed update = %#v, ok=%v, want rename/Grace", update, ok)
	}
}

func TestUpdateWaitsForEarlierCommand(t *testing.T) {
	t.Parallel()
	r := newBody([]protocol.WorkflowHistoryEvent{
		{Type: EventTimerStarted, TaskID: "timer-1", Attributes: map[string]any{"duration_ms": float64(1000)}},
		{Type: EventTimerFired, TaskID: "timer-1"},
		{Type: EventWorkflowUpdateAccepted, TaskID: "update-1", Attributes: map[string]any{"update_name": "rename", "args": []any{"Grace"}}},
		{Type: EventWorkflowUpdateCompleted, TaskID: "update-1", Attributes: map[string]any{"update_name": "rename", "args": []any{"Grace"}}},
	})
	if update, ok := r.NextUpdateBeforeCommand(); ok {
		t.Fatalf("update advanced ahead of earlier command: %#v", update)
	}
	if _, err := r.NextTimer(1000); err != nil {
		t.Fatalf("NextTimer: %v", err)
	}
	update, ok := r.NextUpdateBeforeCommand()
	if !ok || update.TaskID != "update-1" || !update.Completed {
		t.Fatalf("update after command = %#v, ok=%v", update, ok)
	}
}

func TestSignalsByNameAcceptsCanonicalSignalName(t *testing.T) {
	t.Parallel()
	r := newBody([]protocol.WorkflowHistoryEvent{{
		Type:       EventWorkflowSignaled,
		Attributes: map[string]any{"signal_name": "ready", "args": []any{"Ada"}},
	}})
	got := r.SignalsByName("ready")
	if len(got) != 1 || got[0][0] != "Ada" {
		t.Fatalf("SignalsByName = %#v, want Ada", got)
	}
}

func TestNextActivityAdvancesCursorAndDetectsDeterminism(t *testing.T) {
	t.Parallel()
	r := newBody([]protocol.WorkflowHistoryEvent{
		{Type: EventActivityTaskScheduled, TaskID: "act-1", Attributes: map[string]any{"activity_type": "Greet"}},
		{Type: EventActivityTaskScheduled, TaskID: "act-2", Attributes: map[string]any{"activity_type": "Farewell"}},
	})
	first, err := r.NextActivity("Greet")
	if err != nil || first == nil || first.TaskID != "act-1" {
		t.Fatalf("first NextActivity = %+v, err=%v", first, err)
	}
	// Determinism violation: workflow asks for a different activity than
	// what's recorded next.
	_, err = r.NextActivity("Whoops")
	if err == nil {
		t.Fatal("expected determinism violation on mismatched activity")
	}
	var det *DeterminismError
	if !errors.As(err, &det) {
		t.Fatalf("expected DeterminismError, got %T: %v", err, err)
	}
	// A mismatch leaves the recorded event unconsumed and is recorded, so a
	// caught violation still fails the task.
	if !errors.Is(r.DeterminismErr(), err) {
		t.Fatalf("DeterminismErr = %v, want the first violation %v", r.DeterminismErr(), err)
	}
	if next, err := r.NextActivity("Farewell"); err != nil || next == nil || next.TaskID != "act-2" {
		t.Fatalf("NextActivity after a mismatch = %+v, err=%v; want the unconsumed act-2", next, err)
	}
	if next, err := r.NextActivity("Anything"); err != nil || next != nil {
		t.Fatalf("NextActivity past end = %+v, err=%v", next, err)
	}
}

func TestNextTimerChecksDuration(t *testing.T) {
	t.Parallel()
	r := newBody([]protocol.WorkflowHistoryEvent{
		{Type: EventTimerStarted, TaskID: "tmr-1", Attributes: map[string]any{"duration_ms": float64(2500)}},
	})
	if _, err := r.NextTimer(2000); err == nil {
		t.Fatal("expected determinism violation when timer duration changes")
	}
	// A mismatch leaves the event unconsumed.
	if ev, err := r.NextTimer(2500); err != nil || ev == nil || ev.TaskID != "tmr-1" {
		t.Fatalf("NextTimer happy = %+v, err=%v", ev, err)
	}
}

func TestIsTimerFired(t *testing.T) {
	t.Parallel()
	r := newBody([]protocol.WorkflowHistoryEvent{
		{Type: EventTimerStarted, TaskID: "tmr-1", Attributes: map[string]any{"duration_ms": float64(1000)}},
		{Type: EventTimerFired, TaskID: "tmr-1"},
		{Type: EventTimerStarted, TaskID: "tmr-2", Attributes: map[string]any{"duration_ms": float64(1000)}},
	})
	first, _ := r.NextTimer(1000)
	if !r.IsTimerFired(first) {
		t.Fatal("expected first timer to be fired")
	}
	second, _ := r.NextTimer(1000)
	if r.IsTimerFired(second) {
		t.Fatal("expected second timer to still be pending")
	}
}

func TestCheckCancellationReturnsSentinel(t *testing.T) {
	t.Parallel()
	r := newBody([]protocol.WorkflowHistoryEvent{
		{Type: EventWorkflowCancellationRequest},
	})
	if err := r.CheckCancellation(); !errors.Is(err, ErrCancellationRequested) {
		t.Fatalf("CheckCancellation = %v, want ErrCancellationRequested", err)
	}
	r2 := newBody(nil)
	if err := r2.CheckCancellation(); err != nil {
		t.Fatalf("CheckCancellation on empty = %v, want nil", err)
	}
}

func TestNumberAsInt64HandlesJSONShapes(t *testing.T) {
	t.Parallel()
	cases := []struct {
		in   any
		want int64
		ok   bool
	}{
		{int(7), 7, true},
		{int64(8), 8, true},
		{float64(9), 9, true},
		{float32(10.7), 10, true},
		{"11", 0, false},
	}
	for _, c := range cases {
		got, ok := numberAsInt64(c.in)
		if ok != c.ok || got != c.want {
			t.Fatalf("numberAsInt64(%v) = %d,%v want %d,%v", c.in, got, ok, c.want, c.ok)
		}
	}
}

// newBody builds a Replay whose commands all belong to the workflow body.
func newBody(history []protocol.WorkflowHistoryEvent) *Replay {
	return New(history, nil)
}

func ownershipHistory() []protocol.WorkflowHistoryEvent {
	return []protocol.WorkflowHistoryEvent{
		{Type: EventActivityTaskScheduled, TaskID: "before-any-update"},
		{Type: EventWorkflowUpdateAccepted, TaskID: "update-1"},
		{Type: EventTimerStarted, TaskID: "inside-update-1"},
		{Type: EventWorkflowUpdateCompleted, TaskID: "update-1"},
		{Type: EventChildWorkflowStarted, TaskID: "between-updates"},
		{Type: EventWorkflowUpdateAccepted, TaskID: "update-2"},
		{Type: EventActivityTaskScheduled, TaskID: "while-update-2-pending"},
	}
}

// Only commands inside an update's window can belong to an update.
func TestOwnershipCandidatesCoverUpdateWindows(t *testing.T) {
	t.Parallel()
	got := OwnershipCandidates(ownershipHistory())
	want := []string{"inside-update-1", "while-update-2-pending"}
	if len(got) != len(want) || got[0] != want[0] || got[1] != want[1] {
		t.Fatalf("candidates = %v, want %v", got, want)
	}
	legacy := OwnershipCandidates([]protocol.WorkflowHistoryEvent{
		{Type: EventActivityTaskScheduled, TaskID: "before-legacy"},
		{Type: EventWorkflowUpdateCompleted, TaskID: "legacy-1"},
		{Type: EventActivityTaskScheduled, TaskID: "after-legacy"},
	})
	if len(legacy) != 1 || legacy[0] != "before-legacy" {
		t.Fatalf("legacy candidates = %v, want [before-legacy]", legacy)
	}
}

// A legacy entry with no accepted event is positioned at its earliest owned
// command, so it applies before a later body command.
func TestLegacyUpdatePositionedAtItsEarliestOwnedCommand(t *testing.T) {
	t.Parallel()
	r := New([]protocol.WorkflowHistoryEvent{
		{Type: EventActivityTaskScheduled, TaskID: "act-update", Attributes: map[string]any{"activity_type": "Validate"}},
		{Type: EventActivityTaskScheduled, TaskID: "act-body", Attributes: map[string]any{"activity_type": "Greet"}},
		{Type: EventWorkflowUpdateCompleted, TaskID: "legacy-1", Attributes: map[string]any{"update_name": "approve"}},
	}, Owners{"act-update": "legacy-1", "act-body": "wf-task"})
	update, ok := r.NextUpdateBeforeCommand()
	if !ok || update.TaskID != "legacy-1" {
		t.Fatalf("next update = %#v, %v; want legacy-1 before the body's Greet", update, ok)
	}
}
