package transport

import (
	"context"
	"time"
)

// Follower contains the shared polling state machine used by log iterators.
type Follower[Entry any] struct {
	fetch   func(context.Context) ([]Entry, time.Duration, error)
	entryID func(Entry) int64
	entries []Entry
	entry   Entry
	lastID  int64
	hasLast bool
	err     error
}

func NewFollower[Entry any](
	fetch func(context.Context) ([]Entry, time.Duration, error),
	entryID func(Entry) int64,
) *Follower[Entry] {
	return &Follower[Entry]{fetch: fetch, entryID: entryID}
}

func (it *Follower[Entry]) Next(ctx context.Context) bool {
	for it != nil && it.err == nil {
		if err := ctx.Err(); err != nil {
			it.err = err
			return false
		}
		if len(it.entries) > 0 {
			it.entry, it.entries = it.entries[0], it.entries[1:]
			if it.entryID != nil {
				id := it.entryID(it.entry)
				if it.hasLast && id <= it.lastID {
					continue
				}
				it.lastID, it.hasLast = id, true
			}
			return true
		}
		var delay time.Duration
		it.entries, delay, it.err = it.fetch(ctx)
		if it.err != nil {
			return false
		}
		if len(it.entries) == 0 {
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

func (it *Follower[Entry]) Entry() Entry {
	if it == nil {
		var zero Entry
		return zero
	}
	return it.entry
}

func (it *Follower[Entry]) Err() error {
	if it == nil {
		return nil
	}
	return it.err
}
