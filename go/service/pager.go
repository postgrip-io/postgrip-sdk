package service

import (
	"context"

	"github.com/postgrip-io/postgrip-agent-sdks/go/internal/transport"
)

type ServicePager struct {
	pager *transport.Pager[ServiceList]
}

func (c *Client) Services(query OpenAPIListServicesQuery) *ServicePager {
	return &ServicePager{pager: transport.NewPager(func(ctx context.Context) (ServiceList, string, error) {
		page, err := c.List(ctx, query)
		if err == nil && page.NextCursor != "" {
			query.Cursor = &page.NextCursor
		}
		return page, page.NextCursor, err
	})}
}

func (p *ServicePager) Next(ctx context.Context) bool {
	return p != nil && p.pager.Next(ctx)
}

func (p *ServicePager) Page() ServiceList { return p.pager.Page() }
func (p *ServicePager) Err() error        { return p.pager.Err() }

type EnvironmentPager struct {
	pager *transport.Pager[EnvironmentList]
}

func (c *Client) ServiceEnvironments(ref Reference, query OpenAPIListServiceEnvironmentsQuery) *EnvironmentPager {
	return &EnvironmentPager{pager: transport.NewPager(func(ctx context.Context) (EnvironmentList, string, error) {
		page, err := c.Environments(ctx, ref, query)
		if err == nil && page.NextCursor != "" {
			query.Cursor = &page.NextCursor
		}
		return page, page.NextCursor, err
	})}
}

func (p *EnvironmentPager) Next(ctx context.Context) bool {
	return p != nil && p.pager.Next(ctx)
}

func (p *EnvironmentPager) Page() EnvironmentList { return p.pager.Page() }
func (p *EnvironmentPager) Err() error            { return p.pager.Err() }

type DeploymentPager struct {
	pager *transport.Pager[DeploymentList]
}

func (c *Client) ServiceDeployments(ref Reference, query OpenAPIListServiceDeploymentsQuery) *DeploymentPager {
	return &DeploymentPager{pager: transport.NewPager(func(ctx context.Context) (DeploymentList, string, error) {
		page, err := c.Deployments(ctx, ref, query)
		if err == nil && page.NextCursor != "" {
			query.Cursor = &page.NextCursor
		}
		return page, page.NextCursor, err
	})}
}

func (p *DeploymentPager) Next(ctx context.Context) bool {
	return p != nil && p.pager.Next(ctx)
}

func (p *DeploymentPager) Page() DeploymentList { return p.pager.Page() }
func (p *DeploymentPager) Err() error           { return p.pager.Err() }
