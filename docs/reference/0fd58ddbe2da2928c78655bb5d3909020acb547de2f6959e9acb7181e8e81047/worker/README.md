# Worker API

Contract digest: `86004c9dd3c7b8cf629e47141a53e4fcfb97f633294b96a68bec1c67f957fcce`
Bundle digest: `0fd58ddbe2da2928c78655bb5d3909020acb547de2f6959e9acb7181e8e81047`

## Jobs

- [`getWorkerJob`](./getWorkerJob.md) — Get a worker job
- [`listWorkerJobs`](./listWorkerJobs.md) — List worker jobs

## Logs

- [`listWorkerOperationalLogs`](./listWorkerOperationalLogs.md) — List operational logs
- [`listWorkerSecurityLogs`](./listWorkerSecurityLogs.md) — List security logs

## Snapshots

- [`createWorkerSnapshot`](./createWorkerSnapshot.md) — Take a worker snapshot now
- [`getWorkerSnapshotSettings`](./getWorkerSnapshotSettings.md) — Read a worker's snapshot settings
- [`getWorkerSnapshotStatus`](./getWorkerSnapshotStatus.md) — Read a worker's snapshot status
- [`listStorageDestinations`](./listStorageDestinations.md) — List storage destinations
- [`listWorkerSnapshots`](./listWorkerSnapshots.md) — List a worker's snapshots
- [`updateWorkerSnapshotSettings`](./updateWorkerSnapshotSettings.md) — Replace a worker's snapshot settings

## System

- [`workerOrchestratorHealth`](./workerOrchestratorHealth.md) — Check Worker Orchestrator health

## Workers

- [`checkWorker`](./checkWorker.md) — Check worker connectivity and trust
- [`createWorker`](./createWorker.md) — Create a pending Worker
- [`getWorker`](./getWorker.md) — Get a worker
- [`listWorkerAssignments`](./listWorkerAssignments.md) — List worker assignments
- [`listWorkers`](./listWorkers.md) — List workers
- [`placeWorkerInMaintenance`](./placeWorkerInMaintenance.md) — Place a worker in maintenance
- [`resumeWorkerFromMaintenance`](./resumeWorkerFromMaintenance.md) — Resume a worker from maintenance
- [`upgradeWorker`](./upgradeWorker.md) — Queue a bounded worker-host upgrade
