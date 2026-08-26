# Releasing the unified SDKs

PostGrip publishes exactly three SDK artifacts at the same version:

| Tag | Artifact | Protected environment |
| --- | --- | --- |
| `go/vX.Y.Z` | `github.com/postgrip-io/postgrip-agent-sdks/go` | `sdk-release` |
| `typescript/vX.Y.Z` | `@postgrip/sdk` | `npm` |
| `python/vX.Y.Z` | `postgrip` | `pypi` |

The protected environments are release gates, not credential storage in the
repository. Their reviewers must confirm both registry ownership and that the
linked server contract/common-token change is deployed before approving a
publishing job. The npm and PyPI jobs use trusted publishing; no long-lived
registry token belongs in this repository.

## Before creating tags

1. Merge and deploy the coordinated server PR. Record its commit and deployment
   evidence in the SDK release or change record.
2. Confirm the npm `@postgrip` owner controls `@postgrip/sdk`, and the PyPI owner
   controls `postgrip`. A registry name returning not-found is not ownership
   evidence.
3. Set `VERSION`, `typescript/package.json`, `python/pyproject.toml`, and
   `go/version.go` to the same SemVer.
4. Run the complete validation and artifact inspection:

   ```sh
   python3 scripts/generate_openapi.py --plane all --check
   python3 scripts/check_operation_coverage.py
   python3 scripts/test_api_endpoints.py --plane all --mode recorded
   python3 scripts/test_curl_examples.py --plane all --mode recorded
   python3 scripts/check_release_artifacts.py --ecosystem all \
     --report /tmp/postgrip-release-artifacts.json
   ```

5. Review the artifact report for contents, direct dependencies, size, and
   build/inspection time. Raising a limit in `test/release-limits.json`
   requires explicit release review.

## Publishing order

Create the three ecosystem-prefixed tags only after the server deployment and
owner checks pass. Each workflow calls the same reusable CI validation before
building its artifact. Go validates the standalone module before creating its
release; npm packs and installs all subpaths before trusted publishing; PyPI
builds, installs, and imports the root plus all three submodules before trusted
publishing.

The three tags may run independently, but all must use the same value from
`VERSION`. Plane-specific tags and packages are obsolete and must not be
reintroduced.
