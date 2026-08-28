package service

import (
	"context"
	"errors"
	"strings"
)

// WriteOptions carries the mandatory replay and concurrency fences for a
// Service administration mutation.
type WriteOptions struct {
	IdempotencyKey string
	IfMatch        string
}

// MutationOptions carries an idempotency fence for a mutation whose
// concurrency preconditions are expressed in its request body.
type MutationOptions struct {
	IdempotencyKey string
}

func (o WriteOptions) validate(conditional bool) error {
	if err := validateIdempotencyKey(o.IdempotencyKey); err != nil {
		return err
	}
	if conditional && (strings.TrimSpace(o.IfMatch) == "" || strings.ContainsAny(o.IfMatch, "\r\n")) {
		return errors.New("postgrip-service: If-Match ETag must be non-empty and contain no line breaks")
	}
	return nil
}

type TargetServicesClient struct{ client *Client }
type ProjectsClient struct{ client *Client }
type ServiceEnvironmentsClient struct{ client *Client }
type ManagedVolumesClient struct{ client *Client }
type ServiceDomainsClient struct{ client *Client }
type ServiceDNSClient struct{ client *Client }
type ServiceVariablesClient struct{ client *Client }
type ServiceRepositoriesClient struct{ client *Client }
type ServicePromotionsClient struct{ client *Client }
type ServiceRetentionClient struct{ client *Client }
type ServiceConfigurationOperationsClient struct{ client *Client }
type DeclarativeConfigurationClient struct{ client *Client }

func (c *Client) TargetServices() TargetServicesClient { return TargetServicesClient{client: c} }
func (c *Client) Projects() ProjectsClient             { return ProjectsClient{client: c} }
func (c *Client) EnvironmentAdministration() ServiceEnvironmentsClient {
	return ServiceEnvironmentsClient{client: c}
}
func (c *Client) ManagedVolumes() ManagedVolumesClient { return ManagedVolumesClient{client: c} }
func (c *Client) ServiceDomains() ServiceDomainsClient { return ServiceDomainsClient{client: c} }
func (c *Client) ServiceDNS() ServiceDNSClient         { return ServiceDNSClient{client: c} }
func (c *Client) ServiceVariables() ServiceVariablesClient {
	return ServiceVariablesClient{client: c}
}
func (c *Client) ServiceRepositories() ServiceRepositoriesClient {
	return ServiceRepositoriesClient{client: c}
}
func (c *Client) ServicePromotions() ServicePromotionsClient {
	return ServicePromotionsClient{client: c}
}
func (c *Client) ServiceRetention() ServiceRetentionClient {
	return ServiceRetentionClient{client: c}
}
func (c *Client) ServiceConfigurationOperations() ServiceConfigurationOperationsClient {
	return ServiceConfigurationOperationsClient{client: c}
}
func (c *Client) DeclarativeConfiguration() DeclarativeConfigurationClient {
	return DeclarativeConfigurationClient{client: c}
}

func (c TargetServicesClient) Attach(ctx context.Context, body OpenAPIAttachTargetServiceRequestBody, options WriteOptions) (OpenAPIAttachTargetServiceResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIAttachTargetServiceResponseBody{}, err
	}
	return c.client.OpenAPI().AttachTargetService(ctx, OpenAPIAttachTargetServiceHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c TargetServicesClient) Update(ctx context.Context, serviceID string, body OpenAPIUpdateTargetServiceRequestBody, options WriteOptions) (OpenAPIUpdateTargetServiceResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIUpdateTargetServiceResponseBody{}, err
	}
	return c.client.OpenAPI().UpdateTargetService(ctx, serviceID, OpenAPIUpdateTargetServiceHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c TargetServicesClient) RemovalImpact(ctx context.Context, serviceID string) (OpenAPIGetTargetServiceRemovalImpactResponseBody, error) {
	return c.client.OpenAPI().GetTargetServiceRemovalImpact(ctx, serviceID)
}

func (c TargetServicesClient) Detach(ctx context.Context, serviceID string, body OpenAPIDetachTargetServiceRequestBody, options WriteOptions) (OpenAPIDetachTargetServiceResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIDetachTargetServiceResponseBody{}, err
	}
	return c.client.OpenAPI().DetachTargetService(ctx, serviceID, OpenAPIDetachTargetServiceHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c TargetServicesClient) PutConnection(ctx context.Context, serviceID string, body OpenAPIPutTargetServiceConnectionRequestBody, options WriteOptions) (OpenAPIPutTargetServiceConnectionResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIPutTargetServiceConnectionResponseBody{}, err
	}
	return c.client.OpenAPI().PutTargetServiceConnection(ctx, serviceID, OpenAPIPutTargetServiceConnectionHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c TargetServicesClient) ClearConnection(ctx context.Context, serviceID string, options WriteOptions) (OpenAPIClearTargetServiceConnectionResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIClearTargetServiceConnectionResponseBody{}, err
	}
	return c.client.OpenAPI().ClearTargetServiceConnection(ctx, serviceID, OpenAPIClearTargetServiceConnectionHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch})
}

