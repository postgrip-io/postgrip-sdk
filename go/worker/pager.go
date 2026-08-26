package worker

import "context"

type WorkerPager struct {
	client  *Client
	options ListWorkersOptions
	current WorkerList
	err     error
	done    bool
}

func (c *Client) Workers(options ListWorkersOptions) *WorkerPager {
	return &WorkerPager{client: c, options: options}
}

func (p *WorkerPager) Next(ctx context.Context) bool {
	if p == nil || p.done || p.err != nil {
		return false
	}
	p.current, p.err = p.client.List(ctx, p.options)
	if p.err != nil {
		return false
	}
	if p.current.NextPageToken == nil || *p.current.NextPageToken == "" {
		p.done = true
	} else {
		p.options.PageToken = p.current.NextPageToken
	}
	return true
}

func (p *WorkerPager) Page() WorkerList { return p.current }
func (p *WorkerPager) Err() error       { return p.err }

type JobPager struct {
	client   *Client
	workerID string
	query    OpenAPIListWorkerJobsQuery
	current  JobList
	err      error
	done     bool
}

func (c *Client) WorkerJobs(workerID string, query OpenAPIListWorkerJobsQuery) *JobPager {
	return &JobPager{client: c, workerID: workerID, query: query}
}

func (p *JobPager) Next(ctx context.Context) bool {
	if p == nil || p.done || p.err != nil {
		return false
	}
	p.current, p.err = p.client.Jobs(ctx, p.workerID, p.query)
	if p.err != nil {
		return false
	}
	if p.current.NextPageToken == nil || *p.current.NextPageToken == "" {
		p.done = true
	} else {
		p.query.PageToken = p.current.NextPageToken
	}
	return true
}

func (p *JobPager) Page() JobList { return p.current }
func (p *JobPager) Err() error    { return p.err }
