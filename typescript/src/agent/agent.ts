import { DeterminismError, WorkflowReplay } from './_replay.js';
import { runInActivityRuntime } from './activity.js';
import { Connection } from './connection.js';
import {
  ApplicationFailure,
  CancelledFailure,
  ignoreTerminalTaskMutation,
  isTerminalTaskMutation,
} from './errors.js';
import { ContinueAsNewCommand, runInWorkflowRuntime, validateWorkflowSandbox, withTimeout } from './workflow.js';
import type {
  ActivityInvocationPayload,
  ActivityOptions,
  ActivityRegistry,
  FailureInfo,
  ChildWorkflowOptions,
  Task,
  TaskResult,
  TimerPayload,
  WorkflowHistoryEvent,
  WorkflowPayload,
  WorkflowQueryPayload,
  WorkflowRegistry,
  WorkflowUpdatePayload,
} from './types.js';

export interface AgentOptions {
  connection: Connection;
  namespace?: string;
  taskQueue?: string;
  workflows: WorkflowRegistry;
  activities?: ActivityRegistry;
  identity?: string;
  name?: string;
  host?: string;
  pollIntervalMs?: number;
  maxConcurrentTaskExecutions?: number;
  maxConcurrentTasks?: number;
}

export interface AgentShutdownOptions {
  timeoutMs?: number;
}

const WORKFLOW_RUNTIME_TASK_TYPES = ['workflow:', 'activity:', 'query:', 'update:'];

export class Agent {
  private readonly connection: Connection;
  private readonly namespace: string;
  private readonly taskQueue: string;
  private readonly workflows: WorkflowRegistry;
  private readonly activities: ActivityRegistry;
  private readonly identity: string;
  private readonly pollIntervalMs: number;
  private readonly maxConcurrentTasks: number;
  private readonly inFlightTasks = new Set<Promise<void>>();
  private runController: AbortController | undefined;

  private constructor(options: AgentOptions) {
    this.connection = options.connection;
    this.namespace = options.namespace ?? process.env.POSTGRIP_AGENT_NAMESPACE ?? 'default';
    const taskQueue = options.taskQueue ?? process.env.POSTGRIP_AGENT_TASK_QUEUE;
    if (!taskQueue) {
      throw new Error('taskQueue is required');
    }
    this.taskQueue = taskQueue;
    this.workflows = options.workflows;
    this.activities = options.activities ?? {};
    const managedRuntime = process.env.POSTGRIP_AGENT_MANAGED_RUNTIME === 'true';
    if (!managedRuntime) {
      throw new Error('postgrip-agent: Agent workers must be launched by a PostGrip host agent as managed workflow runtimes; submit workflow.runtime work to an agent pool instead');
    }
    this.identity = options.identity ?? process.env.POSTGRIP_AGENT_ID ?? `ts-agent-${crypto.randomUUID()}`;
    this.pollIntervalMs = options.pollIntervalMs ?? 1000;
    this.maxConcurrentTasks = Math.max(1, options.maxConcurrentTaskExecutions ?? options.maxConcurrentTasks ?? 4);
    this.connection.configureAgentAuth?.({
      agentId: this.identity,
      name: options.name,
      host: options.host,
      namespace: this.namespace,
      queue: this.taskQueue,
      accessToken: process.env.POSTGRIP_AGENT_ACCESS_TOKEN,
      refreshToken: process.env.POSTGRIP_AGENT_REFRESH_TOKEN,
      accessExpiresAt: process.env.POSTGRIP_AGENT_ACCESS_EXPIRES_AT,
      signingPrivateKey: process.env.POSTGRIP_AGENT_SIGNING_PRIVATE_KEY,
    });
  }

  static async create(options: AgentOptions): Promise<Agent> {
    await options.connection.health();
    return new Agent(options);
  }

