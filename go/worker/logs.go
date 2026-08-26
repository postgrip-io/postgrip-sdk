package worker

import (
	"context"
	"time"
)

type OperationalLogIterator struct {
	client   *Client
	workerID string
	query    OpenAPIListWorkerOperationalLogsQuery
	entries  []OperationalLogEntry
	entry    OperationalLogEntry
	lastID   int64
	hasLast  bool
	err      error
}

func (c *Client) FollowOperationalLogs(workerID string, query OpenAPIListWorkerOperationalLogsQuery) *OperationalLogIterator {
	return &OperationalLogIterator{client: c, workerID: workerID, query: query}
}

func (it *OperationalLogIterator) Next(ctx context.Context) bool {
	for it != nil && it.err == nil {
		if err := ctx.Err(); err != nil {
			it.err = err
			return false
		}
		if len(it.entries) > 0 {
			it.entry, it.entries = it.entries[0], it.entries[1:]
			if it.hasLast && it.entry.Id <= it.lastID {
				continue
			}
			it.lastID, it.hasLast = it.entry.Id, true
			return true
		}
		page, err := it.client.OpenAPI().ListWorkerOperationalLogs(ctx, it.workerID, it.query)
		if err != nil {
			it.err = err
			return false
		}
		it.query.Cursor = &page.NextCursor
		it.entries = page.Items
		if len(it.entries) == 0 {
			timer := time.NewTimer(it.client.connection.followInterval)
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

func (it *OperationalLogIterator) Entry() OperationalLogEntry { return it.entry }
func (it *OperationalLogIterator) Err() error                 { return it.err }

type SecurityLogIterator struct {
	client   *Client
	workerID string
	query    OpenAPIListWorkerSecurityLogsQuery
	entries  []SecurityLogEntry
	entry    SecurityLogEntry
	lastID   int64
	hasLast  bool
	err      error
}

func (c *Client) FollowSecurityLogs(workerID string, query OpenAPIListWorkerSecurityLogsQuery) *SecurityLogIterator {
	return &SecurityLogIterator{client: c, workerID: workerID, query: query}
}

func (it *SecurityLogIterator) Next(ctx context.Context) bool {
	for it != nil && it.err == nil {
		if err := ctx.Err(); err != nil {
			it.err = err
			return false
		}
		if len(it.entries) > 0 {
			it.entry, it.entries = it.entries[0], it.entries[1:]
			if it.hasLast && it.entry.Id <= it.lastID {
				continue
			}
			it.lastID, it.hasLast = it.entry.Id, true
			return true
		}
		page, err := it.client.OpenAPI().ListWorkerSecurityLogs(ctx, it.workerID, it.query)
		if err != nil {
			it.err = err
			return false
		}
		it.query.Cursor = &page.NextCursor
		it.entries = page.Items
		if len(it.entries) == 0 {
			timer := time.NewTimer(it.client.connection.followInterval)
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

func (it *SecurityLogIterator) Entry() SecurityLogEntry { return it.entry }
func (it *SecurityLogIterator) Err() error              { return it.err }
