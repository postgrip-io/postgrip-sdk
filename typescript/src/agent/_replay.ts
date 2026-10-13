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
const UPDATE_ACCEPTED = 'WorkflowUpdateAccepted';
const UPDATE_TERMINAL_TYPES = new Set(['WorkflowUpdateCompleted', 'WorkflowUpdateFailed']);

/**
 * Maps a command event's `task_id` to the task that issued the command: the
 * workflow task for body commands, or an update task. The Agent reads it from
 * each command task's payload before replay; a command missing from it belongs
 * to the body.
 */
export type CommandOwners = Readonly<Record<string, string>>;

/** One owner's ordered position over its command events. */
interface CommandCursor {
  readonly events: Array<{ event: WorkflowHistoryEvent; index: number }>;
  next: number;
  activities: number;
  timers: number;
  children: number;
}

function emptyCursor(): CommandCursor {
  return { events: [], next: 0, activities: 0, timers: 0, children: 0 };
}

/**
 * Task IDs of the command events that could belong to an update: those between
 * an accepted update event and its terminal event, or the end of history while
 * it is pending, and those before the terminal event of a legacy entry with no
 * accepted event. The Agent reads each one's owner before building a replay.
 */
export function ownershipCandidates(history: readonly WorkflowHistoryEvent[]): string[] {
  const acceptedAt = new Map<string, number>();
  const terminalAt = new Map<string, number>();
  history.forEach((event, index) => {
    if (!event.task_id) return;
    if (event.type === UPDATE_ACCEPTED && !acceptedAt.has(event.task_id)) acceptedAt.set(event.task_id, index);
    if (UPDATE_TERMINAL_TYPES.has(event.type) && !terminalAt.has(event.task_id)) terminalAt.set(event.task_id, index);
  });
  const inWindow = (index: number): boolean => {
    for (const [taskId, terminal] of terminalAt) {
      const start = acceptedAt.get(taskId) ?? -1;
      if (index > start && index < terminal) return true;
    }
    for (const [taskId, start] of acceptedAt) {
      if (!terminalAt.has(taskId) && index > start) return true;
    }
    return false;
  };
  const candidates = new Set<string>();
  history.forEach((event, index) => {
    if (COMMAND_TYPES.has(event.type) && event.task_id && inWindow(index)) candidates.add(event.task_id);
  });
  return [...candidates];
}

export class WorkflowReplay {
  /** Body-owned command events in history order; the body must consume them in this order. */
  private readonly body: CommandCursor = emptyCursor();
  /** Command events each update task owns, in history order. */
  private readonly owned = new Map<string, CommandCursor>();
  private readonly signals: WorkflowHistoryEvent[];
  private readonly completedUpdates: WorkflowHistoryEvent[];
  private readonly cancellation: WorkflowHistoryEvent | undefined;
  /** The executing update task, or undefined while the body runs. */
  private owner: string | undefined;
  private ownerLive = false;
  /** The first determinism error raised; a caught one still fails the task. */
  determinismError: DeterminismError | undefined;

  constructor(history: WorkflowHistoryEvent[], owners: CommandOwners = {}) {
    const updateTasks = new Set(
      history
        .filter((event) => event.task_id && (event.type === UPDATE_ACCEPTED || UPDATE_TERMINAL_TYPES.has(event.type)))
        .map((event) => event.task_id as string),
    );
    history.forEach((event, index) => {
      if (!COMMAND_TYPES.has(event.type)) return;
      const owner = event.task_id ? owners[event.task_id] : undefined;
      if (owner && updateTasks.has(owner)) {
        let cursor = this.owned.get(owner);
        if (!cursor) {
          cursor = emptyCursor();
          this.owned.set(owner, cursor);
        }
        cursor.events.push({ event, index });
        return;
      }
      this.body.events.push({ event, index });
    });
    this.signals = history.filter((event) => event.type === 'WorkflowSignaled');
    this.completedUpdates = history.filter((event) => event.type === 'WorkflowUpdateCompleted');
    this.cancellation = history.find((event) => event.type === 'WorkflowCancellationRequested');
    this.history = history;
  }

