# Worker API

Contract digest: `8d07b8d36c75dda71eb8e708472fca5f9f7dbd15eb2674aae905d049f58be0c3`
Bundle digest: `87c0db92da44a39eb7a85c5f5b39186dbebc8e8f243cab5e1462838c7742a017`

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