  async run(options: { signal?: AbortSignal } = {}): Promise<void> {
    const controller = new AbortController();
    const stop = () => controller.abort();
    options.signal?.addEventListener('abort', stop, { once: true });
    this.runController = controller;
    try {
      await Promise.all(
        Array.from({ length: this.maxConcurrentTasks }, () => this.pollLoop({ signal: controller.signal })),
      );
    } finally {
      if (this.runController === controller) {
        this.runController = undefined;
      }
      options.signal?.removeEventListener('abort', stop);
    }
  }

  async shutdown(options: AgentShutdownOptions = {}): Promise<void> {
    this.runController?.abort();
    const drained = Promise.allSettled([...this.inFlightTasks]).then(() => undefined);
    if (options.timeoutMs == null || options.timeoutMs < 0) {
      await drained;
      return;
    }
    await Promise.race([
      drained,
      delay(options.timeoutMs),
    ]);
  }

  private async pollLoop(options: { signal?: AbortSignal } = {}): Promise<void> {
    while (!options.signal?.aborted) {
      let task: Task<WorkflowPayload | ActivityInvocationPayload | WorkflowQueryPayload | WorkflowUpdatePayload> | undefined;
      try {
        const response = await this.connection.pollTaskResponse<WorkflowPayload | ActivityInvocationPayload | WorkflowQueryPayload | WorkflowUpdatePayload>({
          namespace: this.namespace,
          queue: this.taskQueue,
          agentId: this.identity,
          waitSeconds: 20,
          taskTypes: WORKFLOW_RUNTIME_TASK_TYPES,
          signal: options.signal,
        });
        if (response.directive?.type === 'shutdown') {
          this.runController?.abort();
          return;
        }
        task = response.task;
      } catch (err) {
        if (options.signal?.aborted) return;
        const message = err instanceof Error ? err.message : String(err);
        console.warn(`postgrip-agent: poll failed: ${message}`);
        await delay(this.pollIntervalMs, options.signal);
        continue;
      }
      if (options.signal?.aborted) return;
      if (!task) {
        await delay(this.pollIntervalMs, options.signal);
        continue;
      }
      const execution = this.executeTask(task);
      this.inFlightTasks.add(execution);
      try {
        await execution;
      } finally {
        this.inFlightTasks.delete(execution);
      }
    }
  }

  async runUntil<T>(promise: Promise<T>, options: { signal?: AbortSignal } = {}): Promise<T> {
    const controller = new AbortController();
    const stop = () => controller.abort();
    options.signal?.addEventListener('abort', stop, { once: true });
    const runPromise = this.run({ signal: controller.signal }).catch((err) => {
      if (!controller.signal.aborted) throw err;
    });
    try {
      return await promise;
    } finally {
      controller.abort();
      await runPromise;
      options.signal?.removeEventListener('abort', stop);
    }
  }

  private async executeTask(task: Task<WorkflowPayload | ActivityInvocationPayload | WorkflowQueryPayload | WorkflowUpdatePayload>): Promise<void> {
    if (task.type.startsWith('activity:')) {
      await this.withLeaseRenewal(task as Task<ActivityInvocationPayload>, () => this.executeActivityTask(task as Task<ActivityInvocationPayload>));
      return;
    }
    if (task.type.startsWith('query:')) {
      await this.executeQueryTask(task as Task<WorkflowQueryPayload>);
      return;
    }
    if (task.type.startsWith('update:')) {
      await this.executeUpdateTask(task as Task<WorkflowUpdatePayload>);
      return;
    }
    await this.executeWorkflowTask(task as Task<WorkflowPayload>);
  }

  private async executeWorkflowTask(task: Task<WorkflowPayload>): Promise<void> {
    await this.withLeaseRenewal(task, () => this.executeWorkflowTaskLeased(task));
  }

