---
title: API reference
layout: default
nav_order: 6
---

# API reference

The full, auto-generated Go API documentation lives on [pkg.go.dev](https://pkg.go.dev/github.com/postgrip-io/postgrip-agent-sdks/go). Every public type, function, method, and constant is rendered from the source godoc comments and stays in sync with each released version.

[Open pkg.go.dev/github.com/postgrip-io/postgrip-agent-sdks/go →](https://pkg.go.dev/github.com/postgrip-io/postgrip-agent-sdks/go){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }

## Direct links to each package

| Package    | godoc                                                                          |
|:-----------|:--------------------------------------------------------------------------------|
| `client`   | [pkg.go.dev/github.com/postgrip-io/postgrip-agent-sdks/go/agent/client](https://pkg.go.dev/github.com/postgrip-io/postgrip-agent-sdks/go/agent/client)    |
| `worker`   | [pkg.go.dev/github.com/postgrip-io/postgrip-agent-sdks/go/agent/worker](https://pkg.go.dev/github.com/postgrip-io/postgrip-agent-sdks/go/agent/worker)    |
| `workflow` | [pkg.go.dev/github.com/postgrip-io/postgrip-agent-sdks/go/agent/workflow](https://pkg.go.dev/github.com/postgrip-io/postgrip-agent-sdks/go/agent/workflow) |
| `activity` | [pkg.go.dev/github.com/postgrip-io/postgrip-agent-sdks/go/agent/activity](https://pkg.go.dev/github.com/postgrip-io/postgrip-agent-sdks/go/agent/activity) |
| `failure`  | [pkg.go.dev/github.com/postgrip-io/postgrip-agent-sdks/go/agent/failure](https://pkg.go.dev/github.com/postgrip-io/postgrip-agent-sdks/go/agent/failure)  |

## Source

Source, issues, and releases are maintained in [`postgrip-io/postgrip-sdks`](https://github.com/postgrip-io/postgrip-sdks).

## Versioning

The SDK uses Go modules and semantic versioning. Pin to a specific version in your `go.mod`:

```sh
go get github.com/postgrip-io/postgrip-agent-sdks/go@v0.13.0
```

While the version stays at `v0.x.x`, the public API may evolve. Pin to a tag for stability and read release notes when upgrading.

[All releases →](https://github.com/postgrip-io/postgrip-sdks/releases?q=go%2Fv){: .btn .fs-5 .mb-4 .mb-md-0 }
