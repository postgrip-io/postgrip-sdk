package client

import (
	"context"
	"net/http"
)

// openAPIHeadersContextKey carries the per-call header parameters of a
// generated operation, such as its Idempotency-Key.
type openAPIHeadersContextKey struct{}

// withOpenAPIHeaders returns a context whose requests carry headers, merged
// over any per-call headers ctx already carries. Only the operations that
// declare a header send it.
func withOpenAPIHeaders(ctx context.Context, headers http.Header) context.Context {
	merged := openAPIHeaders(ctx)
	for name, values := range headers {
		merged[http.CanonicalHeaderKey(name)] = append([]string(nil), values...)
	}
	return context.WithValue(ctx, openAPIHeadersContextKey{}, merged)
}

// openAPIHeaders returns a copy of the per-call headers ctx carries.
func openAPIHeaders(ctx context.Context) http.Header {
	if headers, ok := ctx.Value(openAPIHeadersContextKey{}).(http.Header); ok {
		return headers.Clone()
	}
	return http.Header{}
}

// WithIdempotencyKey returns a context whose task sends and signals carry key
// as their Idempotency-Key: enqueueTask (TaskClient.Enqueue,
// WorkflowClient.Start, Connection.EnqueueTask), signalWorkflow
// (WorkflowHandle.Signal, Connection.SignalWorkflow) and
// signalWithStartWorkflow. Other operations made with the context send no key.
//
// The header is optional on these operations. With a key, a resend of the
// same request within 24 hours answers the first request's stored result
// (marked Idempotent-Replayed: true) instead of sending or signalling again,
// and a connection with EnableRetries retries the request. A key names one
// request: reusing it with another body answers 409 IDEMPOTENCY_CONFLICT. The
// key must be 1 to 128 visible ASCII characters; an invalid key fails before
// sending. An empty key leaves ctx unchanged.
func WithIdempotencyKey(ctx context.Context, key string) context.Context {
	if key == "" {
		return ctx
	}
	return withOpenAPIHeaders(ctx, http.Header{"Idempotency-Key": {key}})
}