  private async executeWorkflowTaskLeased(task: Task<WorkflowPayload>): Promise<void> {
    const startedAt = new Date().toISOString();
    try {
      if (!task.type.startsWith('workflow:')) {
        throw ApplicationFailure.nonRetryable(`unsupported TypeScript task type ${task.type}`, 'UnsupportedTaskType', task.type);
      }
      const workflowType = task.payload?.workflowType ?? task.type.replace(/^workflow:/, '');
      const workflow = this.workflows[workflowType];
      if (!workflow) {
        throw ApplicationFailure.nonRetryable(`workflow ${workflowType} is not registered`, 'WorkflowNotRegistered', workflowType);
      }
      validateWorkflowSandbox(workflow);
      const workflowId = task.payload?.workflowId ?? task.id;
      const workflowRunId = task.payload?.runId ?? workflowId;
      const history = await this.connection.getWorkflowHistory(workflowRunId);
      const replay = new WorkflowReplay(history);
      const handlers = new WorkflowHandlers(replay);
      await this.emit(task.id, 'started', 'workflow', `started workflow ${workflowType}`, { workflowType });
      const value = await runInWorkflowRuntime({
        workflowId,
        workflowRunId,
        taskQueue: task.queue,
        workflowType,
        cancellationScopes: [],
        executeActivity: (name, args, options) => this.executeActivityCommand(task, replay, name, args, options),
        executeChild: (name, args, options) => this.executeChildWorkflowCommand(task, replay, name, args, options),
        continueAsNew: (name, args, options) => {
          throw new ContinueAsNewCommand(name, args, options);
        },
        sleep: (ms, cancellationScope) => this.executeTimerCommand(task, replay, ms, cancellationScope),
        condition: (predicate, timeoutMs, cancellationScope) => this.executeConditionCommand(task, replay, predicate, timeoutMs, cancellationScope),
        cancellationRequested: () => replay.isCancellationRequested(),
        setSignalHandler: (name, handler) => handlers.setSignalHandler(name, handler),
        setQueryHandler: (name, handler) => handlers.setQueryHandler(name, handler),
        setUpdateHandler: (name, handler) => handlers.setUpdateHandler(name, handler),
        emit: (event) => this.emit(task.id, event.kind ?? 'progress', event.stage, event.message, event.details),
      }, () => workflow(...(task.payload?.args ?? [])));
      const result: TaskResult = {
        value,
        message: 'workflow completed',
        started_at: startedAt,
        finished_at: new Date().toISOString(),
      };
      await this.emit(task.id, 'completed', 'workflow', `completed workflow ${workflowType}`);
      await this.connection.completeTask(task.id, this.identity, result).catch(ignoreTerminalTaskMutation);
    } catch (err) {
      if (err instanceof WorkflowBlocked) {
        await this.connection.blockTask(task.id, this.identity, err.message).catch(ignoreTerminalTaskMutation);
        return;
      }
      if (err instanceof ContinueAsNewCommand) {
        await this.completeWorkflowAsContinued(task, err, startedAt);
        return;
      }
      if (err instanceof CancelledFailure) {
        await this.emit(task.id, 'failed', 'workflow', err.message).catch(() => undefined);
        await this.connection.failTask(task.id, this.identity, err.message, {
          message: err.message,
          failure: failureInfoFromError(err),
          started_at: startedAt,
          finished_at: new Date().toISOString(),
        }).catch(ignoreTerminalTaskMutation);
        return;
      }
      const message = err instanceof Error ? err.message : String(err);
      await this.emit(task.id, 'failed', 'workflow', message).catch(() => undefined);
      await this.connection.failTask(task.id, this.identity, message, {
        failure: failureInfoFromError(err),
        started_at: startedAt,
        finished_at: new Date().toISOString(),
      }).catch(ignoreTerminalTaskMutation);
    }
  }

  private async executeQueryTask(task: Task<WorkflowQueryPayload>): Promise<void> {
    await this.withLeaseRenewal(task, () => this.executeHandlerTaskLeased(task, 'query'));
  }

  private async executeUpdateTask(task: Task<WorkflowUpdatePayload>): Promise<void> {
    await this.withLeaseRenewal(task, () => this.executeHandlerTaskLeased(task, 'update'));
  }

