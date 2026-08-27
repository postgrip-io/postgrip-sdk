package service

import (
	"context"
	"time"

	"github.com/postgrip-io/postgrip-agent-sdks/go/internal/transport"
)

type LogIterator struct {
	follower *transport.Follower[LogEntry]
}

func (c *Client) FollowLogs(ref Reference, query OpenAPIListServiceLogsQuery) *LogIterator {
	follow := true
	query.Follow = &follow
	return &LogIterator{follower: transport.NewFollower(func(ctx context.Context) ([]LogEntry, time.Duration, error) {
		page, err := c.Logs(ctx, ref, query)
		if err != nil {
			return nil, 0, err
		}
		query.Cursor = &page.NextCursor
		delay := time.Duration(page.PollAfterMs) * time.Millisecond
		if delay <= 0 {
			delay = c.connection.followInterval
		}
		return page.Items, delay, nil
	}, nil)}
}

func (it *LogIterator) Next(ctx context.Context) bool {
	return it != nil && it.follower.Next(ctx)
}

func (it *LogIterator) Entry() LogEntry { return it.follower.Entry() }
func (it *LogIterator) Err() error      { return it.follower.Err() }
