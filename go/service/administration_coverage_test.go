package service

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync/atomic"
	"testing"
)

func serviceResultError[T any](_ T, err error) error { return err }

func mustServiceResult(t *testing.T, err error) {
	t.Helper()
	if err != nil {
		t.Fatal(err)
	}
}

func TestEveryAdministrationFacadeExecutesThroughTheTransport(t *testing.T) {
	t.Parallel()
	var calls atomic.Int32
	client := newTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		if r.Header.Get("Authorization") != "Bearer pgt_test-token" {
			t.Fatalf("authorization=%q", r.Header.Get("Authorization"))
		}
		if r.Method != http.MethodGet && r.URL.Path != "/api/v1/services/configuration/validate" && r.URL.Path != "/api/v1/services/release-groups/preview" && r.Header.Get("Idempotency-Key") != "operation-1" {
			t.Fatalf("idempotency=%q for %s", r.Header.Get("Idempotency-Key"), r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		if strings.HasSuffix(r.URL.Path, "/variables/export") || strings.HasSuffix(r.URL.Path, "/webhook-events") || strings.HasSuffix(r.URL.Path, "/integrations/github/branches") {
			_, _ = fmt.Fprint(w, `[]`)
			return
		}
		_, _ = fmt.Fprint(w, `{}`)
	}), nil)
	ctx := context.Background()
	write := WriteOptions{IdempotencyKey: "operation-1", IfMatch: `"etag:1"`}
	mutation := MutationOptions{IdempotencyKey: "operation-1"}
	repositoryID := int64(1)

	apps := client.Apps()
	mustServiceResult(t, serviceResultError(apps.List(ctx)))
	mustServiceResult(t, serviceResultError(apps.Get(ctx, "app-1")))
	mustServiceResult(t, serviceResultError(apps.Create(ctx, OpenAPICreateServiceAppRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(apps.Update(ctx, "app-1", OpenAPIUpdateServiceAppRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(apps.Delete(ctx, "app-1", write)))

	targets := client.TargetServices()
	mustServiceResult(t, serviceResultError(targets.Attach(ctx, OpenAPIAttachTargetServiceRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(targets.Update(ctx, "target-1", OpenAPIUpdateTargetServiceRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(targets.RemovalImpact(ctx, "target-1")))
	mustServiceResult(t, serviceResultError(targets.Detach(ctx, "target-1", OpenAPIDetachTargetServiceRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(targets.PutConnection(ctx, "target-1", OpenAPIPutTargetServiceConnectionRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(targets.ClearConnection(ctx, "target-1", write)))

	projects := client.Projects()
	mustServiceResult(t, serviceResultError(projects.Create(ctx, OpenAPICreateServiceProjectRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(projects.Update(ctx, "project-1", OpenAPIUpdateServiceProjectRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(projects.RemovalImpact(ctx, "project-1")))
	mustServiceResult(t, serviceResultError(projects.Delete(ctx, "project-1", OpenAPIDeleteServiceProjectRequestBody{}, write)))

	environments := client.EnvironmentAdministration()
	mustServiceResult(t, serviceResultError(environments.Get(ctx, "project-1", "environment-1")))
	mustServiceResult(t, serviceResultError(environments.Create(ctx, "project-1", OpenAPICreateServiceEnvironmentRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(environments.Update(ctx, "project-1", "environment-1", OpenAPIUpdateServiceEnvironmentRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(environments.PreviewReassignment(ctx, "project-1", "environment-1", OpenAPIPreviewServiceEnvironmentReassignmentRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(environments.Reassign(ctx, "project-1", "environment-1", OpenAPIReassignServiceEnvironmentRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(environments.RecoveryMove(ctx, "project-1", "environment-1", "move-1")))
	mustServiceResult(t, serviceResultError(environments.ReviseRecoveryMoveVolume(ctx, "project-1", "environment-1", "move-1", "volume-1", OpenAPIReviseRecoveryMoveVolumeRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(environments.ConfirmRecoveryMoveVariables(ctx, "project-1", "environment-1", "move-1", write)))
	mustServiceResult(t, serviceResultError(environments.RemovalImpact(ctx, "project-1", "environment-1")))
	mustServiceResult(t, serviceResultError(environments.Delete(ctx, "project-1", "environment-1", OpenAPIDeleteServiceEnvironmentRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(environments.GetCompose(ctx, "project-1", "environment-1")))
	mustServiceResult(t, serviceResultError(environments.PutCompose(ctx, "project-1", "environment-1", OpenAPIPutServiceComposeFileRequestBody{}, mutation)))
	mustServiceResult(t, serviceResultError(environments.DeleteCompose(ctx, "project-1", "environment-1", mutation)))

	volumes := client.ManagedVolumes()
	mustServiceResult(t, serviceResultError(volumes.List(ctx, "project-1")))
	mustServiceResult(t, serviceResultError(volumes.Create(ctx, "project-1", OpenAPICreateServiceVolumeRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(volumes.Get(ctx, "project-1", "volume-1")))
	mustServiceResult(t, serviceResultError(volumes.RemovalImpact(ctx, "project-1", "volume-1")))
	mustServiceResult(t, serviceResultError(volumes.Delete(ctx, "project-1", "volume-1", OpenAPIDeleteServiceVolumeRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(volumes.Bind(ctx, "project-1", "environment-1", OpenAPIBindServiceVolumeRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(volumes.UpdateBinding(ctx, "project-1", "environment-1", "volume-1", OpenAPIUpdateServiceVolumeBindingRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(volumes.Unbind(ctx, "project-1", "environment-1", "volume-1", write)))

	domains := client.ServiceDomains()
	mustServiceResult(t, serviceResultError(domains.List(ctx, "project-1", "environment-1")))
	mustServiceResult(t, serviceResultError(domains.Create(ctx, "project-1", "environment-1", OpenAPICreateServiceDomainRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(domains.Update(ctx, "project-1", "environment-1", "domain-1", OpenAPIUpdateServiceDomainRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(domains.Delete(ctx, "project-1", "environment-1", "domain-1", write)))
	mustServiceResult(t, serviceResultError(domains.Verification(ctx, "project-1", "environment-1", "domain-1")))
	mustServiceResult(t, serviceResultError(domains.Verify(ctx, "project-1", "environment-1", "domain-1", mutation)))

	dns := client.ServiceDNS()
	mustServiceResult(t, serviceResultError(dns.CanonicalState(ctx, "project-1", "environment-1", "domain-1")))
	mustServiceResult(t, serviceResultError(dns.Plans(ctx, "project-1", "environment-1", "domain-1")))
	mustServiceResult(t, serviceResultError(dns.CreatePlan(ctx, "project-1", "environment-1", "domain-1", OpenAPICreateServiceDNSPlanRequestBody{}, mutation)))
	mustServiceResult(t, serviceResultError(dns.Plan(ctx, "project-1", "environment-1", "domain-1", "plan-1")))
	mustServiceResult(t, serviceResultError(dns.Apply(ctx, "project-1", "environment-1", "domain-1", "plan-1", OpenAPIApplyServiceDNSPlanRequestBody{}, mutation)))
	mustServiceResult(t, serviceResultError(dns.ReportProviderResult(ctx, "project-1", "environment-1", "domain-1", "plan-1", OpenAPIReportServiceDNSProviderResultRequestBody{}, mutation)))

	variables := client.ServiceVariables()
	mustServiceResult(t, serviceResultError(variables.List(ctx, "project-1", "environment-1")))
	mustServiceResult(t, serviceResultError(variables.Create(ctx, "project-1", "environment-1", OpenAPICreateServiceVariableRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(variables.Update(ctx, "project-1", "environment-1", "variable-1", OpenAPIUpdateServiceVariableRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(variables.Delete(ctx, "project-1", "environment-1", "variable-1", write)))
	mustServiceResult(t, serviceResultError(variables.PutValue(ctx, "project-1", "environment-1", "variable-1", OpenAPIPutServiceVariableValueRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(variables.ClearValue(ctx, "project-1", "environment-1", "variable-1", write)))
	mustServiceResult(t, serviceResultError(variables.Apply(ctx, "project-1", OpenAPIApplyServiceVariablesRequestBody{}, mutation)))
	mustServiceResult(t, serviceResultError(variables.Export(ctx, "project-1", "environment-1")))

	repositories := client.ServiceRepositories()
	mustServiceResult(t, serviceResultError(repositories.Get(ctx, "project-1")))
	mustServiceResult(t, serviceResultError(repositories.Update(ctx, "project-1", OpenAPIUpdateServiceRepositoryRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(repositories.PutCredential(ctx, "project-1", "source-access", OpenAPIPutServiceRepositoryCredentialRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(repositories.ClearCredential(ctx, "project-1", "source-access", write)))
	mustServiceResult(t, serviceResultError(repositories.RefreshCredential(ctx, "project-1", "source-access", write)))
	mustServiceResult(t, serviceResultError(repositories.ListGitHub(ctx, OpenAPIListGitHubAppRepositoriesQuery{})))
	mustServiceResult(t, serviceResultError(repositories.ListGitHubAccounts(ctx)))
	mustServiceResult(t, serviceResultError(repositories.PreviewGitHubAdoption(ctx, "project-1", OpenAPIPreviewGitHubRepositoryAdoptionRequestBody{RepositoryId: &repositoryID}, mutation)))
	mustServiceResult(t, serviceResultError(repositories.AdoptGitHub(ctx, "project-1", OpenAPIAdoptGitHubRepositoryRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(repositories.GitHubBranches(ctx, OpenAPIListServiceGitHubBranchesQuery{})))
	mustServiceResult(t, serviceResultError(repositories.GitHubFile(ctx, OpenAPICheckServiceGitHubRepositoryFileQuery{})))

	promotions := client.ServicePromotions()
	mustServiceResult(t, serviceResultError(promotions.List(ctx, "project-1", OpenAPIListServicePromotionsQuery{})))
	mustServiceResult(t, serviceResultError(promotions.Preview(ctx, "project-1", OpenAPIPreviewServicePromotionQuery{})))
	mustServiceResult(t, serviceResultError(promotions.Create(ctx, "project-1", OpenAPIPromoteServiceDeploymentRequestBody{}, write)))

	releaseGroups := client.ServiceReleaseGroups()
	mustServiceResult(t, serviceResultError(releaseGroups.List(ctx, OpenAPIListServiceReleaseGroupsQuery{})))
	mustServiceResult(t, serviceResultError(releaseGroups.Preview(ctx, OpenAPIPreviewServiceReleaseGroupRequestBody{})))
	mustServiceResult(t, serviceResultError(releaseGroups.Create(ctx, OpenAPICreateServiceReleaseGroupRequestBody{}, mutation)))
	mustServiceResult(t, serviceResultError(releaseGroups.Get(ctx, "release-group-1")))
	mustServiceResult(t, serviceResultError(releaseGroups.Events(ctx, "release-group-1", OpenAPIListServiceReleaseGroupEventsQuery{})))
	mustServiceResult(t, serviceResultError(releaseGroups.Cancel(ctx, "release-group-1", mutation)))
	mustServiceResult(t, serviceResultError(releaseGroups.Retry(ctx, "release-group-1", mutation)))

	retention := client.ServiceRetention()
	mustServiceResult(t, serviceResultError(retention.GetBuild(ctx, "project-1")))
	mustServiceResult(t, serviceResultError(retention.UpdateBuild(ctx, "project-1", OpenAPIUpdateServiceBuildLogSettingsRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(retention.TrimBuild(ctx, "project-1", OpenAPITrimServiceBuildLogsQuery{}, write)))
	mustServiceResult(t, serviceResultError(retention.FlushBuild(ctx, "project-1", OpenAPIFlushServiceBuildLogsQuery{}, write)))
	mustServiceResult(t, serviceResultError(retention.GetRuntime(ctx, "project-1", OpenAPIGetServiceRuntimeLogSettingsQuery{})))
	mustServiceResult(t, serviceResultError(retention.UpdateRuntime(ctx, "project-1", OpenAPIUpdateServiceRuntimeLogSettingsRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(retention.TrimRuntime(ctx, "project-1", OpenAPITrimServiceRuntimeLogsQuery{}, write)))
	mustServiceResult(t, serviceResultError(retention.FlushRuntime(ctx, "project-1", OpenAPIFlushServiceRuntimeLogsQuery{}, write)))

	operations := client.ServiceConfigurationOperations()
	mustServiceResult(t, serviceResultError(operations.List(ctx, OpenAPIListServiceConfigurationOperationsQuery{})))
	mustServiceResult(t, serviceResultError(operations.Get(ctx, "operation-1")))
	mustServiceResult(t, serviceResultError(operations.Retry(ctx, "operation-1", write)))
	mustServiceResult(t, serviceResultError(operations.Abandon(ctx, "operation-1", write)))

	configuration := client.DeclarativeConfiguration()
	mustServiceResult(t, serviceResultError(configuration.Validate(ctx, OpenAPIValidatePostGripConfigurationRequestBody{})))
	mustServiceResult(t, serviceResultError(configuration.GetStack(ctx, "stack-1")))
	mustServiceResult(t, serviceResultError(configuration.CreatePlan(ctx, "stack-1", OpenAPICreatePostGripConfigurationPlanRequestBody{}, mutation)))
	mustServiceResult(t, serviceResultError(configuration.GetPlan(ctx, "stack-1", "plan-1")))
	mustServiceResult(t, serviceResultError(configuration.ListActions(ctx, "stack-1", "plan-1", OpenAPIListPostGripConfigurationPlanActionsQuery{})))
	mustServiceResult(t, serviceResultError(configuration.Apply(ctx, "stack-1", "plan-1", OpenAPIApplyPostGripConfigurationPlanRequestBody{}, mutation)))
	mustServiceResult(t, serviceResultError(configuration.GetOperation(ctx, "stack-1", "operation-1")))
	mustServiceResult(t, serviceResultError(configuration.ListOperationActions(ctx, "stack-1", "operation-1", OpenAPIListPostGripConfigurationStackOperationActionsQuery{})))
	mustServiceResult(t, serviceResultError(configuration.RetryOperation(ctx, "stack-1", "operation-1", write)))
	mustServiceResult(t, serviceResultError(configuration.ResubmitSecretInputs(ctx, "stack-1", "operation-1", OpenAPIResubmitPostGripConfigurationSecretInputsRequestBody{}, write)))

	diagnostics := client.ServiceDiagnostics()
	mustServiceResult(t, serviceResultError(diagnostics.Screenshot(ctx, "project-1", "deployment-1")))
	mustServiceResult(t, serviceResultError(diagnostics.WebhookEvents(ctx, "project-1", OpenAPIListServiceWebhookDispatchEventsQuery{})))

	traffic := client.ServiceTraffic()
	mustServiceResult(t, serviceResultError(traffic.Status(ctx, "project-1", OpenAPIGetServiceTrafficStatusQuery{})))
	mustServiceResult(t, serviceResultError(traffic.Report(ctx, "project-1", OpenAPIGetServiceTrafficReportQuery{})))
	mustServiceResult(t, serviceResultError(traffic.UpdateSettings(ctx, "project-1", OpenAPIPutServiceTrafficSettingsRequestBody{}, mutation)))
	mustServiceResult(t, serviceResultError(traffic.Trim(ctx, "project-1", OpenAPITrimServiceTrafficQuery{}, mutation)))
	mustServiceResult(t, serviceResultError(traffic.Flush(ctx, "project-1", OpenAPIFlushServiceTrafficQuery{}, mutation)))

	if calls.Load() != 106 {
		t.Fatalf("transport calls=%d, want 106", calls.Load())
	}
}

func TestAdministrationWriteOptionsRejectUnsafeFencesBeforeTransport(t *testing.T) {
	t.Parallel()
	var calls atomic.Int32
	client := newTestClient(t, http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		calls.Add(1)
	}), nil)
	for _, options := range []WriteOptions{
		{IdempotencyKey: "", IfMatch: `"etag:1"`},
		{IdempotencyKey: "operation-1", IfMatch: ""},
		{IdempotencyKey: "operation-1", IfMatch: "etag\r\nInjected: true"},
	} {
		if _, err := client.Projects().Update(context.Background(), "project-1", OpenAPIUpdateServiceProjectRequestBody{}, options); err == nil {
			t.Fatalf("unsafe options accepted: %#v", options)
		}
	}
	if calls.Load() != 0 {
		t.Fatalf("unsafe options made %d requests", calls.Load())
	}
}

func TestEnvironmentAndDeploymentPagersPreserveOpaqueCursors(t *testing.T) {
	t.Parallel()
	var environmentCalls, deploymentCalls atomic.Int32
	client := newTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/api/v1/services/project/project-1/environments":
			if environmentCalls.Add(1) == 1 {
				_, _ = fmt.Fprint(w, `{"items":[],"nextCursor":"environment-next"}`)
				return
			}
			if r.URL.Query().Get("cursor") != "environment-next" {
				t.Fatalf("environment cursor=%q", r.URL.Query().Get("cursor"))
			}
			_, _ = fmt.Fprint(w, `{"items":[],"nextCursor":""}`)
		case r.URL.Path == "/api/v1/services/project/project-1/deployments":
			if deploymentCalls.Add(1) == 1 {
				_, _ = fmt.Fprint(w, `{"items":[],"nextCursor":"deployment-next"}`)
				return
			}
			if r.URL.Query().Get("cursor") != "deployment-next" {
				t.Fatalf("deployment cursor=%q", r.URL.Query().Get("cursor"))
			}
			_, _ = fmt.Fprint(w, `{"items":[],"nextCursor":""}`)
		default:
			t.Fatalf("unexpected path=%s", r.URL.Path)
		}
	}), nil)
	ref := Reference{Source: OpenAPIServiceSourceProject, ID: "project-1"}
	environments := client.ServiceEnvironments(ref, OpenAPIListServiceEnvironmentsQuery{})
	if !environments.Next(context.Background()) || !environments.Next(context.Background()) || environments.Next(context.Background()) || environments.Err() != nil {
		t.Fatalf("environment pager err=%v", environments.Err())
	}
	deployments := client.ServiceDeployments(ref, OpenAPIListServiceDeploymentsQuery{})
	if !deployments.Next(context.Background()) || !deployments.Next(context.Background()) || deployments.Next(context.Background()) || deployments.Err() != nil {
		t.Fatalf("deployment pager err=%v", deployments.Err())
	}
}

func TestTargetServicePutConnectionSendsTheHTTPCredentialAsGiven(t *testing.T) {
	t.Parallel()
	var got atomic.Value
	client := newTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPut || r.URL.Path != "/api/v1/services/target/target-1/connection" {
			t.Errorf("request=%s %s", r.Method, r.URL.Path)
		}
		if r.Header.Get("Idempotency-Key") != "connection-1" || r.Header.Get("If-Match") != `"target:3"` {
			t.Errorf("fences=%q %q", r.Header.Get("Idempotency-Key"), r.Header.Get("If-Match"))
		}
		body, _ := io.ReadAll(r.Body)
		got.Store(string(body))
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprint(w, `{"target":{"httpAuth":{"scheme":"api_key","headerName":"X-API-Key"}}}`)
	}), nil)
	headerName, value := "X-API-Key", "key-value"
	response, err := client.TargetServices().PutConnection(context.Background(), "target-1", OpenAPIPutTargetServiceConnectionRequestBody{
		Http: &TargetServiceHTTPCredential{Scheme: "api_key", HeaderName: &headerName, Value: &value},
	}, WriteOptions{IdempotencyKey: "connection-1", IfMatch: `"target:3"`})
	if err != nil {
		t.Fatal(err)
	}
	if body := got.Load(); body != `{"http":{"scheme":"api_key","headerName":"X-API-Key","value":"key-value"}}` {
		t.Fatalf("body=%v", body)
	}
	auth := response.Target.HttpAuth
	if auth == nil || auth.Scheme != "api_key" || auth.HeaderName == nil || *auth.HeaderName != "X-API-Key" || auth.Username != nil {
		t.Fatalf("httpAuth=%+v", auth)
	}

	password := "secret"
	if _, err := client.TargetServices().PutConnection(context.Background(), "target-1", OpenAPIPutTargetServiceConnectionRequestBody{Password: &password}, WriteOptions{IdempotencyKey: "connection-1", IfMatch: `"target:3"`}); err != nil {
		t.Fatal(err)
	}
	if body := got.Load(); body != `{"password":"secret"}` {
		t.Fatalf("password body=%v", body)
	}
}