  private async executeHandlerTaskLeased(
    task: Task<WorkflowQueryPayload | WorkflowUpdatePayload>,
    kind: 'query' | 'update',
  ): Promise<void> {
    const startedAt = new Date().toISOString();
    const payload = task.payload;
    const name = kind === 'query'
      ? (payload as WorkflowQueryPayload | undefined)?.queryName
      : (payload as WorkflowUpdatePayload | undefined)?.updateName;
    const invalidCode = kind === 'query' ? 'InvalidWorkflowQueryPayload' : 'InvalidWorkflowUpdatePayload';
    const missingCode = kind === 'query' ? 'QueryNotRegistered' : 'UpdateNotRegistered';
    try {
      if (!payload?.workflowId || !payload.workflowType || !name) {
        throw ApplicationFailure.nonRetryable(`invalid workflow ${kind} payload`, invalidCode);
      }
      const workflow = this.workflows[payload.workflowType];
      if (!workflow) {
        throw ApplicationFailure.nonRetryable(`workflow ${payload.workflowType} is not registered`, 'WorkflowNotRegistered', payload.workflowType);
      }
      validateWorkflowSandbox(workflow);
      const sourceWorkflow = await this.connection.getWorkflow(payload.workflowRunId ?? payload.workflowId);
      const sourceTask = await this.connection.getTask<WorkflowPayload>(sourceWorkflow.task_id);
      const history = await this.connection.getWorkflowHistory(payload.workflowRunId ?? payload.workflowId);
      const replay = new WorkflowReplay(history);
      const handlers = new WorkflowHandlers(replay);
      await this.emit(task.id, 'started', kind, `started ${kind} ${name}`, { workflowType: payload.workflowType });
      try {
        await runInWorkflowRuntime({
          workflowId: payload.workflowId,
          workflowRunId: payload.workflowRunId ?? sourceWorkflow.run_id ?? payload.workflowId,
          taskQueue: sourceWorkflow.queue,
          workflowType: payload.workflowType,
          cancellationScopes: [],
          continueAsNew: () => {
            throw new WorkflowQueryReady('workflow continued as new');
          },
          executeActivity: (name) => this.replayActivityForQuery(replay, name),
          executeChild: (name) => this.replayChildForQuery(replay, name),
          sleep: () => this.replayTimerForQuery(replay),
          condition: (predicate) => this.replayConditionForQuery(predicate),
          cancellationRequested: () => replay.isCancellationRequested(),
          setSignalHandler: (name, handler) => handlers.setSignalHandler(name, handler),
          setQueryHandler: (name, handler) => handlers.setQueryHandler(name, handler),
          setUpdateHandler: (name, handler) => handlers.setUpdateHandler(name, handler),
          emit: async () => undefined,
        }, () => workflow(...(sourceTask.payload?.args ?? [])));
      } catch (err) {
        if (!(err instanceof WorkflowQueryReady)) {
          throw err;
        }
      }
      const handler = kind === 'query' ? handlers.queryHandler(name) : handlers.updateHandler(name);
      if (!handler) {
        throw ApplicationFailure.nonRetryable(`${kind} ${name} is not registered`, missingCode, name);
      }
      const value = await Promise.resolve(handler(...(payload.args ?? [])));
      await this.emit(task.id, 'completed', kind, `completed ${kind} ${name}`);
      await this.connection.completeTask(task.id, this.identity, {
        value,
        message: `${kind} completed`,
        started_at: startedAt,
        finished_at: new Date().toISOString(),
      }).catch(ignoreTerminalTaskMutation);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      await this.emit(task.id, 'failed', kind, message).catch(() => undefined);
      await this.connection.failTask(task.id, this.identity, message, {
        started_at: startedAt,
        finished_at: new Date().toISOString(),
      }).catch(ignoreTerminalTaskMutation);
    }
  }