func (c ProjectsClient) Create(ctx context.Context, body OpenAPICreateServiceProjectRequestBody, options WriteOptions) (OpenAPICreateServiceProjectResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPICreateServiceProjectResponseBody{}, err
	}
	return c.client.OpenAPI().CreateServiceProject(ctx, OpenAPICreateServiceProjectHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c ProjectsClient) Update(ctx context.Context, serviceID string, body OpenAPIUpdateServiceProjectRequestBody, options WriteOptions) (OpenAPIUpdateServiceProjectResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIUpdateServiceProjectResponseBody{}, err
	}
	return c.client.OpenAPI().UpdateServiceProject(ctx, serviceID, OpenAPIUpdateServiceProjectHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c ProjectsClient) RemovalImpact(ctx context.Context, serviceID string) (OpenAPIGetServiceProjectRemovalImpactResponseBody, error) {
	return c.client.OpenAPI().GetServiceProjectRemovalImpact(ctx, serviceID)
}

func (c ProjectsClient) Delete(ctx context.Context, serviceID string, body OpenAPIDeleteServiceProjectRequestBody, options WriteOptions) (OpenAPIDeleteServiceProjectResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIDeleteServiceProjectResponseBody{}, err
	}
	return c.client.OpenAPI().DeleteServiceProject(ctx, serviceID, OpenAPIDeleteServiceProjectHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c ServiceEnvironmentsClient) Get(ctx context.Context, projectID, environmentID string) (OpenAPIGetServiceEnvironmentResponseBody, error) {
	return c.client.OpenAPI().GetServiceEnvironment(ctx, projectID, environmentID)
}

func (c ServiceEnvironmentsClient) Create(ctx context.Context, projectID string, body OpenAPICreateServiceEnvironmentRequestBody, options WriteOptions) (OpenAPICreateServiceEnvironmentResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPICreateServiceEnvironmentResponseBody{}, err
	}
	return c.client.OpenAPI().CreateServiceEnvironment(ctx, projectID, OpenAPICreateServiceEnvironmentHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c ServiceEnvironmentsClient) Update(ctx context.Context, projectID, environmentID string, body OpenAPIUpdateServiceEnvironmentRequestBody, options WriteOptions) (OpenAPIUpdateServiceEnvironmentResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIUpdateServiceEnvironmentResponseBody{}, err
	}
	return c.client.OpenAPI().UpdateServiceEnvironment(ctx, projectID, environmentID, OpenAPIUpdateServiceEnvironmentHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c ServiceEnvironmentsClient) PreviewReassignment(ctx context.Context, projectID, environmentID string, body OpenAPIPreviewServiceEnvironmentReassignmentRequestBody, options WriteOptions) (OpenAPIPreviewServiceEnvironmentReassignmentResponseBody, error) {
	if err := options.validate(false); err != nil {
		return OpenAPIPreviewServiceEnvironmentReassignmentResponseBody{}, err
	}
	return c.client.OpenAPI().PreviewServiceEnvironmentReassignment(ctx, projectID, environmentID, OpenAPIPreviewServiceEnvironmentReassignmentHeaders{IdempotencyKey: options.IdempotencyKey}, body)
}

func (c ServiceEnvironmentsClient) Reassign(ctx context.Context, projectID, environmentID string, body OpenAPIReassignServiceEnvironmentRequestBody, options WriteOptions) (OpenAPIReassignServiceEnvironmentResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIReassignServiceEnvironmentResponseBody{}, err
	}
	return c.client.OpenAPI().ReassignServiceEnvironment(ctx, projectID, environmentID, OpenAPIReassignServiceEnvironmentHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c ServiceEnvironmentsClient) RemovalImpact(ctx context.Context, projectID, environmentID string) (OpenAPIGetServiceEnvironmentRemovalImpactResponseBody, error) {
	return c.client.OpenAPI().GetServiceEnvironmentRemovalImpact(ctx, projectID, environmentID)
}

