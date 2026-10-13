import type {
  Task,
  WorkflowExecution,
  WorkflowExecutionDescription,
  WorkflowPayload,
  WorkflowUIMetadata,
} from './types.js';

const POSTGRIP_UI_MEMO_KEY = 'postgrip.ui';

export function memoWithWorkflowUI(
  memo?: Record<string, unknown>,
  ui?: WorkflowUIMetadata,
): Record<string, unknown> | undefined {
  if (!ui) return memo;
  const cleanUI: WorkflowUIMetadata = {};
  if (ui.displayName?.trim()) cleanUI.displayName = ui.displayName.trim();
  if (ui.description?.trim()) cleanUI.description = ui.description.trim();
  if (ui.tags?.length) {
    const tags = ui.tags.map((tag) => tag.trim()).filter(Boolean);
    if (tags.length) cleanUI.tags = tags;
  }
  if (ui.details) {
    const details = Object.fromEntries(
      Object.entries(ui.details)
        .map(([key, value]) => [key.trim(), value] as const)
        .filter(([key]) => key !== ''),
    );
    if (Object.keys(details).length > 0) cleanUI.details = details;
  }
  if (Object.keys(cleanUI).length === 0) return memo;
  return { ...(memo ?? {}), [POSTGRIP_UI_MEMO_KEY]: cleanUI };
}

export function describeWorkflowTask<R>(task: Task<WorkflowPayload, R>): WorkflowExecutionDescription<R> {
  return {
    workflowId: task.payload?.workflowId ?? task.id,
    runId: task.payload?.runId,
    taskId: task.id,
    namespace: task.namespace,
    taskQueue: task.queue,
    workflowType: task.payload?.workflowType ?? task.type.replace(/^workflow:/, ''),
    status: task.state,
    attempt: task.attempt,
    leaseTimeoutSeconds: task.lease_timeout_seconds,
    workflowRunTimeoutMs: task.payload?.runTimeoutMs,
    retry: task.payload?.retry,
    memo: task.payload?.memo,
    searchAttributes: task.payload?.searchAttributes,
    result: task.result?.value,
    error: task.error,
    startedAt: task.created_at,
    updatedAt: task.updated_at,
  };
}

export function describeWorkflowExecution<R>(workflow: WorkflowExecution<R>): WorkflowExecutionDescription<R> {
  return {
    workflowId: workflow.id,
    runId: workflow.run_id,
    taskId: workflow.task_id,
    namespace: workflow.namespace,
    taskQueue: workflow.queue,
    workflowType: workflow.type,
    status: workflow.state === 'running' ? 'leased' : workflow.state,
    attempt: workflow.attempt,
    workflowRunTimeoutMs: workflow.run_timeout_ms,
    retry: workflow.retry,
    memo: workflow.memo,
    searchAttributes: workflow.search_attributes,
    result: workflow.result?.value as R,
    error: workflow.error,
    startedAt: workflow.created_at,
    updatedAt: workflow.updated_at,
  };
}
