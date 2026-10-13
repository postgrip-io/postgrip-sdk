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

const COMMAND_TYPES = new Set(['ActivityTaskScheduled', 'TimerStarted', 'ChildWorkflowExecutionStarted']);

export class WorkflowReplay {
  /** Command events in history order; workflow code must consume them in this order. */
  private readonly commands: Array<{ event: WorkflowHistoryEvent; index: number }>;
  private readonly signals: WorkflowHistoryEvent[];
  private readonly completedUpdates: WorkflowHistoryEvent[];
  private readonly cancellation: WorkflowHistoryEvent | undefined;
  private commandCursor = 0;
  activityIndex = 0;
  private timerIndex = 0;
  private childIndex = 0;
  /** The first determinism error raised; a caught one still fails the task. */
  determinismError: DeterminismError | undefined;

  constructor(history: WorkflowHistoryEvent[]) {
    this.commands = history
      .map((event, index) => ({ event, index }))
      .filter(({ event }) => COMMAND_TYPES.has(event.type));
    this.signals = history.filter((event) => event.type === 'WorkflowSignaled');
    this.completedUpdates = history.filter((event) => event.type === 'WorkflowUpdateCompleted');
    this.cancellation = history.find((event) => event.type === 'WorkflowCancellationRequested');
    this.history = history;
  }

  private readonly history: WorkflowHistoryEvent[];

  nextActivity(activityType: string): WorkflowHistoryEvent | undefined {
    const event = this.nextCommand('ActivityTaskScheduled');
    if (event && event.attributes?.activity_type !== activityType) {
      throw this.fail(`activity command changed at index ${this.activityIndex + 1}: history=${String(event.attributes?.activity_type)} replay=${activityType}`);
    }
    if (event) {
      this.activityIndex += 1;
      this.commandCursor += 1;
    }
    return event;
  }

  nextTimer(durationMs?: number): WorkflowHistoryEvent | undefined {
    const event = this.nextCommand('TimerStarted');
    const historyDuration = event?.attributes?.duration_ms;
    if (event && typeof durationMs === 'number' && typeof historyDuration === 'number' && Math.round(durationMs) !== historyDuration) {
      throw this.fail(`timer command changed at index ${this.timerIndex + 1}: history=${historyDuration} replay=${Math.round(durationMs)}`);
    }
    if (event) {
      this.timerIndex += 1;
      this.commandCursor += 1;
    }
    return event;
  }

  nextChild(workflowType: string): WorkflowHistoryEvent | undefined {
    const event = this.nextCommand('ChildWorkflowExecutionStarted');
    if (event && event.attributes?.workflow_type !== workflowType) {
      throw this.fail(`child workflow command changed at index ${this.childIndex + 1}: history=${String(event.attributes?.workflow_type)} replay=${workflowType}`);
    }
    if (event) {
      this.childIndex += 1;
      this.commandCursor += 1;
    }
    return event;
  }

  /**
   * The earliest unconsumed command event, without consuming it. Undefined when
   * none remains (the command is new). A different kind is a determinism error,
   * covering reordering and a kind whose events ran out while others remain.
   */
  private nextCommand(kind: string): WorkflowHistoryEvent | undefined {
    const next = this.commands[this.commandCursor];
    if (!next) {
      return undefined;
    }
    if (next.event.type !== kind) {
      throw this.fail(`command changed at history index ${next.index}: history=${next.event.type} replay=${kind}`);
    }
    return next.event;
  }

  private fail(message: string): DeterminismError {
    const error = new DeterminismError(message);
    this.determinismError ??= error;
    return error;
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