  private async completeWorkflowAsContinued(task: Task<WorkflowPayload>, command: ContinueAsNewCommand, startedAt: string): Promise<void> {
    const currentWorkflowId = task.payload?.workflowId ?? task.id;
    const nextWorkflowId = command.options.workflowId ?? `${currentWorkflowId}-continue-${crypto.randomUUID()}`;
    const taskQueue = command.options.taskQueue ?? task.queue;
    const nextTask = await this.connection.enqueueTask<WorkflowPayload>({
      type: `workflow:${command.workflowType}`,
      queue: taskQueue,
      namespace: task.namespace,
      payload: {
        namespace: task.namespace,
        workflowType: command.workflowType,
        workflowId: nextWorkflowId,
        continuedFromWorkflowId: currentWorkflowId,
        runTimeoutMs: command.options.workflowRunTimeoutMs,
        retry: command.options.retry,
        args: command.args,
      },
      lease_timeout_seconds: command.options.leaseTimeoutSeconds,
    });
    await this.emit(task.id, 'completed', 'workflow', `continued workflow as new ${command.workflowType}`, {
      workflowType: command.workflowType,
      workflowId: nextWorkflowId,
      taskQueue,
    });
    await this.connection.completeTask(task.id, this.identity, {
      message: 'workflow continued as new',
      continue_as_new: {
        workflow_id: nextWorkflowId,
        workflow_type: command.workflowType,
        task_queue: taskQueue,
        task_id: nextTask.id,
      },
      started_at: startedAt,
      finished_at: new Date().toISOString(),
    }).catch(ignoreTerminalTaskMutation);
  }

  private async executeActivityCommand(
    workflowTask: Task<WorkflowPayload>,
    replay: WorkflowReplay,
    name: string,
    args: unknown[],
    options: ActivityOptions,
  ): Promise<unknown> {
    this.throwIfCancelled(replay, options.cancellationScope);
    const scheduled = replayCommand(() => replay.nextActivity(name));
    if (scheduled?.task_id) {
      const task = await this.connection.getTask<ActivityInvocationPayload>(scheduled.task_id);
      if (task.state === 'succeeded') return task.result?.value;
      if (task.state === 'failed') {
        if (replay.isActivityCanceled(scheduled)) {
          throw new CancelledFailure(replay.activityCancellationReason(scheduled));
        }
        if (replay.hasActivityRetryScheduled(scheduled)) {
          return this.executeActivityCommand(workflowTask, replay, name, args, options);
        }
        throw ApplicationFailure.create({ message: task.error ?? 'activity failed', type: 'ActivityFailure' });
      }
      throw new WorkflowBlocked(`waiting for activity ${name}`);
    }
    await this.connection.enqueueTask<ActivityInvocationPayload>({
      type: `activity:${name}`,
      namespace: workflowTask.namespace,
      queue: workflowTask.queue,
      payload: {
        activityType: name,
        workflowId: workflowTask.payload?.workflowId ?? workflowTask.id,
        workflowRunId: workflowTask.payload?.runId,
        workflowTaskId: workflowTask.id,
        attempt: 1,
        cancellationType: options.cancellationType,
        retry: options.retry,
        args,
      },
      lease_timeout_seconds: options.startToCloseTimeoutMs ? Math.ceil(options.startToCloseTimeoutMs / 1000) : undefined,
    });
    throw new WorkflowBlocked(`scheduled activity ${name}`);
  }

  private async executeTimerCommand(
    workflowTask: Task<WorkflowPayload>,
    replay: WorkflowReplay,
    durationMs: number,
    cancellationScope: 'cancellable' | 'non_cancellable' = 'cancellable',
  ): Promise<void> {
    this.throwIfCancelled(replay, cancellationScope);
    const started = replayCommand(() => replay.nextTimer(durationMs));
    if (started?.task_id) {
      if (replay.isTimerFired(started)) return;
      throw new WorkflowBlocked('waiting for timer');
    }
    const normalizedDurationMs = Math.max(0, Math.round(durationMs));
    const timerId = crypto.randomUUID();
    const fireAt = new Date(Date.now() + normalizedDurationMs).toISOString();
    await this.connection.enqueueTask<TimerPayload>({
      type: 'timer',
      namespace: workflowTask.namespace,
      queue: workflowTask.queue,
      payload: {
        workflowId: workflowTask.payload?.workflowId ?? workflowTask.id,
        workflowRunId: workflowTask.payload?.runId,
        workflowTaskId: workflowTask.id,
        timerId,
        durationMs: normalizedDurationMs,
        fireAt,
      },
    });
    throw new WorkflowBlocked(`scheduled timer for ${normalizedDurationMs}ms`);
  }

