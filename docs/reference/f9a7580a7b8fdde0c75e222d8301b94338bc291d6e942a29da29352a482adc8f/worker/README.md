# Worker API

Contract digest: `538a02d973231fb350dd5f87cd0ef62731a7a99456be534d076b40a5009cc1d9`
Bundle digest: `f9a7580a7b8fdde0c75e222d8301b94338bc291d6e942a29da29352a482adc8f`

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
