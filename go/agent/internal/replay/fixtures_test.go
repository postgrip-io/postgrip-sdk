package replay

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"sort"
	"testing"

	"github.com/postgrip-io/postgrip-agent-sdks/go/protocol"
)

type replayFixture struct {
	History []protocol.WorkflowHistoryEvent `json:"history"`
	Steps   []struct {
		Command      string `json:"command"`
		Name         string `json:"name"`
		DurationMS   int64  `json:"duration_ms"`
		WorkflowType string `json:"workflow_type"`
		Expect       string `json:"expect"`
	} `json:"steps"`
}

// The shared conformance fixtures in test/fixtures/replay run unchanged in
// every SDK language.
func TestSharedReplayConformanceFixtures(t *testing.T) {
	directory := filepath.Join("..", "..", "..", "..", "test", "fixtures", "replay")
	files, err := filepath.Glob(filepath.Join(directory, "*.json"))
	if err != nil || len(files) == 0 {
		t.Fatalf("no replay fixtures in %s: %v", directory, err)
	}
	sort.Strings(files)
	for _, file := range files {
		t.Run(filepath.Base(file), func(t *testing.T) {
			raw, err := os.ReadFile(file)
			if err != nil {
				t.Fatal(err)
			}
			var fixture replayFixture
			if err := json.Unmarshal(raw, &fixture); err != nil {
				t.Fatal(err)
			}
			r := New(fixture.History)
			expectsViolation := false
			for index, step := range fixture.Steps {
				var event *protocol.WorkflowHistoryEvent
				switch step.Command {
				case "activity":
					event, err = r.NextActivity(step.Name)
				case "timer":
					event, err = r.NextTimer(step.DurationMS)
				case "child":
					event, err = r.NextChild(step.WorkflowType)
				default:
					t.Fatalf("step %d: unknown command %q", index, step.Command)
				}
				outcome := "new"
				var det *DeterminismError
				switch {
				case errors.As(err, &det):
					outcome = "nondeterministic"
				case err != nil:
					t.Fatalf("step %d: %v", index, err)
				case event != nil:
					outcome = "replay"
				}
				if outcome != step.Expect {
					t.Fatalf("step %d (%s): outcome %q, want %q", index, step.Command, outcome, step.Expect)
				}
				expectsViolation = expectsViolation || step.Expect == "nondeterministic"
			}
			if (r.DeterminismErr() != nil) != expectsViolation {
				t.Fatalf("recorded determinism error = %v, want recorded=%v", r.DeterminismErr(), expectsViolation)
			}
		})
	}
}
