package transport

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
)

// APIError is the decoded common error envelope. Planes convert it into their
// own distinct public error types, which own the default error text.
type APIError struct {
	StatusCode int
	Code       string
	Message    string
	RequestID  string
	Details    map[string]any
	RetryAfter time.Duration
}

// Error returns text without server-provided content. Plane error types
// replace it with their own formatter.
func (e *APIError) Error() string {
	if e == nil {
		return ""
	}
	return fmt.Sprintf("postgrip: HTTP %d %s", e.StatusCode, http.StatusText(e.StatusCode))
}

// errorEnvelope mirrors the common contract ErrorResponse schema. Transport
// imports no plane, so it cannot use a plane's generated type.
type errorEnvelope struct {
	Code      string         `json:"code"`
	Message   string         `json:"message"`
	RequestID string         `json:"requestId"`
	Details   map[string]any `json:"details,omitempty"`
}

// decodeAPIError decodes the envelope, falling back to HTTP_ERROR, the status
// text and the X-Request-ID header. The boolean reports whether Retry-After
// carried a usable value.
func decodeAPIError(response *http.Response, body []byte, retryAfterMax time.Duration) (*APIError, bool) {
	payload := errorEnvelope{}
	if err := json.Unmarshal(body, &payload); err != nil {
		payload = errorEnvelope{}
	}
	code := strings.TrimSpace(payload.Code)
	if code == "" {
		code = "HTTP_ERROR"
	}
	message := strings.TrimSpace(payload.Message)
	if message == "" {
		message = http.StatusText(response.StatusCode)
	}
	requestID := strings.TrimSpace(payload.RequestID)
	if requestID == "" {
		requestID = strings.TrimSpace(response.Header.Get("X-Request-ID"))
	}
	retryAfter, retryAfterSet := ParseRetryAfter(response.Header.Get("Retry-After"), retryAfterMax)
	return &APIError{StatusCode: response.StatusCode, Code: code, Message: message,
		RequestID: requestID, Details: payload.Details, RetryAfter: retryAfter}, retryAfterSet
}
