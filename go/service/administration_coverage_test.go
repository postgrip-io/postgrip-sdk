package service

import (
	"context"
	"fmt"
	"net/http"
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
		if r.Method != http.MethodGet && r.Header.Get("Idempotency-Key") != "operation-1" {
			t.Fatalf("idempotency=%q for %s", r.Header.Get("Idempotency-Key"), r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprint(w, `{}`)
	}), nil)
	ctx := context.Background()
	write := WriteOptions{IdempotencyKey: "operation-1", IfMatch: `"etag:1"`}
	mutation := MutationOptions{IdempotencyKey: "operation-1"}

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
	mustServiceResult(t, serviceResultError(environments.RemovalImpact(ctx, "project-1", "environment-1")))
	mustServiceResult(t, serviceResultError(environments.Delete(ctx, "project-1", "environment-1", OpenAPIDeleteServiceEnvironmentRequestBody{}, write)))

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

	variables := client.ServiceVariables()
	mustServiceResult(t, serviceResultError(variables.List(ctx, "project-1", "environment-1")))
	mustServiceResult(t, serviceResultError(variables.Create(ctx, "project-1", "environment-1", OpenAPICreateServiceVariableRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(variables.Update(ctx, "project-1", "environment-1", "variable-1", OpenAPIUpdateServiceVariableRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(variables.Delete(ctx, "project-1", "environment-1", "variable-1", write)))
	mustServiceResult(t, serviceResultError(variables.PutValue(ctx, "project-1", "environment-1", "variable-1", OpenAPIPutServiceVariableValueRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(variables.ClearValue(ctx, "project-1", "environment-1", "variable-1", write)))
	mustServiceResult(t, serviceResultError(variables.Apply(ctx, "project-1", OpenAPIApplyServiceVariablesRequestBody{}, mutation)))

	repositories := client.ServiceRepositories()
	mustServiceResult(t, serviceResultError(repositories.Get(ctx, "project-1")))
	mustServiceResult(t, serviceResultError(repositories.Update(ctx, "project-1", OpenAPIUpdateServiceRepositoryRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(repositories.PutCredential(ctx, "project-1", "source-access", OpenAPIPutServiceRepositoryCredentialRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(repositories.ClearCredential(ctx, "project-1", "source-access", write)))
	mustServiceResult(t, serviceResultError(repositories.RefreshCredential(ctx, "project-1", "source-access", write)))

	promotions := client.ServicePromotions()
	mustServiceResult(t, serviceResultError(promotions.List(ctx, "project-1", OpenAPIListServicePromotionsQuery{})))
	mustServiceResult(t, serviceResultError(promotions.Preview(ctx, "project-1", OpenAPIPreviewServicePromotionQuery{})))
	mustServiceResult(t, serviceResultError(promotions.Create(ctx, "project-1", OpenAPIPromoteServiceDeploymentRequestBody{}, write)))

	retention := client.ServiceRetention()
	mustServiceResult(t, serviceResultError(retention.GetBuild(ctx, "project-1")))
	mustServiceResult(t, serviceResultError(retention.UpdateBuild(ctx, "project-1", OpenAPIUpdateServiceBuildLogSettingsRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(retention.TrimBuild(ctx, "project-1", write)))
	mustServiceResult(t, serviceResultError(retention.FlushBuild(ctx, "project-1", write)))
	mustServiceResult(t, serviceResultError(retention.GetRuntime(ctx, "project-1", OpenAPIGetServiceRuntimeLogSettingsQuery{})))
	mustServiceResult(t, serviceResultError(retention.UpdateRuntime(ctx, "project-1", OpenAPIUpdateServiceRuntimeLogSettingsQuery{}, OpenAPIUpdateServiceRuntimeLogSettingsRequestBody{}, write)))
	mustServiceResult(t, serviceResultError(retention.TrimRuntime(ctx, "project-1", OpenAPITrimServiceRuntimeLogsQuery{}, write)))
	mustServiceResult(t, serviceResultError(retention.FlushRuntime(ctx, "project-1", OpenAPIFlushServiceRuntimeLogsQuery{}, write)))

	operations := client.ServiceConfigurationOperations()
	mustServiceResult(t, serviceResultError(operations.List(ctx, OpenAPIListServiceConfigurationOperationsQuery{})))
	mustServiceResult(t, serviceResultError(operations.Get(ctx, "operation-1")))
	mustServiceResult(t, serviceResultError(operations.Retry(ctx, "operation-1", write)))

	if calls.Load() != 55 {
		t.Fatalf("transport calls=%d, want 55", calls.Load())
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