  private readonly history: WorkflowHistoryEvent[];

  nextActivity(activityType: string): WorkflowHistoryEvent | undefined {
    const cursor = this.current();
    const event = this.nextCommand('ActivityTaskScheduled');
    if (event && event.attributes?.activity_type !== activityType) {
      throw this.fail(`activity command changed at index ${cursor.activities + 1}: history=${String(event.attributes?.activity_type)} replay=${activityType}`);
    }
    if (event) {
      cursor.activities += 1;
      cursor.next += 1;
    }
    return event;
  }

  nextTimer(durationMs?: number): WorkflowHistoryEvent | undefined {
    const cursor = this.current();
    const event = this.nextCommand('TimerStarted');
    const historyDuration = event?.attributes?.duration_ms;
    if (event && typeof durationMs === 'number' && typeof historyDuration === 'number' && Math.round(durationMs) !== historyDuration) {
      throw this.fail(`timer command changed at index ${cursor.timers + 1}: history=${historyDuration} replay=${Math.round(durationMs)}`);
    }
    if (event) {
      cursor.timers += 1;
      cursor.next += 1;
    }
    return event;
  }

  nextChild(workflowType: string): WorkflowHistoryEvent | undefined {
    const cursor = this.current();
    const event = this.nextCommand('ChildWorkflowExecutionStarted');
    if (event && event.attributes?.workflow_type !== workflowType) {
      throw this.fail(`child workflow command changed at index ${cursor.children + 1}: history=${String(event.attributes?.workflow_type)} replay=${workflowType}`);
    }
    if (event) {
      cursor.children += 1;
      cursor.next += 1;
    }
    return event;
  }

  /**
   * Makes the update task the executing owner until the returned function
   * restores the previous one. A live owner schedules new commands once its
   * recorded ones are consumed; a replayed owner already finished, so a further
   * command is a determinism error.
   */
  enterOwner(taskId: string, live: boolean): () => void {
    const previous = this.owner;
    const previousLive = this.ownerLive;
    this.owner = taskId;
    this.ownerLive = live;
    return () => {
      this.owner = previous;
      this.ownerLive = previousLive;
    };
  }

  /**
   * The completion check's leftover test: a body-owned command event left
   * unconsumed when the workflow completes, continues as new or, in query
   * replay, returns, is a recorded determinism error.
   */
  checkBodyConsumed(): void {
    this.checkConsumed(this.body, 'workflow');
  }

  /** Fails a replayed update handler that returned or raised with its own command events left unconsumed. */
  checkOwnerConsumed(taskId: string): void {
    const cursor = this.owned.get(taskId);
    if (cursor) this.checkConsumed(cursor, `update ${taskId} handler`);
  }

  private checkConsumed(cursor: CommandCursor, who: string): void {
    const left = cursor.events[cursor.next];
    if (left) {
      throw this.fail(`${who} finished before replaying recorded command at history index ${left.index}: history=${left.event.type}`);
    }
  }

  private current(): CommandCursor {
    if (this.owner === undefined) return this.body;
    let cursor = this.owned.get(this.owner);
    if (!cursor) {
      cursor = emptyCursor();
      this.owned.set(this.owner, cursor);
    }
    return cursor;
  }

  /**
   * The executing owner's earliest unconsumed command event, without consuming
   * it. Undefined when none remains (the command is new). A different kind is a
   * determinism error, covering reordering and a kind whose events ran out while
   * others remain. A replayed update handler with no recorded command left has
   * already finished, so a further command is a determinism error.
   */
  private nextCommand(kind: string): WorkflowHistoryEvent | undefined {
    const cursor = this.current();
    const next = cursor.events[cursor.next];
    if (!next) {
      if (this.owner !== undefined && !this.ownerLive) {
        throw this.fail(`update ${this.owner} handler issued ${kind} after its recorded commands`);
      }
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
