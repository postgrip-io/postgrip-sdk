package service

import "context"

type ServicePager struct {
	client  *Client
	query   OpenAPIListServicesQuery
	current ServiceList
	err     error
	done    bool
}

func (c *Client) Services(query OpenAPIListServicesQuery) *ServicePager {
	return &ServicePager{client: c, query: query}
}

func (p *ServicePager) Next(ctx context.Context) bool {
	if p == nil || p.done || p.err != nil {
		return false
	}
	p.current, p.err = p.client.List(ctx, p.query)
	if p.err != nil {
		return false
	}
	if p.current.NextCursor == "" {
		p.done = true
	} else {
		p.query.Cursor = &p.current.NextCursor
	}
	return true
}

func (p *ServicePager) Page() ServiceList { return p.current }
func (p *ServicePager) Err() error        { return p.err }

type EnvironmentPager struct {
	client  *Client
	ref     Reference
	query   OpenAPIListServiceEnvironmentsQuery
	current EnvironmentList
	err     error
	done    bool
}

func (c *Client) ServiceEnvironments(ref Reference, query OpenAPIListServiceEnvironmentsQuery) *EnvironmentPager {
	return &EnvironmentPager{client: c, ref: ref, query: query}
}

func (p *EnvironmentPager) Next(ctx context.Context) bool {
	if p == nil || p.done || p.err != nil {
		return false
	}
	p.current, p.err = p.client.Environments(ctx, p.ref, p.query)
	if p.err != nil {
		return false
	}
	if p.current.NextCursor == "" {
		p.done = true
	} else {
		p.query.Cursor = &p.current.NextCursor
	}
	return true
}

func (p *EnvironmentPager) Page() EnvironmentList { return p.current }
func (p *EnvironmentPager) Err() error            { return p.err }

type DeploymentPager struct {
	client  *Client
	ref     Reference
	query   OpenAPIListServiceDeploymentsQuery
	current DeploymentList
	err     error
	done    bool
}

func (c *Client) ServiceDeployments(ref Reference, query OpenAPIListServiceDeploymentsQuery) *DeploymentPager {
	return &DeploymentPager{client: c, ref: ref, query: query}
}

func (p *DeploymentPager) Next(ctx context.Context) bool {
	if p == nil || p.done || p.err != nil {
		return false
	}
	p.current, p.err = p.client.Deployments(ctx, p.ref, p.query)
	if p.err != nil {
		return false
	}
	if p.current.NextCursor == "" {
		p.done = true
	} else {
		p.query.Cursor = &p.current.NextCursor
	}
	return true
}

func (p *DeploymentPager) Page() DeploymentList { return p.current }
func (p *DeploymentPager) Err() error           { return p.err }
