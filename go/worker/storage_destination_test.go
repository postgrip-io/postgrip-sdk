package worker

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

const storageDestinationListBody = `{"items":[` +
	`{"id":"0d6c2a4e-8b1f-4c3d-9e7a-5f2b1c0d9e8a","name":"Production backups","provider":"r2","bucket":"pg-backups","endpoint":"https://account.r2.cloudflarestorage.com","accountId":"account","prefix":"postgrip","createdAt":"2026-11-01T09:30:00Z","updatedAt":"2026-11-01T09:30:00Z"},` +
	`{"id":"7e3f9a1b-2c4d-4e5f-8a6b-9c0d1e2f3a4b","name":"us-east archive","provider":"s3","bucket":"acme-worker-snapshots","region":"us-east-1","createdAt":"2026-10-20T14:05:12Z","updatedAt":"2026-11-03T08:00:00Z"}]}`

func TestStorageDestinationsReadsTheOrganizationList(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet || r.URL.Path != "/api/v1/storage-destinations" || r.URL.RawQuery != "" {
			t.Fatalf("request = %s %s?%s", r.Method, r.URL.Path, r.URL.RawQuery)
		}
		if r.Header.Get("Authorization") != "Bearer pgt_test-token" || r.Header.Get("Idempotency-Key") != "" {
			t.Fatalf("authorization=%q idempotency=%q", r.Header.Get("Authorization"), r.Header.Get("Idempotency-Key"))
		}
		_, _ = io.WriteString(w, storageDestinationListBody)
	}))
	defer server.Close()
	list, err := newTestClient(t, server, false).StorageDestinations(context.Background())
	if err != nil || len(list.Items) != 2 {
		t.Fatalf("StorageDestinations() = %#v, %v", list, err)
	}
	r2, s3 := list.Items[0], list.Items[1]
	if r2.Id != "0d6c2a4e-8b1f-4c3d-9e7a-5f2b1c0d9e8a" || r2.Provider != "r2" || r2.Region != nil ||
		r2.Endpoint == nil || *r2.Endpoint != "https://account.r2.cloudflarestorage.com" || r2.AccountId == nil || *r2.AccountId != "account" ||
		r2.Prefix == nil || *r2.Prefix != "postgrip" || !r2.CreatedAt.Equal(time.Date(2026, 11, 1, 9, 30, 0, 0, time.UTC)) {
		t.Fatalf("r2 destination = %#v", r2)
	}
	if s3.Provider != "s3" || s3.Region == nil || *s3.Region != "us-east-1" || s3.Endpoint != nil || s3.AccountId != nil || s3.Prefix != nil {
		t.Fatalf("s3 destination = %#v", s3)
	}
	// The id is what UpdateSnapshotSettings takes as StorageDestinationId.
	_ = UpdateWorkerSnapshotSettingsRequest{StorageDestinationId: &r2.Id}
	encoded, err := json.Marshal(s3)
	if err != nil || strings.Contains(string(encoded), "endpoint") || strings.Contains(string(encoded), "prefix") {
		t.Fatalf("absent optional fields re-encoded: %s (%v)", encoded, err)
	}
}

func TestStorageDestinationsAnswersAnEmptyList(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = io.WriteString(w, `{"items":[]}`)
	}))
	defer server.Close()
	list, err := newTestClient(t, server, false).StorageDestinations(context.Background())
	if err != nil || list.Items == nil || len(list.Items) != 0 {
		t.Fatalf("StorageDestinations() = %#v, %v", list, err)
	}
}

func TestStorageDestinationsKeepsBoundedReadRetry(t *testing.T) {
	var attempts atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if attempts.Add(1) == 1 {
			w.Header().Set("Retry-After", "0")
			w.WriteHeader(http.StatusServiceUnavailable)
			_, _ = io.WriteString(w, `{"code":"AUTH_UNAVAILABLE","message":"try again","requestId":"req"}`)
			return
		}
		_, _ = io.WriteString(w, storageDestinationListBody)
	}))
	defer server.Close()
	if list, err := newTestClient(t, server, true).StorageDestinations(context.Background()); err != nil || len(list.Items) != 2 || attempts.Load() != 2 {
		t.Fatalf("StorageDestinations() = %#v, %v; attempts = %d", list, err, attempts.Load())
	}
}

func TestStorageDestinationTypesCarryNoCredential(t *testing.T) {
	typ := reflect.TypeOf(StorageDestination{})
	var names []string
	for i := 0; i < typ.NumField(); i++ {
		names = append(names, strings.Split(typ.Field(i).Tag.Get("json"), ",")[0])
	}
	want := []string{"id", "name", "provider", "bucket", "region", "endpoint", "accountId", "prefix", "createdAt", "updatedAt"}
	if !reflect.DeepEqual(names, want) {
		t.Fatalf("StorageDestination fields = %v, want %v", names, want)
	}
	if field, ok := reflect.TypeOf(StorageDestinationList{}).FieldByName("Items"); !ok || field.Type.Elem() != typ {
		t.Fatalf("StorageDestinationList.Items = %#v", field)
	}
}