  private async executeChildWorkflowCommand(
    workflowTask: Task<WorkflowPayload>,
    replay: WorkflowReplay,
    workflowType: string,
    args: unknown[],
    options: ChildWorkflowOptions,
  ): Promise<unknown> {
    this.throwIfCancelled(replay, options.cancellationScope);
    const started = replayCommand(() => replay.nextChild(workflowType));
    if (started) {
      const childWorkflowId = childWorkflowIdFromEvent(started);
      if (!childWorkflowId) {
        throw ApplicationFailure.nonRetryable('child workflow history is missing child workflow ID', 'InvalidChildWorkflowHistory');
      }
      const child = await this.connection.getWorkflow(childWorkflowRunIdFromEvent(started) ?? childWorkflowId);
      if (child.state === 'succeeded') return child.result?.value;
      if (child.state === 'failed') {
        throw ApplicationFailure.create({ message: child.error ?? 'child workflow failed', type: 'ChildWorkflowFailure' });
      }
      throw new WorkflowBlocked(`waiting for child workflow ${workflowType}`);
    }
    const childWorkflowId = options.workflowId ?? crypto.randomUUID();
    await this.connection.enqueueTask<WorkflowPayload>({
      type: `workflow:${workflowType}`,
      namespace: workflowTask.namespace,
      queue: options.taskQueue ?? workflowTask.queue,
      payload: {
        namespace: workflowTask.namespace,
        workflowType,
        workflowId: childWorkflowId,
        parentWorkflowId: workflowTask.payload?.workflowId ?? workflowTask.id,
        parentWorkflowRunId: workflowTask.payload?.runId,
        parentWorkflowTaskId: workflowTask.id,
        parentCancellationType: options.cancellationType,
        runTimeoutMs: options.workflowRunTimeoutMs,
        retry: options.retry,
        args,
      },
      lease_timeout_seconds: options.leaseTimeoutSeconds,
    });
    throw new WorkflowBlocked(`scheduled child workflow ${workflowType}`);
  }

  private async executeConditionCommand(
    workflowTask: Task<WorkflowPayload>,
    replay: WorkflowReplay,
    predicate: () => boolean,
    timeoutMs?: number,
    cancellationScope: 'cancellable' | 'non_cancellable' = 'cancellable',
  ): Promise<boolean> {
    this.throwIfCancelled(replay, cancellationScope);
    if (predicate()) return true;
    if (timeoutMs == null) {
      throw new WorkflowBlocked('waiting for condition');
    }
    await this.executeTimerCommand(workflowTask, replay, timeoutMs, cancellationScope);
    return predicate();
  }

  private async executeActivityTask(task: Task<ActivityInvocationPayload>): Promise<void> {
    const startedAt = new Date().toISOString();
    const activityType = task.payload?.activityType ?? task.type.replace(/^activity:/, '');
    const activity = this.activities[activityType];
    try {
      if (!activity) {
        throw ApplicationFailure.nonRetryable(`activity ${activityType} is not registered`, 'ActivityNotRegistered', activityType);
      }
      await this.emit(task.id, 'started', 'activity', `started activity ${activityType}`, { activityType });
      const value = await withTimeout(
        runInActivityRuntime({
          taskId: task.id,
          activityType,
          heartbeat: async (details) => {
            await this.connection.heartbeatTask(task.id, this.identity, {
              kind: 'heartbeat',
              stage: 'activity',
              message: `activity ${activityType} heartbeat`,
              details,
            });
          },
          emit: async (event) => {
            await this.connection.appendTaskEvent(task.id, this.identity, event);
          },
        }, () => Promise.resolve(activity(...(task.payload?.args ?? [])))),
        task.lease_timeout_seconds > 0 ? task.lease_timeout_seconds * 1000 : undefined,
        `activity ${activityType} timed out`,
      );
      await this.emit(task.id, 'completed', 'activity', `completed activity ${activityType}`);
      await this.connection.completeTask(task.id, this.identity, {
        value,
        message: 'activity completed',
        started_at: startedAt,
        finished_at: new Date().toISOString(),
      }).catch(ignoreTerminalTaskMutation);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      await this.emit(task.id, 'failed', 'activity', message).catch(() => undefined);
      await this.connection.failTask(task.id, this.identity, message, {
        failure: failureInfoFromError(err),
        started_at: startedAt,
        finished_at: new Date().toISOString(),
      }).catch(ignoreTerminalTaskMutation);
    }
  }