func (c ServiceEnvironmentsClient) Delete(ctx context.Context, projectID, environmentID string, body OpenAPIDeleteServiceEnvironmentRequestBody, options WriteOptions) (OpenAPIDeleteServiceEnvironmentResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIDeleteServiceEnvironmentResponseBody{}, err
	}
	return c.client.OpenAPI().DeleteServiceEnvironment(ctx, projectID, environmentID, OpenAPIDeleteServiceEnvironmentHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c ManagedVolumesClient) List(ctx context.Context, projectID string) (OpenAPIListServiceVolumesResponseBody, error) {
	return c.client.OpenAPI().ListServiceVolumes(ctx, projectID)
}

func (c ManagedVolumesClient) Create(ctx context.Context, projectID string, body OpenAPICreateServiceVolumeRequestBody, options WriteOptions) (OpenAPICreateServiceVolumeResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPICreateServiceVolumeResponseBody{}, err
	}
	return c.client.OpenAPI().CreateServiceVolume(ctx, projectID, OpenAPICreateServiceVolumeHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c ManagedVolumesClient) Get(ctx context.Context, projectID, volumeRef string) (OpenAPIGetServiceVolumeResponseBody, error) {
	return c.client.OpenAPI().GetServiceVolume(ctx, projectID, volumeRef)
}

func (c ManagedVolumesClient) RemovalImpact(ctx context.Context, projectID, volumeRef string) (OpenAPIGetServiceVolumeRemovalImpactResponseBody, error) {
	return c.client.OpenAPI().GetServiceVolumeRemovalImpact(ctx, projectID, volumeRef)
}

func (c ManagedVolumesClient) Delete(ctx context.Context, projectID, volumeRef string, body OpenAPIDeleteServiceVolumeRequestBody, options WriteOptions) (OpenAPIDeleteServiceVolumeResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIDeleteServiceVolumeResponseBody{}, err
	}
	return c.client.OpenAPI().DeleteServiceVolume(ctx, projectID, volumeRef, OpenAPIDeleteServiceVolumeHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c ManagedVolumesClient) Bind(ctx context.Context, projectID, environmentID string, body OpenAPIBindServiceVolumeRequestBody, options WriteOptions) (OpenAPIBindServiceVolumeResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIBindServiceVolumeResponseBody{}, err
	}
	return c.client.OpenAPI().BindServiceVolume(ctx, projectID, environmentID, OpenAPIBindServiceVolumeHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c ManagedVolumesClient) UpdateBinding(ctx context.Context, projectID, environmentID, volumeRef string, body OpenAPIUpdateServiceVolumeBindingRequestBody, options WriteOptions) (OpenAPIUpdateServiceVolumeBindingResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIUpdateServiceVolumeBindingResponseBody{}, err
	}
	return c.client.OpenAPI().UpdateServiceVolumeBinding(ctx, projectID, environmentID, volumeRef, OpenAPIUpdateServiceVolumeBindingHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c ManagedVolumesClient) Unbind(ctx context.Context, projectID, environmentID, volumeRef string, options WriteOptions) (OpenAPIUnbindServiceVolumeResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIUnbindServiceVolumeResponseBody{}, err
	}
	return c.client.OpenAPI().UnbindServiceVolume(ctx, projectID, environmentID, volumeRef, OpenAPIUnbindServiceVolumeHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch})
}

func (c ServiceDomainsClient) List(ctx context.Context, projectID, environmentID string) (OpenAPIListServiceDomainsResponseBody, error) {
	return c.client.OpenAPI().ListServiceDomains(ctx, projectID, environmentID)
}

func (c ServiceDomainsClient) Create(ctx context.Context, projectID, environmentID string, body OpenAPICreateServiceDomainRequestBody, options WriteOptions) (OpenAPICreateServiceDomainResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPICreateServiceDomainResponseBody{}, err
	}
	return c.client.OpenAPI().CreateServiceDomain(ctx, projectID, environmentID, OpenAPICreateServiceDomainHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c ServiceDomainsClient) Update(ctx context.Context, projectID, environmentID, domainID string, body OpenAPIUpdateServiceDomainRequestBody, options WriteOptions) (OpenAPIUpdateServiceDomainResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIUpdateServiceDomainResponseBody{}, err
	}
	return c.client.OpenAPI().UpdateServiceDomain(ctx, projectID, environmentID, domainID, OpenAPIUpdateServiceDomainHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c ServiceDomainsClient) Delete(ctx context.Context, projectID, environmentID, domainID string, options WriteOptions) (OpenAPIDeleteServiceDomainResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIDeleteServiceDomainResponseBody{}, err
	}
	return c.client.OpenAPI().DeleteServiceDomain(ctx, projectID, environmentID, domainID, OpenAPIDeleteServiceDomainHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch})
}

