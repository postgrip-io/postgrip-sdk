# Releasing the unified SDKs

PostGrip currently publishes three SDK artifacts at the same version, one per
supported language:

| Tag | Artifact | Protected environment |
| --- | --- | --- |
| `go/vX.Y.Z` | `github.com/postgrip-io/postgrip-agent-sdks/go` | `sdk-release` |
| `typescript/vX.Y.Z` | `@postgrip/sdk` | `npm` |
| `python/vX.Y.Z` | `postgrip` | `pypi` |

Adding another language requires the
[architecture admission requirements](development/architecture.md#openapi-and-language-mapping)
and a coordinated update to this release matrix, package-layout checks,
artifact inspection and publishing workflows. The current release process
covers only the three artifacts above.

The protected environments are release gates, not credential storage in the
repository. Their reviewers must confirm both registry ownership and that the
linked server contract/common-token change is deployed before approving a
publishing job. The npm and PyPI jobs use trusted publishing; no long-lived
registry token belongs in this repository.

Every publishing workflow passes `live-pre-release-gate.yml` before its
artifact job. The gate waits for an accepted `postgrip-sdk-live/pre-release`
run of the tagged commit and, when there is none, dispatches
`live-pre-release.yml` in the private `postgrip-io/postgrip-sdk-live` with that
commit ([design](design/live-suites-private-repository-20261109.md), D3 and
D4). The three publishing workflows share one run per commit. The gate runs in
the `sdk-release-gate` environment, restricted to release tags, which holds
`SDK_LIVE_DISPATCH_TOKEN`: a fine-grained token with **Actions: write** on
`postgrip-io/postgrip-sdk-live` only. If the suite waits longer than the gate's
340 minutes for the stage lease, the gate fails; re-run it to keep waiting
without starting a second suite run.

The stage environments, `sdk-live-nightly` and `sdk-live-pre-release`, live in
the private repository, with the isolated plane URLs, one combined management
token, disposable fixture values and the compressed scenario secret described
in [Live integration tiers](live-testing.md). Neither may point at production.

The optional Service domain verification job reads its fixture only after the
protected environment is loaded. Configure `POSTGRIP_SERVICE_DISPOSABLE_DOMAIN_ID`,
set the independent `POSTGRIP_CONFIRM_DISPOSABLE_DOMAIN` variable to that exact
ID, and set `POSTGRIP_SERVICE_DOMAIN_LIVE_DISPOSABLE=true`. Keep the confirmation
and disposable opt-in as separately reviewed environment variables; do not
derive either one in the workflow. The job safely skips when no domain ID is
configured.

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
   python3 scripts/test_api_endpoints.py --plane all
   python3 scripts/test_curl_examples.py --plane all
   python3 scripts/check_release_artifacts.py --ecosystem all \
     --report /tmp/postgrip-release-artifacts.json
   PYTHONPATH=python/src python3 scripts/test_live_api.py --self-test
   ```

5. Review the artifact report for contents, direct dependencies, size, and
   build/inspection time. Raising a limit in `test/release-limits.json`
   requires explicit release review.
6. Confirm the current contract bundle has a successful disposable nightly run
   and approve the isolated pre-release environment. A tier label or recorded
   fixture is not live execution evidence.

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

## Historical decisions

See the [historical SDK records](archive/index.md) for the unification design,
phase evidence and dated simplification review. Current requirements are above;
old results do not establish present release readiness.
