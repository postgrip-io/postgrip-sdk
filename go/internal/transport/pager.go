package transport

import "context"

// Pager contains the shared state machine used by public plane-specific pagers.
type Pager[Page any] struct {
	fetch   func(context.Context) (Page, string, error)
	current Page
	err     error
	done    bool
}

func NewPager[Page any](fetch func(context.Context) (Page, string, error)) *Pager[Page] {
	return &Pager[Page]{fetch: fetch}
}

func (p *Pager[Page]) Next(ctx context.Context) bool {
	if p == nil || p.done || p.err != nil {
		return false
	}
	var next string
	p.current, next, p.err = p.fetch(ctx)
	if p.err != nil {
		return false
	}
	p.done = next == ""
	return true
}

func (p *Pager[Page]) Page() Page {
	if p == nil {
		var zero Page
		return zero
	}
	return p.current
}

func (p *Pager[Page]) Err() error {
	if p == nil {
		return nil
	}
	return p.err
}