func (c ServiceDomainsClient) Verification(ctx context.Context, projectID, environmentID, domainID string) (OpenAPIGetServiceDomainVerificationResponseBody, error) {
	return c.client.OpenAPI().GetServiceDomainVerification(ctx, projectID, environmentID, domainID)
}

func (c ServiceDomainsClient) Verify(ctx context.Context, projectID, environmentID, domainID string, options MutationOptions) (OpenAPIVerifyServiceDomainResponseBody, error) {
	if err := validateIdempotencyKey(options.IdempotencyKey); err != nil {
		return OpenAPIVerifyServiceDomainResponseBody{}, err
	}
	return c.client.OpenAPI().VerifyServiceDomain(ctx, projectID, environmentID, domainID, OpenAPIVerifyServiceDomainHeaders{IdempotencyKey: options.IdempotencyKey})
}

func (c ServiceDNSClient) CanonicalState(ctx context.Context, projectID, environmentID, domainID string) (OpenAPIGetServiceDNSCanonicalStateResponseBody, error) {
	return c.client.OpenAPI().GetServiceDNSCanonicalState(ctx, projectID, environmentID, domainID)
}

func (c ServiceDNSClient) Plans(ctx context.Context, projectID, environmentID, domainID string) (OpenAPIListServiceDNSPlansResponseBody, error) {
	return c.client.OpenAPI().ListServiceDNSPlans(ctx, projectID, environmentID, domainID)
}

func (c ServiceDNSClient) CreatePlan(ctx context.Context, projectID, environmentID, domainID string, body OpenAPICreateServiceDNSPlanRequestBody, options MutationOptions) (OpenAPICreateServiceDNSPlanResponseBody, error) {
	if err := validateIdempotencyKey(options.IdempotencyKey); err != nil {
		return OpenAPICreateServiceDNSPlanResponseBody{}, err
	}
	return c.client.OpenAPI().CreateServiceDNSPlan(ctx, projectID, environmentID, domainID, OpenAPICreateServiceDNSPlanHeaders{IdempotencyKey: options.IdempotencyKey}, body)
}

func (c ServiceDNSClient) Plan(ctx context.Context, projectID, environmentID, domainID, planID string) (OpenAPIGetServiceDNSPlanResponseBody, error) {
	return c.client.OpenAPI().GetServiceDNSPlan(ctx, projectID, environmentID, domainID, planID)
}

func (c ServiceDNSClient) Apply(ctx context.Context, projectID, environmentID, domainID, planID string, body OpenAPIApplyServiceDNSPlanRequestBody, options MutationOptions) (OpenAPIApplyServiceDNSPlanResponseBody, error) {
	if err := validateIdempotencyKey(options.IdempotencyKey); err != nil {
		return OpenAPIApplyServiceDNSPlanResponseBody{}, err
	}
	return c.client.OpenAPI().ApplyServiceDNSPlan(ctx, projectID, environmentID, domainID, planID, OpenAPIApplyServiceDNSPlanHeaders{IdempotencyKey: options.IdempotencyKey}, body)
}

func (c ServiceDNSClient) ReportProviderResult(ctx context.Context, projectID, environmentID, domainID, planID string, body OpenAPIReportServiceDNSProviderResultRequestBody, options MutationOptions) (OpenAPIReportServiceDNSProviderResultResponseBody, error) {
	if err := validateIdempotencyKey(options.IdempotencyKey); err != nil {
		return OpenAPIReportServiceDNSProviderResultResponseBody{}, err
	}
	return c.client.OpenAPI().ReportServiceDNSProviderResult(ctx, projectID, environmentID, domainID, planID, OpenAPIReportServiceDNSProviderResultHeaders{IdempotencyKey: options.IdempotencyKey}, body)
}

func (c ServiceDNSClient) Rollback(ctx context.Context, projectID, environmentID, domainID, planID string, body OpenAPIRollbackServiceDNSPlanRequestBody, options MutationOptions) (OpenAPIRollbackServiceDNSPlanResponseBody, error) {
	if err := validateIdempotencyKey(options.IdempotencyKey); err != nil {
		return OpenAPIRollbackServiceDNSPlanResponseBody{}, err
	}
	return c.client.OpenAPI().RollbackServiceDNSPlan(ctx, projectID, environmentID, domainID, planID, OpenAPIRollbackServiceDNSPlanHeaders{IdempotencyKey: options.IdempotencyKey}, body)
}

