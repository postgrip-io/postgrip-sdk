# Service API

Contract digest: `08309318d5a9624cb4447f01417077eed5c1f0d21f02bcfe8c9c6f386ccd8a30`
Bundle digest: `e53278e3f9a421f682e65bf9f84baa0bb8f76225cd317197eb522ff567505650`

## Administration

- [`adoptGitHubRepository`](./adoptGitHubRepository.md) — Adopt an authorized GitHub App repository
- [`applyPostGripConfigurationPlan`](./applyPostGripConfigurationPlan.md) — Apply an accepted declarative configuration plan
- [`applyServiceVariables`](./applyServiceVariables.md) — Apply Service Variables
- [`attachTargetService`](./attachTargetService.md) — Attach Target Service
- [`bindServiceVolume`](./bindServiceVolume.md) — Bind Service Volume
- [`clearServiceRepositoryCredential`](./clearServiceRepositoryCredential.md) — Clear Service Repository Credential
- [`clearServiceVariableValue`](./clearServiceVariableValue.md) — Clear Service Variable Value
- [`clearTargetServiceConnection`](./clearTargetServiceConnection.md) — Clear Target Service Connection
- [`createPostGripConfigurationPlan`](./createPostGripConfigurationPlan.md) — Create a deterministic declarative configuration plan
- [`createServiceDomain`](./createServiceDomain.md) — Create Service Domain
- [`createServiceEnvironment`](./createServiceEnvironment.md) — Create Service Environment
- [`createServiceProject`](./createServiceProject.md) — Create Service Project
- [`createServiceVariable`](./createServiceVariable.md) — Create Service Variable
- [`createServiceVolume`](./createServiceVolume.md) — Create Service Volume
- [`deleteServiceDomain`](./deleteServiceDomain.md) — Delete Service Domain
- [`deleteServiceEnvironment`](./deleteServiceEnvironment.md) — Delete Service Environment
- [`deleteServiceProject`](./deleteServiceProject.md) — Delete Service Project
- [`deleteServiceVariable`](./deleteServiceVariable.md) — Delete Service Variable
- [`deleteServiceVolume`](./deleteServiceVolume.md) — Delete Service Volume
- [`detachTargetService`](./detachTargetService.md) — Detach Target Service
- [`flushServiceBuildLogs`](./flushServiceBuildLogs.md) — Flush Service Build Logs
- [`flushServiceRuntimeLogs`](./flushServiceRuntimeLogs.md) — Flush Service Runtime Logs
- [`getPostGripConfigurationPlan`](./getPostGripConfigurationPlan.md) — Get declarative configuration plan metadata
- [`getPostGripConfigurationStack`](./getPostGripConfigurationStack.md) — Get declarative configuration stack state
- [`getPostGripConfigurationStackOperation`](./getPostGripConfigurationStackOperation.md) — Get a declarative configuration operation
- [`getServiceBuildLogSettings`](./getServiceBuildLogSettings.md) — Get Service Build Log Settings
- [`getServiceConfigurationOperation`](./getServiceConfigurationOperation.md) — Get Service Configuration Operation
- [`getServiceDNSCanonicalState`](./getServiceDNSCanonicalState.md) — Get canonical DNS and failover state
- [`getServiceDNSFailoverPolicy`](./getServiceDNSFailoverPolicy.md) — Get the canonical DNS failover policy
- [`getServiceDNSPlan`](./getServiceDNSPlan.md) — Get a provider-neutral DNS plan
- [`getServiceDomainVerification`](./getServiceDomainVerification.md) — Get the latest public Service domain verification
- [`getServiceEnvironment`](./getServiceEnvironment.md) — Get Service Environment
- [`getServiceEnvironmentRemovalImpact`](./getServiceEnvironmentRemovalImpact.md) — Get Service Environment Removal Impact
- [`getServiceProjectRemovalImpact`](./getServiceProjectRemovalImpact.md) — Get Service Project Removal Impact
- [`getServiceRepository`](./getServiceRepository.md) — Get Service Repository
- [`getServiceRuntimeLogSettings`](./getServiceRuntimeLogSettings.md) — Get Service Runtime Log Settings
- [`getServiceVolume`](./getServiceVolume.md) — Get Service Volume
- [`getServiceVolumeRemovalImpact`](./getServiceVolumeRemovalImpact.md) — Get Service Volume Removal Impact
- [`getTargetServiceRemovalImpact`](./getTargetServiceRemovalImpact.md) — Get Target Service Removal Impact
- [`listGitHubAppRepositories`](./listGitHubAppRepositories.md) — List repositories authorized for GitHub App adoption
- [`listPostGripConfigurationPlanActions`](./listPostGripConfigurationPlanActions.md) — List declarative configuration plan actions
- [`listPostGripConfigurationStackOperationActions`](./listPostGripConfigurationStackOperationActions.md) — List declarative configuration operation actions
- [`listServiceConfigurationOperations`](./listServiceConfigurationOperations.md) — List Service Configuration Operations
- [`listServiceDNSPlans`](./listServiceDNSPlans.md) — List canonical DNS plan history
- [`listServiceDomains`](./listServiceDomains.md) — List Service Domains
- [`listServicePromotions`](./listServicePromotions.md) — List Service Promotions
- [`listServiceVariables`](./listServiceVariables.md) — List Service Variables
- [`listServiceVolumes`](./listServiceVolumes.md) — List Service Volumes
- [`previewGitHubRepositoryAdoption`](./previewGitHubRepositoryAdoption.md) — Preview GitHub App repository adoption
- [`previewServiceEnvironmentReassignment`](./previewServiceEnvironmentReassignment.md) — Preview Service Environment Reassignment
- [`previewServicePromotion`](./previewServicePromotion.md) — Preview Service Promotion
- [`promoteServiceDeployment`](./promoteServiceDeployment.md) — Promote Service Deployment
- [`putServiceRepositoryCredential`](./putServiceRepositoryCredential.md) — Put Service Repository Credential
- [`putServiceVariableValue`](./putServiceVariableValue.md) — Put Service Variable Value
- [`putTargetServiceConnection`](./putTargetServiceConnection.md) — Put Target Service Connection
- [`reassignServiceEnvironment`](./reassignServiceEnvironment.md) — Reassign Service Environment
- [`refreshServiceRepositoryCredential`](./refreshServiceRepositoryCredential.md) — Refresh Service Repository Credential
- [`resubmitPostGripConfigurationSecretInputs`](./resubmitPostGripConfigurationSecretInputs.md) — Resubmit expired declarative secret inputs
- [`retryPostGripConfigurationStackOperation`](./retryPostGripConfigurationStackOperation.md) — Retry a declarative configuration operation
- [`retryServiceConfigurationOperation`](./retryServiceConfigurationOperation.md) — Retry Service Configuration Operation
- [`trimServiceBuildLogs`](./trimServiceBuildLogs.md) — Trim Service Build Logs
- [`trimServiceRuntimeLogs`](./trimServiceRuntimeLogs.md) — Trim Service Runtime Logs
- [`unbindServiceVolume`](./unbindServiceVolume.md) — Unbind Service Volume
- [`updateServiceBuildLogSettings`](./updateServiceBuildLogSettings.md) — Update Service Build Log Settings
- [`updateServiceDNSFailoverPolicy`](./updateServiceDNSFailoverPolicy.md) — Configure bounded canonical DNS failover
- [`updateServiceDomain`](./updateServiceDomain.md) — Update Service Domain
- [`updateServiceEnvironment`](./updateServiceEnvironment.md) — Update Service Environment
- [`updateServiceProject`](./updateServiceProject.md) — Update Service Project
- [`updateServiceRepository`](./updateServiceRepository.md) — Update Service Repository
- [`updateServiceRuntimeLogSettings`](./updateServiceRuntimeLogSettings.md) — Update Service Runtime Log Settings
- [`updateServiceVariable`](./updateServiceVariable.md) — Update Service Variable
- [`updateServiceVolumeBinding`](./updateServiceVolumeBinding.md) — Update Service Volume Binding
- [`updateTargetService`](./updateTargetService.md) — Update Target Service
- [`validatePostGripConfiguration`](./validatePostGripConfiguration.md) — Validate declarative configuration against tenant state

