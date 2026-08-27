package worker

import (
	"context"
	"time"

	"github.com/postgrip-io/postgrip-agent-sdks/go/internal/transport"
)

type OperationalLogIterator struct {
	follower *transport.Follower[OperationalLogEntry]
}

func (c *Client) FollowOperationalLogs(workerID string, query OpenAPIListWorkerOperationalLogsQuery) *OperationalLogIterator {
	return &OperationalLogIterator{follower: transport.NewFollower(func(ctx context.Context) ([]OperationalLogEntry, time.Duration, error) {
		page, err := c.OpenAPI().ListWorkerOperationalLogs(ctx, workerID, query)
		if err != nil {
			return nil, 0, err
		}
		query.Cursor = &page.NextCursor
		return page.Items, c.connection.followInterval, nil
	}, func(entry OperationalLogEntry) int64 { return entry.Id })}
}

func (it *OperationalLogIterator) Next(ctx context.Context) bool {
	return it != nil && it.follower.Next(ctx)
}

func (it *OperationalLogIterator) Entry() OperationalLogEntry { return it.follower.Entry() }
func (it *OperationalLogIterator) Err() error                 { return it.follower.Err() }

type SecurityLogIterator struct {
	follower *transport.Follower[SecurityLogEntry]
}

func (c *Client) FollowSecurityLogs(workerID string, query OpenAPIListWorkerSecurityLogsQuery) *SecurityLogIterator {
	return &SecurityLogIterator{follower: transport.NewFollower(func(ctx context.Context) ([]SecurityLogEntry, time.Duration, error) {
		page, err := c.OpenAPI().ListWorkerSecurityLogs(ctx, workerID, query)
		if err != nil {
			return nil, 0, err
		}
		query.Cursor = &page.NextCursor
		return page.Items, c.connection.followInterval, nil
	}, func(entry SecurityLogEntry) int64 { return entry.Id })}
}

func (it *SecurityLogIterator) Next(ctx context.Context) bool {
	return it != nil && it.follower.Next(ctx)
}

func (it *SecurityLogIterator) Entry() SecurityLogEntry { return it.follower.Entry() }
func (it *SecurityLogIterator) Err() error              { return it.follower.Err() }