func (c ServiceDNSClient) FailoverPolicy(ctx context.Context, projectID, environmentID, domainID string) (OpenAPIGetServiceDNSFailoverPolicyResponseBody, error) {
	return c.client.OpenAPI().GetServiceDNSFailoverPolicy(ctx, projectID, environmentID, domainID)
}

func (c ServiceDNSClient) UpdateFailoverPolicy(ctx context.Context, projectID, environmentID, domainID string, body OpenAPIUpdateServiceDNSFailoverPolicyRequestBody, options MutationOptions) (OpenAPIUpdateServiceDNSFailoverPolicyResponseBody, error) {
	if err := validateIdempotencyKey(options.IdempotencyKey); err != nil {
		return OpenAPIUpdateServiceDNSFailoverPolicyResponseBody{}, err
	}
	return c.client.OpenAPI().UpdateServiceDNSFailoverPolicy(ctx, projectID, environmentID, domainID, OpenAPIUpdateServiceDNSFailoverPolicyHeaders{IdempotencyKey: options.IdempotencyKey}, body)
}

func (c ServiceDNSClient) Failover(ctx context.Context, projectID, environmentID, domainID string, body OpenAPIRequestServiceDNSFailoverRequestBody, options MutationOptions) (OpenAPIRequestServiceDNSFailoverResponseBody, error) {
	if err := validateIdempotencyKey(options.IdempotencyKey); err != nil {
		return OpenAPIRequestServiceDNSFailoverResponseBody{}, err
	}
	return c.client.OpenAPI().RequestServiceDNSFailover(ctx, projectID, environmentID, domainID, OpenAPIRequestServiceDNSFailoverHeaders{IdempotencyKey: options.IdempotencyKey}, body)
}

func (c ServiceVariablesClient) List(ctx context.Context, projectID, environmentID string) (OpenAPIListServiceVariablesResponseBody, error) {
	return c.client.OpenAPI().ListServiceVariables(ctx, projectID, environmentID)
}

func (c ServiceVariablesClient) Create(ctx context.Context, projectID, environmentID string, body OpenAPICreateServiceVariableRequestBody, options WriteOptions) (OpenAPICreateServiceVariableResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPICreateServiceVariableResponseBody{}, err
	}
	return c.client.OpenAPI().CreateServiceVariable(ctx, projectID, environmentID, OpenAPICreateServiceVariableHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c ServiceVariablesClient) Update(ctx context.Context, projectID, environmentID, variableID string, body OpenAPIUpdateServiceVariableRequestBody, options WriteOptions) (OpenAPIUpdateServiceVariableResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIUpdateServiceVariableResponseBody{}, err
	}
	return c.client.OpenAPI().UpdateServiceVariable(ctx, projectID, environmentID, variableID, OpenAPIUpdateServiceVariableHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c ServiceVariablesClient) Delete(ctx context.Context, projectID, environmentID, variableID string, options WriteOptions) (OpenAPIDeleteServiceVariableResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIDeleteServiceVariableResponseBody{}, err
	}
	return c.client.OpenAPI().DeleteServiceVariable(ctx, projectID, environmentID, variableID, OpenAPIDeleteServiceVariableHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch})
}

func (c ServiceVariablesClient) PutValue(ctx context.Context, projectID, environmentID, variableID string, body OpenAPIPutServiceVariableValueRequestBody, options WriteOptions) (OpenAPIPutServiceVariableValueResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIPutServiceVariableValueResponseBody{}, err
	}
	return c.client.OpenAPI().PutServiceVariableValue(ctx, projectID, environmentID, variableID, OpenAPIPutServiceVariableValueHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c ServiceVariablesClient) ClearValue(ctx context.Context, projectID, environmentID, variableID string, options WriteOptions) (OpenAPIClearServiceVariableValueResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIClearServiceVariableValueResponseBody{}, err
	}
	return c.client.OpenAPI().ClearServiceVariableValue(ctx, projectID, environmentID, variableID, OpenAPIClearServiceVariableValueHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch})
}

func (c ServiceVariablesClient) Apply(ctx context.Context, projectID string, body OpenAPIApplyServiceVariablesRequestBody, options MutationOptions) (OpenAPIApplyServiceVariablesResponseBody, error) {
	if err := validateIdempotencyKey(options.IdempotencyKey); err != nil {
		return OpenAPIApplyServiceVariablesResponseBody{}, err
	}
	return c.client.OpenAPI().ApplyServiceVariables(ctx, projectID, OpenAPIApplyServiceVariablesHeaders{IdempotencyKey: options.IdempotencyKey}, body)
}

func (c ServiceRepositoriesClient) Get(ctx context.Context, projectID string) (OpenAPIGetServiceRepositoryResponseBody, error) {
	return c.client.OpenAPI().GetServiceRepository(ctx, projectID)
}