  private async replayActivityForQuery(replay: WorkflowReplay, name: string): Promise<unknown> {
    if (replay.isCancellationRequested()) throw new WorkflowQueryReady('workflow cancelled');
    const scheduled = replayCommand(() => replay.nextActivity(name));
    if (!scheduled?.task_id) {
      throw new WorkflowQueryReady();
    }
    const task = await this.connection.getTask<ActivityInvocationPayload>(scheduled.task_id);
    if (task.state === 'succeeded') return task.result?.value;
    if (task.state === 'failed') {
      if (replay.isActivityCanceled(scheduled)) {
        throw new WorkflowQueryReady('activity cancelled');
      }
      if (replay.hasActivityRetryScheduled(scheduled)) {
        return this.replayActivityForQuery(replay, name);
      }
      throw ApplicationFailure.create({ message: task.error ?? 'activity failed', type: 'ActivityFailure' });
    }
    throw new WorkflowQueryReady(`waiting for activity ${name}`);
  }

  private async replayTimerForQuery(replay: WorkflowReplay): Promise<void> {
    if (replay.isCancellationRequested()) throw new WorkflowQueryReady('workflow cancelled');
    const started = replayCommand(() => replay.nextTimer());
    if (!started?.task_id || !replay.isTimerFired(started)) {
      throw new WorkflowQueryReady('waiting for timer');
    }
  }

  private async replayChildForQuery(replay: WorkflowReplay, name: string): Promise<unknown> {
    if (replay.isCancellationRequested()) throw new WorkflowQueryReady('workflow cancelled');
    const started = replayCommand(() => replay.nextChild(name));
    if (!started) {
      throw new WorkflowQueryReady();
    }
    const childWorkflowId = childWorkflowIdFromEvent(started);
    if (!childWorkflowId) {
      throw ApplicationFailure.nonRetryable('child workflow history is missing child workflow ID', 'InvalidChildWorkflowHistory');
    }
    const child = await this.connection.getWorkflow(childWorkflowRunIdFromEvent(started) ?? childWorkflowId);
    if (child.state === 'succeeded') return child.result?.value;
    if (child.state === 'failed') {
      throw ApplicationFailure.create({ message: child.error ?? 'child workflow failed', type: 'ChildWorkflowFailure' });
    }
    throw new WorkflowQueryReady(`waiting for child workflow ${name}`);
  }

  private async replayConditionForQuery(predicate: () => boolean): Promise<boolean> {
    // Query replay should stop once the workflow would block or observe cancellation.
    if (predicate()) return true;
    throw new WorkflowQueryReady('waiting for condition');
  }

  private throwIfCancelled(replay: WorkflowReplay, cancellationScope: 'cancellable' | 'non_cancellable' = 'cancellable'): void {
    if (cancellationScope === 'non_cancellable' || !replay.isCancellationRequested()) {
      return;
    }
    throw new CancelledFailure(replay.cancellationReason());
  }

  private async emit(
    taskId: string,
    kind: 'started' | 'heartbeat' | 'milestone' | 'progress' | 'completed' | 'failed',
    stage?: string,
    message?: string,
    details?: Record<string, unknown>,
  ): Promise<void> {
    await this.connection.appendTaskEvent(taskId, this.identity, { kind, stage, message, details });
  }