## Applications

- [`createServiceApp`](./createServiceApp.md) — Create a service application grouping
- [`deleteServiceApp`](./deleteServiceApp.md) — Delete a service application grouping
- [`getServiceApp`](./getServiceApp.md) — Get a service application grouping
- [`listServiceApps`](./listServiceApps.md) — List service application groupings
- [`updateServiceApp`](./updateServiceApp.md) — Replace a service application grouping

## Configuration

- [`deleteServiceComposeFile`](./deleteServiceComposeFile.md) — Delete an environment Compose override
- [`exportServiceVariables`](./exportServiceVariables.md) — Export non-secret environment variables
- [`getServiceComposeFile`](./getServiceComposeFile.md) — Get an environment Compose override
- [`putServiceComposeFile`](./putServiceComposeFile.md) — Replace an environment Compose override

## Deployments

- [`getServiceDeployment`](./getServiceDeployment.md) — Get a service deployment
- [`getServiceDeploymentScreenshot`](./getServiceDeploymentScreenshot.md) — Get a deployment browser-check screenshot
- [`listServiceDeployments`](./listServiceDeployments.md) — List service deployments
- [`listServiceWebhookDispatchEvents`](./listServiceWebhookDispatchEvents.md) — List service webhook dispatch events

## Environments

- [`listServiceEnvironments`](./listServiceEnvironments.md) — List service environments
- [`resolveServiceEnvironment`](./resolveServiceEnvironment.md) — Resolve an exact service environment ID or name