func (c ServiceRepositoriesClient) Update(ctx context.Context, projectID string, body OpenAPIUpdateServiceRepositoryRequestBody, options WriteOptions) (OpenAPIUpdateServiceRepositoryResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIUpdateServiceRepositoryResponseBody{}, err
	}
	return c.client.OpenAPI().UpdateServiceRepository(ctx, projectID, OpenAPIUpdateServiceRepositoryHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c ServiceRepositoriesClient) PutCredential(ctx context.Context, projectID, kind string, body OpenAPIPutServiceRepositoryCredentialRequestBody, options WriteOptions) (OpenAPIPutServiceRepositoryCredentialResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIPutServiceRepositoryCredentialResponseBody{}, err
	}
	return c.client.OpenAPI().PutServiceRepositoryCredential(ctx, projectID, kind, OpenAPIPutServiceRepositoryCredentialHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c ServiceRepositoriesClient) ClearCredential(ctx context.Context, projectID, kind string, options WriteOptions) (OpenAPIClearServiceRepositoryCredentialResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIClearServiceRepositoryCredentialResponseBody{}, err
	}
	return c.client.OpenAPI().ClearServiceRepositoryCredential(ctx, projectID, kind, OpenAPIClearServiceRepositoryCredentialHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch})
}

func (c ServiceRepositoriesClient) RefreshCredential(ctx context.Context, projectID, kind string, options WriteOptions) (OpenAPIRefreshServiceRepositoryCredentialResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIRefreshServiceRepositoryCredentialResponseBody{}, err
	}
	return c.client.OpenAPI().RefreshServiceRepositoryCredential(ctx, projectID, kind, OpenAPIRefreshServiceRepositoryCredentialHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch})
}

func (c ServiceRepositoriesClient) ListGitHub(ctx context.Context, query OpenAPIListGitHubAppRepositoriesQuery) (OpenAPIListGitHubAppRepositoriesResponseBody, error) {
	return c.client.OpenAPI().ListGitHubAppRepositories(ctx, query)
}

func (c ServiceRepositoriesClient) PreviewGitHubAdoption(ctx context.Context, projectID string, body OpenAPIPreviewGitHubRepositoryAdoptionRequestBody, options MutationOptions) (OpenAPIPreviewGitHubRepositoryAdoptionResponseBody, error) {
	if err := validateIdempotencyKey(options.IdempotencyKey); err != nil {
		return OpenAPIPreviewGitHubRepositoryAdoptionResponseBody{}, err
	}
	return c.client.OpenAPI().PreviewGitHubRepositoryAdoption(ctx, projectID, OpenAPIPreviewGitHubRepositoryAdoptionHeaders{IdempotencyKey: options.IdempotencyKey}, body)
}

func (c ServiceRepositoriesClient) AdoptGitHub(ctx context.Context, projectID string, body OpenAPIAdoptGitHubRepositoryRequestBody, options WriteOptions) (OpenAPIAdoptGitHubRepositoryResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIAdoptGitHubRepositoryResponseBody{}, err
	}
	return c.client.OpenAPI().AdoptGitHubRepository(ctx, projectID, OpenAPIAdoptGitHubRepositoryHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c ServicePromotionsClient) List(ctx context.Context, projectID string, query OpenAPIListServicePromotionsQuery) (OpenAPIListServicePromotionsResponseBody, error) {
	return c.client.OpenAPI().ListServicePromotions(ctx, projectID, query)
}

func (c ServicePromotionsClient) Preview(ctx context.Context, projectID string, query OpenAPIPreviewServicePromotionQuery) (OpenAPIPreviewServicePromotionResponseBody, error) {
	return c.client.OpenAPI().PreviewServicePromotion(ctx, projectID, query)
}

func (c ServicePromotionsClient) Create(ctx context.Context, projectID string, body OpenAPIPromoteServiceDeploymentRequestBody, options WriteOptions) (OpenAPIPromoteServiceDeploymentResponseBody, error) {
	if err := options.validate(false); err != nil {
		return OpenAPIPromoteServiceDeploymentResponseBody{}, err
	}
	return c.client.OpenAPI().PromoteServiceDeployment(ctx, projectID, OpenAPIPromoteServiceDeploymentHeaders{IdempotencyKey: options.IdempotencyKey}, body)
}

func (c ServiceRetentionClient) GetBuild(ctx context.Context, projectID string) (OpenAPIGetServiceBuildLogSettingsResponseBody, error) {
	return c.client.OpenAPI().GetServiceBuildLogSettings(ctx, projectID)
}

