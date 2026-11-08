# Worker API

Contract digest: `40a51d3084dc368881b163637b025f45bb412f6d3525d3caf2842dbda1706460`
Bundle digest: `33186029f5e0ef1b7f6d4c7d1a8ac537828dcea67c8a0520ff273b2add082759`

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
- [`getWorkerRemovalImpact`](./getWorkerRemovalImpact.md) — Preview a worker's removal
- [`listWorkerAssignments`](./listWorkerAssignments.md) — List worker assignments
- [`listWorkers`](./listWorkers.md) — List workers
- [`placeWorkerInMaintenance`](./placeWorkerInMaintenance.md) — Place a worker in maintenance
- [`removeWorker`](./removeWorker.md) — Remove a worker
- [`resumeWorkerFromMaintenance`](./resumeWorkerFromMaintenance.md) — Resume a worker from maintenance
- [`upgradeWorker`](./upgradeWorker.md) — Queue a bounded worker-host upgrade
