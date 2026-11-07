package worker

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"github.com/postgrip-io/postgrip-agent-sdks/go/agent/failure"
)

// errTaskStopped is the cause of a task context PostGrip stopped: a heartbeat
// answered that the task was cancelled (cancelTask), is otherwise terminal, or
// is no longer leased to this Agent. The task is already settled on the
// server, so the Worker reports nothing for it.
var errTaskStopped = errors.New("postgrip-agent: task stopped by PostGrip")

// taskCancelledCode is the error code of a mutation of a task cancelled with
// cancelTask. Its message still says the task is terminal.
const taskCancelledCode = "TASK_CANCELLED"

// isTerminalTaskMutation reports whether a task mutation failed because the
// task is already terminal or no longer leased to this Agent. The server
// answers both with a 409 whose envelope message names the condition, and a
// cancelled task with the code TASK_CANCELLED. It matches the TypeScript
// isTerminalTaskMutation and Python is_terminal_task_mutation.
func isTerminalTaskMutation(err error) bool {
	var sdkErr *failure.SDKError
	if !errors.As(err, &sdkErr) || sdkErr.StatusCode != http.StatusConflict {
		return false
	}
	if sdkErr.Code == taskCancelledCode {
		return true
	}
	var envelope struct {
		Message string `json:"message"`
	}
	if json.Unmarshal(sdkErr.ResponseBody, &envelope) != nil {
		return false
	}
	return strings.Contains(envelope.Message, "terminal") || strings.Contains(envelope.Message, "not leased")
}