func (c ServiceRetentionClient) UpdateBuild(ctx context.Context, projectID string, body OpenAPIUpdateServiceBuildLogSettingsRequestBody, options WriteOptions) (OpenAPIUpdateServiceBuildLogSettingsResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIUpdateServiceBuildLogSettingsResponseBody{}, err
	}
	return c.client.OpenAPI().UpdateServiceBuildLogSettings(ctx, projectID, OpenAPIUpdateServiceBuildLogSettingsHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c ServiceRetentionClient) TrimBuild(ctx context.Context, projectID string, options WriteOptions) (OpenAPITrimServiceBuildLogsResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPITrimServiceBuildLogsResponseBody{}, err
	}
	return c.client.OpenAPI().TrimServiceBuildLogs(ctx, projectID, OpenAPITrimServiceBuildLogsHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch})
}

func (c ServiceRetentionClient) FlushBuild(ctx context.Context, projectID string, options WriteOptions) (OpenAPIFlushServiceBuildLogsResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIFlushServiceBuildLogsResponseBody{}, err
	}
	return c.client.OpenAPI().FlushServiceBuildLogs(ctx, projectID, OpenAPIFlushServiceBuildLogsHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch})
}

func (c ServiceRetentionClient) GetRuntime(ctx context.Context, projectID string, query OpenAPIGetServiceRuntimeLogSettingsQuery) (OpenAPIGetServiceRuntimeLogSettingsResponseBody, error) {
	return c.client.OpenAPI().GetServiceRuntimeLogSettings(ctx, projectID, query)
}

func (c ServiceRetentionClient) UpdateRuntime(ctx context.Context, projectID string, query OpenAPIUpdateServiceRuntimeLogSettingsQuery, body OpenAPIUpdateServiceRuntimeLogSettingsRequestBody, options WriteOptions) (OpenAPIUpdateServiceRuntimeLogSettingsResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIUpdateServiceRuntimeLogSettingsResponseBody{}, err
	}
	return c.client.OpenAPI().UpdateServiceRuntimeLogSettings(ctx, projectID, query, OpenAPIUpdateServiceRuntimeLogSettingsHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}

func (c ServiceRetentionClient) TrimRuntime(ctx context.Context, projectID string, query OpenAPITrimServiceRuntimeLogsQuery, options WriteOptions) (OpenAPITrimServiceRuntimeLogsResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPITrimServiceRuntimeLogsResponseBody{}, err
	}
	return c.client.OpenAPI().TrimServiceRuntimeLogs(ctx, projectID, query, OpenAPITrimServiceRuntimeLogsHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch})
}

func (c ServiceRetentionClient) FlushRuntime(ctx context.Context, projectID string, query OpenAPIFlushServiceRuntimeLogsQuery, options WriteOptions) (OpenAPIFlushServiceRuntimeLogsResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIFlushServiceRuntimeLogsResponseBody{}, err
	}
	return c.client.OpenAPI().FlushServiceRuntimeLogs(ctx, projectID, query, OpenAPIFlushServiceRuntimeLogsHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch})
}

func (c ServiceConfigurationOperationsClient) List(ctx context.Context, query OpenAPIListServiceConfigurationOperationsQuery) (OpenAPIListServiceConfigurationOperationsResponseBody, error) {
	return c.client.OpenAPI().ListServiceConfigurationOperations(ctx, query)
}

func (c ServiceConfigurationOperationsClient) Get(ctx context.Context, operationID string) (OpenAPIGetServiceConfigurationOperationResponseBody, error) {
	return c.client.OpenAPI().GetServiceConfigurationOperation(ctx, operationID)
}

func (c ServiceConfigurationOperationsClient) Retry(ctx context.Context, operationID string, options WriteOptions) (OpenAPIRetryServiceConfigurationOperationResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIRetryServiceConfigurationOperationResponseBody{}, err
	}
	return c.client.OpenAPI().RetryServiceConfigurationOperation(ctx, operationID, OpenAPIRetryServiceConfigurationOperationHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch})
}

// Validate checks a PostGrip configuration without creating a stack or plan.
func (c DeclarativeConfigurationClient) Validate(ctx context.Context, body OpenAPIValidatePostGripConfigurationRequestBody) (OpenAPIValidatePostGripConfigurationResponseBody, error) {
	return c.client.OpenAPI().ValidatePostGripConfiguration(ctx, body)
}

