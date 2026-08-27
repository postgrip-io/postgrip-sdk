interface MilestoneOptions {
  index?: number;
  total?: number;
  status?: 'started' | 'completed' | 'failed' | 'skipped';
  details?: Record<string, unknown>;
}

interface MilestoneEvent {
  kind: 'milestone';
  stage: 'milestone';
  message: string;
  details: Record<string, unknown>;
}

export function milestoneEvent(name: string, options: MilestoneOptions): MilestoneEvent {
  const status = options.status ?? 'completed';
  const prefix = options.index == null || options.total == null
    ? ''
    : `step ${options.index}/${options.total} `;
  return {
    kind: 'milestone',
    stage: 'milestone',
    message: `${prefix}${status} ${name}`.trim(),
    details: {
      ...(options.details ?? {}),
      milestone: true,
      name,
      status,
      ...(options.index == null ? {} : { index: options.index }),
      ...(options.total == null ? {} : { total: options.total }),
    },
  };
}
