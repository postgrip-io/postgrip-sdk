# Live integration tiers

Pull requests exercise every operation in the
[generated coverage report](https://github.com/postgrip-io/postgrip-sdk/blob/main/test/reports/operation-coverage.md)
through strict recorded transports in
Go, TypeScript, and Python and execute every eligible cURL example. Live jobs
add deployed-system evidence at a cadence matched to risk:

| Tier | Environment | Coverage |
| --- | --- | --- |
| Nightly | Protected disposable tenant | Ordinary tenant API lifecycles across Agent, Worker, and Service |
| Pre-release | Protected isolated runtime | Delegated signing/refresh, archive upload, cancellable logs, sandbox WebSocket, and destructive Service operations |
| Production smoke | Production-safe endpoints | Hard-coded public read-only `health` and `workerOrchestratorHealth` allowlist only |

The live fixture manager validates the selected operation set against
`test/operation-tests.json`, so a contract addition cannot silently escape a
live tier. Environment-specific scenarios are protected because they contain
deployment fixture details, but their schema and runner are versioned in this
repository.

The nightly and pre-release tiers run on the stage environment from the
private `postgrip-io/postgrip-sdk-live`, because a public repository can't use
web's stage actions or runners. Each run checks out this repository at the
commit under test and runs its scripts, then reports the result on that commit
as the `postgrip-sdk-live/nightly` or `postgrip-sdk-live/pre-release` status,
linking the run ([design](design/live-suites-private-repository-20261109.md)).
The production smoke stays here, on a GitHub-hosted runner.

The fixture manager owns resource registration, destructive-operation consent,
cleanup and reporting of remaining resources. Failed cleanup stays visible;
a configured live tier is not proof of a successful live run.

For the scenario format and local safety checks, see
[`test/live/README.md`](https://github.com/postgrip-io/postgrip-sdk/blob/main/test/live/README.md).