// GetStack returns the last applied state for a declarative stack.
func (c DeclarativeConfigurationClient) GetStack(ctx context.Context, stackKey string) (OpenAPIGetPostGripConfigurationStackResponseBody, error) {
	return c.client.OpenAPI().GetPostGripConfigurationStack(ctx, stackKey)
}

// CreatePlan creates an immutable, expiring plan without applying it.
func (c DeclarativeConfigurationClient) CreatePlan(ctx context.Context, stackKey string, body OpenAPICreatePostGripConfigurationPlanRequestBody, options MutationOptions) (OpenAPICreatePostGripConfigurationPlanResponseBody, error) {
	if err := validateIdempotencyKey(options.IdempotencyKey); err != nil {
		return OpenAPICreatePostGripConfigurationPlanResponseBody{}, err
	}
	return c.client.OpenAPI().CreatePostGripConfigurationPlan(ctx, stackKey, OpenAPICreatePostGripConfigurationPlanHeaders{IdempotencyKey: options.IdempotencyKey}, body)
}

// GetPlan returns immutable plan metadata and its safe receipt.
func (c DeclarativeConfigurationClient) GetPlan(ctx context.Context, stackKey, planID string) (OpenAPIGetPostGripConfigurationPlanResponseBody, error) {
	return c.client.OpenAPI().GetPostGripConfigurationPlan(ctx, stackKey, planID)
}

// ListActions returns one bounded page of the plan's safe action graph.
func (c DeclarativeConfigurationClient) ListActions(ctx context.Context, stackKey, planID string, query OpenAPIListPostGripConfigurationPlanActionsQuery) (OpenAPIListPostGripConfigurationPlanActionsResponseBody, error) {
	return c.client.OpenAPI().ListPostGripConfigurationPlanActions(ctx, stackKey, planID, query)
}

// Apply starts a durable aggregate operation for an accepted plan.
func (c DeclarativeConfigurationClient) Apply(ctx context.Context, stackKey, planID string, body OpenAPIApplyPostGripConfigurationPlanRequestBody, options MutationOptions) (OpenAPIApplyPostGripConfigurationPlanResponseBody, error) {
	if err := validateIdempotencyKey(options.IdempotencyKey); err != nil {
		return OpenAPIApplyPostGripConfigurationPlanResponseBody{}, err
	}
	return c.client.OpenAPI().ApplyPostGripConfigurationPlan(ctx, stackKey, planID, OpenAPIApplyPostGripConfigurationPlanHeaders{IdempotencyKey: options.IdempotencyKey}, body)
}

// GetOperation returns the current state of a durable stack operation.
func (c DeclarativeConfigurationClient) GetOperation(ctx context.Context, stackKey, operationID string) (OpenAPIGetPostGripConfigurationStackOperationResponseBody, error) {
	return c.client.OpenAPI().GetPostGripConfigurationStackOperation(ctx, stackKey, operationID)
}

// ListOperationActions returns one bounded page of aggregate operation actions.
func (c DeclarativeConfigurationClient) ListOperationActions(ctx context.Context, stackKey, operationID string, query OpenAPIListPostGripConfigurationStackOperationActionsQuery) (OpenAPIListPostGripConfigurationStackOperationActionsResponseBody, error) {
	return c.client.OpenAPI().ListPostGripConfigurationStackOperationActions(ctx, stackKey, operationID, query)
}

// RetryOperation resumes a failed or blocked operation behind its ETag fence.
func (c DeclarativeConfigurationClient) RetryOperation(ctx context.Context, stackKey, operationID string, options WriteOptions) (OpenAPIRetryPostGripConfigurationStackOperationResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIRetryPostGripConfigurationStackOperationResponseBody{}, err
	}
	return c.client.OpenAPI().RetryPostGripConfigurationStackOperation(ctx, stackKey, operationID, OpenAPIRetryPostGripConfigurationStackOperationHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch})
}

// ResubmitSecretInputs replaces only expired secret envelopes behind an ETag fence.
func (c DeclarativeConfigurationClient) ResubmitSecretInputs(ctx context.Context, stackKey, operationID string, body OpenAPIResubmitPostGripConfigurationSecretInputsRequestBody, options WriteOptions) (OpenAPIResubmitPostGripConfigurationSecretInputsResponseBody, error) {
	if err := options.validate(true); err != nil {
		return OpenAPIResubmitPostGripConfigurationSecretInputsResponseBody{}, err
	}
	return c.client.OpenAPI().ResubmitPostGripConfigurationSecretInputs(ctx, stackKey, operationID, OpenAPIResubmitPostGripConfigurationSecretInputsHeaders{IdempotencyKey: options.IdempotencyKey, IfMatch: options.IfMatch}, body)
}
