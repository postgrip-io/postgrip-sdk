package worker

import (
	"context"

	"github.com/postgrip-io/postgrip-agent-sdks/go/internal/transport"
)

type WorkerPager struct {
	pager *transport.Pager[WorkerList]
}

func (c *Client) Workers(options ListWorkersOptions) *WorkerPager {
	return &WorkerPager{pager: transport.NewPager(func(ctx context.Context) (WorkerList, string, error) {
		page, err := c.List(ctx, options)
		next := ""
		if err == nil && page.NextPageToken != nil {
			next = *page.NextPageToken
			if next != "" {
				options.PageToken = page.NextPageToken
			}
		}
		return page, next, err
	})}
}

func (p *WorkerPager) Next(ctx context.Context) bool {
	return p != nil && p.pager.Next(ctx)
}

func (p *WorkerPager) Page() WorkerList { return p.pager.Page() }
func (p *WorkerPager) Err() error       { return p.pager.Err() }

type JobPager struct {
	pager *transport.Pager[JobList]
}

func (c *Client) WorkerJobs(workerID string, query OpenAPIListWorkerJobsQuery) *JobPager {
	return &JobPager{pager: transport.NewPager(func(ctx context.Context) (JobList, string, error) {
		page, err := c.Jobs(ctx, workerID, query)
		next := ""
		if err == nil && page.NextPageToken != nil {
			next = *page.NextPageToken
			if next != "" {
				query.PageToken = page.NextPageToken
			}
		}
		return page, next, err
	})}
}

func (p *JobPager) Next(ctx context.Context) bool {
	return p != nil && p.pager.Next(ctx)
}

func (p *JobPager) Page() JobList { return p.pager.Page() }
func (p *JobPager) Err() error    { return p.pager.Err() }
