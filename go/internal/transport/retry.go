package transport

import (
	"context"
	"errors"
	"math/rand"
	"net/http"
	"strconv"
	"strings"
	"time"
)

// RetryConfig is the executor's retry policy: it bounds opt-in retries of
// eligible operations. Planes configure their own ceilings; the executor
// applies the same rule to every plane. It is not named RetryPolicy because
// protocol owns that wire type and the drift checker rejects SDK redeclarations.
type RetryConfig struct {
	// Enabled is the caller's retry opt-in. Retries are off by default.
	Enabled bool
	// MaxAttempts is the total number of attempts for an eligible operation.
	MaxAttempts int
	// MaxDelay caps the jittered exponential backoff between attempts.
	MaxDelay time.Duration
	// RetryAfterMax caps an honored Retry-After delay.
	RetryAfterMax time.Duration
}

func (p RetryConfig) attempts(operation Operation, idempotencyKey string) int {
	if !p.Enabled || !RetryEligible(operation, idempotencyKey) {
		return 1
	}
	return max(p.MaxAttempts, 1)
}

// delay returns the wait before the attempt after attempt. A Retry-After
// value is honored only for 429 and 503 responses that set one.
func (p RetryConfig) delay(attempt, status int, retryAfter time.Duration, retryAfterSet bool) time.Duration {
	if retryAfterSet && (status == http.StatusTooManyRequests || status == http.StatusServiceUnavailable) {
		return min(max(retryAfter, 0), p.RetryAfterMax)
	}
	capDelay := min(200*time.Millisecond*time.Duration(1<<(attempt-1)), p.MaxDelay)
	return time.Duration(rand.Int63n(max(int64(capDelay), 1)))
}

// RetryableStatus reports whether a response status may be retried for an
// eligible operation.
func RetryableStatus(status int) bool {
	switch status {
	case http.StatusRequestTimeout, http.StatusTooManyRequests, http.StatusBadGateway,
		http.StatusServiceUnavailable, http.StatusGatewayTimeout:
		return true
	}
	return false
}

// ParseRetryAfter parses delta-seconds or an HTTP date, capped at maximum.
// The boolean reports whether the header carried a usable value.
func ParseRetryAfter(value string, maximum time.Duration) (time.Duration, bool) {
	value = strings.TrimSpace(value)
	if value == "" {
		return 0, false
	}
	if seconds, err := strconv.ParseUint(value, 10, 64); err == nil {
		if maximum <= 0 || seconds > uint64(maximum/time.Second) {
			return max(maximum, 0), true
		}
		return time.Duration(seconds) * time.Second, true
	} else if errors.Is(err, strconv.ErrRange) && strings.IndexFunc(value, func(r rune) bool {
		return r < '0' || r > '9'
	}) == -1 {
		return max(maximum, 0), true
	}
	if when, err := http.ParseTime(value); err == nil {
		return min(max(time.Until(when), 0), max(maximum, 0)), true
	}
	return 0, false
}

func waitRetry(ctx context.Context, delay time.Duration) error {
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}
