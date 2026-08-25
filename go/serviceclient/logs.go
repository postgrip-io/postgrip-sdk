package serviceclient

import (
	"context"
	"time"
)

type LogIterator struct {
	client  *Client
	ref     Reference
	query   OpenAPIListServiceLogsQuery
	entries []LogEntry
	entry   LogEntry
	err     error
}

func (c *Client) FollowLogs(ref Reference, query OpenAPIListServiceLogsQuery) *LogIterator {
	follow := true
	query.Follow = &follow
	return &LogIterator{client: c, ref: ref, query: query}
}

func (it *LogIterator) Next(ctx context.Context) bool {
	for it != nil && it.err == nil {
		if err := ctx.Err(); err != nil {
			it.err = err
			return false
		}
		if len(it.entries) > 0 {
			it.entry, it.entries = it.entries[0], it.entries[1:]
			return true
		}
		page, err := it.client.Logs(ctx, it.ref, it.query)
		if err != nil {
			it.err = err
			return false
		}
		it.query.Cursor = &page.NextCursor
		it.entries = page.Items
		if len(it.entries) == 0 {
			delay := time.Duration(page.PollAfterMs) * time.Millisecond
			if delay <= 0 {
				delay = it.client.connection.followInterval
			}
			timer := time.NewTimer(delay)
			select {
			case <-ctx.Done():
				timer.Stop()
				it.err = ctx.Err()
				return false
			case <-timer.C:
			}
		}
	}
	return false
}

func (it *LogIterator) Entry() LogEntry { return it.entry }
func (it *LogIterator) Err() error      { return it.err }