## Logs

- [`listServiceLogs`](./listServiceLogs.md) — List build or runtime logs

## Observability

- [`flushServiceTraffic`](./flushServiceTraffic.md) — Flush service traffic telemetry
- [`getServiceTrafficReport`](./getServiceTrafficReport.md) — Get a service traffic report
- [`getServiceTrafficStatus`](./getServiceTrafficStatus.md) — Get service traffic status
- [`putServiceTrafficSettings`](./putServiceTrafficSettings.md) — Update service traffic settings
- [`trimServiceTraffic`](./trimServiceTraffic.md) — Trim service traffic telemetry

## Operations

- [`applyServiceDNSPlan`](./applyServiceDNSPlan.md) — Release a fenced DNS plan for external apply
- [`cancelServiceDeployment`](./cancelServiceDeployment.md) — Cancel a queued service deployment
- [`checkService`](./checkService.md) — Probe a target or deployed service
- [`createServiceDNSPlan`](./createServiceDNSPlan.md) — Preview an immutable provider-neutral DNS plan
- [`deployService`](./deployService.md) — Queue a deployment for a confirmed commit
- [`previewServiceDeploy`](./previewServiceDeploy.md) — Resolve a deploy request to an immutable commit
- [`redeployService`](./redeployService.md) — Queue a deployment from an existing immutable revision
- [`reportServiceDNSProviderResult`](./reportServiceDNSProviderResult.md) — Report an exact external DNS provider result
- [`requestServiceDNSFailover`](./requestServiceDNSFailover.md) — Request a bounded canonical DNS failover
- [`restartServiceRuntime`](./restartServiceRuntime.md) — Restart the exact current service runtime
- [`rollbackServiceDNSPlan`](./rollbackServiceDNSPlan.md) — Plan rollback to the last verified DNS target
- [`rollbackServiceDeployment`](./rollbackServiceDeployment.md) — Queue rollback to a historical service deployment
- [`startServiceRuntime`](./startServiceRuntime.md) — Start the exact current service runtime
- [`stopServiceRuntime`](./stopServiceRuntime.md) — Stop the exact current service runtime
- [`verifyServiceDomain`](./verifyServiceDomain.md) — Verify public Service domain routing

## Release Groups

- [`cancelServiceReleaseGroup`](./cancelServiceReleaseGroup.md) — Cancel and compensate a release group
- [`createServiceReleaseGroup`](./createServiceReleaseGroup.md) — Create a coordinated release group
- [`getServiceReleaseGroup`](./getServiceReleaseGroup.md) — Get coordinated release state
- [`listServiceReleaseGroupEvents`](./listServiceReleaseGroupEvents.md) — List coordinated release events
- [`listServiceReleaseGroups`](./listServiceReleaseGroups.md) — List coordinated release groups
- [`previewServiceReleaseGroup`](./previewServiceReleaseGroup.md) — Preview a fenced multi-project release
- [`retryServiceReleaseGroup`](./retryServiceReleaseGroup.md) — Retry a safely recovered release group

## Repositories

- [`checkServiceGitHubRepositoryFile`](./checkServiceGitHubRepositoryFile.md) — Check a GitHub repository file
- [`listServiceGitHubBranches`](./listServiceGitHubBranches.md) — List GitHub repository branches

## Services

- [`getService`](./getService.md) — Get a service and its capabilities
- [`getServiceStatus`](./getServiceStatus.md) — Get last-known service and environment status
- [`listServices`](./listServices.md) — List services
- [`resolveService`](./resolveService.md) — Resolve an exact service reference, ID, or name