  private async withLeaseRenewal<T>(
    task: Task<WorkflowPayload | ActivityInvocationPayload | WorkflowQueryPayload | WorkflowUpdatePayload>,
    fn: () => Promise<T>,
  ): Promise<T> {
    let stopped = false;
    const controller = new AbortController();
    const leaseTimeoutSeconds = task.lease_timeout_seconds > 0 ? task.lease_timeout_seconds : 30;
    const intervalMs = Math.max(100, Math.floor((leaseTimeoutSeconds * 1000) / 3));
    const renew = async () => {
      await this.connection.heartbeatTask(task.id, this.identity, {
        kind: 'heartbeat',
        stage: 'lease',
        message: `renewed ${task.type} lease`,
      });
    };
    const loop = (async () => {
      while (!stopped) {
        await delay(intervalMs, controller.signal);
        if (stopped) return;
        try {
          await renew();
        } catch (err) {
          if (isTerminalTaskMutation(err)) {
            return;
          }
        }
      }
    })();
    try {
      return await fn();
    } finally {
      stopped = true;
      controller.abort();
      await loop;
    }
  }

}
class WorkflowBlocked extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'WorkflowBlocked';
  }
}

class WorkflowQueryReady extends Error {
  constructor(message = 'query handlers ready') {
    super(message);
    this.name = 'WorkflowQueryReady';
  }
}

/**
 * Per-invocation handler registries. Replay supplies the recorded signal and
 * update arguments; the runtime owns the handlers and invokes them.
 */
class WorkflowHandlers {
  private readonly queryHandlers = new Map<string, (...args: unknown[]) => unknown>();
  private readonly updateHandlers = new Map<string, (...args: unknown[]) => unknown>();

  constructor(private readonly replay: WorkflowReplay) {}

  setSignalHandler(name: string, handler: (...args: unknown[]) => unknown): void {
    for (const args of this.replay.signalArgs(name)) {
      handler(...args);
    }
  }

  setQueryHandler(name: string, handler: (...args: unknown[]) => unknown): void {
    this.queryHandlers.set(name, handler);
  }

  queryHandler(name: string): ((...args: unknown[]) => unknown) | undefined {
    return this.queryHandlers.get(name);
  }

  setUpdateHandler(name: string, handler: (...args: unknown[]) => unknown): void {
    this.updateHandlers.set(name, handler);
    for (const args of this.replay.completedUpdateArgs(name)) {
      handler(...args);
    }
  }

  updateHandler(name: string): ((...args: unknown[]) => unknown) | undefined {
    return this.updateHandlers.get(name);
  }
}

/** Runs one replay step, translating a replay-owned determinism error into the public failure. */
function replayCommand<T>(step: () => T): T {
  try {
    return step();
  } catch (err) {
    if (err instanceof DeterminismError) {
      throw determinismViolation(err.message);
    }
    throw err;
  }
}

function childWorkflowIdFromEvent(event: WorkflowHistoryEvent): string | undefined {
  const childWorkflowId = event.attributes?.child_workflow_id;
  return typeof childWorkflowId === 'string' ? childWorkflowId : undefined;
}

function childWorkflowRunIdFromEvent(event: WorkflowHistoryEvent): string | undefined {
  const childWorkflowRunId = event.attributes?.child_run_id;
  return typeof childWorkflowRunId === 'string' ? childWorkflowRunId : undefined;
}

function failureInfoFromError(err: unknown): FailureInfo {
  if (err instanceof ApplicationFailure) {
    return {
      message: err.message,
      type: err.type,
      non_retryable: err.nonRetryable,
      details: err.details,
    };
  }
  if (err instanceof CancelledFailure) {
    return {
      message: err.message,
      type: 'CancelledFailure',
      non_retryable: true,
    };
  }
  if (err instanceof Error) {
    return {
      message: err.message,
      type: err.name || 'Error',
    };
  }
  return {
    message: String(err),
    type: 'Error',
  };
}

function determinismViolation(message: string): ApplicationFailure {
  return ApplicationFailure.nonRetryable(message, 'DeterminismViolation');
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) return Promise.resolve();
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener('abort', () => {
      clearTimeout(timer);
      resolve();
    }, { once: true });
  });
}
