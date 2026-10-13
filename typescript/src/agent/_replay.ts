import type { WorkflowHistoryEvent } from './types.js';

/**
 * Raised when workflow code disagrees with durable history. Replay owns this
 * error; the Agent translates it into the public failure at its runtime
 * boundary, so this module depends on no SDK failure type.
 */
export class DeterminismError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'DeterminismError';
  }
}

export class WorkflowReplay {
  private readonly activities: WorkflowHistoryEvent[];
  private readonly timers: WorkflowHistoryEvent[];
  private readonly signals: WorkflowHistoryEvent[];
  private readonly children: WorkflowHistoryEvent[];
  private readonly completedUpdates: WorkflowHistoryEvent[];
  private readonly cancellation: WorkflowHistoryEvent | undefined;
  activityIndex = 0;
  private timerIndex = 0;
  private childIndex = 0;

  constructor(history: WorkflowHistoryEvent[]) {
    this.activities = history.filter((event) => event.type === 'ActivityTaskScheduled');
    this.timers = history.filter((event) => event.type === 'TimerStarted');
    this.signals = history.filter((event) => event.type === 'WorkflowSignaled');
    this.children = history.filter((event) => event.type === 'ChildWorkflowExecutionStarted');
    this.completedUpdates = history.filter((event) => event.type === 'WorkflowUpdateCompleted');
    this.cancellation = history.find((event) => event.type === 'WorkflowCancellationRequested');
    this.history = history;
  }

  private readonly history: WorkflowHistoryEvent[];

  nextActivity(activityType: string): WorkflowHistoryEvent | undefined {
    const event = this.activities[this.activityIndex];
    this.activityIndex += 1;
    if (event && event.attributes?.activity_type !== activityType) {
      throw new DeterminismError(`activity command changed at index ${this.activityIndex}: history=${String(event.attributes?.activity_type)} replay=${activityType}`);
    }
    return event;
  }

  nextTimer(durationMs?: number): WorkflowHistoryEvent | undefined {
    const event = this.timers[this.timerIndex];
    this.timerIndex += 1;
    const historyDuration = event?.attributes?.duration_ms;
    if (event && typeof durationMs === 'number' && typeof historyDuration === 'number' && Math.round(durationMs) !== historyDuration) {
      throw new DeterminismError(`timer command changed at index ${this.timerIndex}: history=${historyDuration} replay=${Math.round(durationMs)}`);
    }
    return event;
  }

  nextChild(workflowType: string): WorkflowHistoryEvent | undefined {
    const event = this.children[this.childIndex];
    this.childIndex += 1;
    if (event && event.attributes?.workflow_type !== workflowType) {
      throw new DeterminismError(`child workflow command changed at index ${this.childIndex}: history=${String(event.attributes?.workflow_type)} replay=${workflowType}`);
    }
    return event;
  }

  isTimerFired(timerStarted: WorkflowHistoryEvent): boolean {
    return this.history.some((event) => (
      event.type === 'TimerFired'
      && event.task_id != null
      && event.task_id === timerStarted.task_id
    ));
  }

  isActivityCanceled(activityScheduled: WorkflowHistoryEvent): boolean {
    return this.history.some((event) => (
      event.type === 'ActivityTaskCanceled'
      && event.task_id != null
      && event.task_id === activityScheduled.task_id
    ));
  }

  hasActivityRetryScheduled(activityScheduled: WorkflowHistoryEvent): boolean {
    return this.history.some((event) => (
      event.type === 'ActivityTaskRetryScheduled'
      && event.attributes?.previous_task === activityScheduled.task_id
    ));
  }

  activityCancellationReason(activityScheduled: WorkflowHistoryEvent): string {
    const event = this.history.find((historyEvent) => (
      historyEvent.type === 'ActivityTaskCanceled'
      && historyEvent.task_id != null
      && historyEvent.task_id === activityScheduled.task_id
    ));
    const reason = event?.attributes?.reason;
    return typeof reason === 'string' && reason ? reason : 'activity cancellation requested';
  }




  /** Recorded arguments of every signal with this name, in history order. */
  signalArgs(name: string): unknown[][] {
    return this.signals
      .filter((event) => event.attributes?.signal_name === name)
      .map((event) => (Array.isArray(event.attributes?.args) ? event.attributes.args : []));
  }

  /** Recorded arguments of every completed update with this name, in history order. */
  completedUpdateArgs(name: string): unknown[][] {
    return this.completedUpdates
      .filter((event) => event.attributes?.update_name === name)
      .map((event) => (Array.isArray(event.attributes?.args) ? event.attributes.args : []));
  }

  isCancellationRequested(): boolean {
    return this.cancellation != null;
  }

  cancellationReason(): string {
    const reason = this.cancellation?.attributes?.reason;
    return typeof reason === 'string' && reason ? reason : 'workflow cancellation requested';
  }
}
