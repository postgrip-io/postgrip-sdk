package transport

import "strings"

// Auth lanes declared by an operation's x-postgrip-auth-lane annotation.
const (
	LanePublic            = "public"
	LaneManagement        = "management"
	LaneWorkerManagement  = "worker-management"
	LaneServiceManagement = "service-management"
	LaneAgent             = "agent"
	LaneEither            = "either"
)

// Operation is one generated contract operation and the x-postgrip execution
// policy the executor applies to it. Generated plane modules emit one value per
// operation; Path holds the route template until the plane's generated resolver
// substitutes path parameters and appends the query. HeaderParameters lists the
// request headers the contract declares, such as Idempotency-Key and If-Match.
type Operation struct {
	ID               string
	Method           string
	Path             string
	AuthLane         string
	Safety           string
	Idempotency      string
	Pagination       string
	Retry            string
	Signing          string
	StreamingRequest bool
	WebSocket        bool
	RequestSchema    string
	ResponseSchema   string
	PathParameters   []string
	HeaderParameters []string
}

// DeclaresHeader reports whether the contract declares the named request
// header for the operation, compared case-insensitively.
func (o Operation) DeclaresHeader(name string) bool {
	for _, declared := range o.HeaderParameters {
		if strings.EqualFold(declared, name) {
			return true
		}
	}
	return false
}

// RetryEligible reports the contract retry rule: the operation is annotated
// bounded and is read-only or carries an idempotency key. Protocol, signed,
// streaming-upload and WebSocket operations are never eligible, even if
// mis-annotated.
func RetryEligible(operation Operation, idempotencyKey string) bool {
	if operation.Retry != "bounded" || operation.Safety == "protocol" || operation.Signing != "" ||
		operation.StreamingRequest || operation.WebSocket {
		return false
	}
	return operation.Safety == "read-only" || idempotencyKey != ""
}
