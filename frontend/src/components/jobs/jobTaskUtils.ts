import type { Job, JobTaskAttemptEvent, JobTaskRun } from '../../api';
import { ui } from '../../ui/tokens';

export type TaskCounts = {
  queued: number;
  running: number;
  done: number;
  failed: number;
  canceled: number;
};

const WORKFLOW_JOB_TYPES = new Set([
  'ocr_box',
  'ocr_page',
  'translate_box',
  'page_translation',
  'box_detection',
  'prepare_dataset',
  'train_model',
]);
const ACTIVE_JOB_STATUSES = new Set(['queued', 'running']);
const TERMINAL_TASK_STATUSES = new Set(['completed', 'failed', 'canceled', 'timed_out']);
const TERMINAL_JOB_STATUSES = new Set(['finished', 'failed', 'canceled']);

export function isWorkflowJob(job: Job): boolean {
  return WORKFLOW_JOB_TYPES.has(job.type);
}

export function isJobActive(job: Job): boolean {
  return ACTIVE_JOB_STATUSES.has(job.status);
}

export function isImplicitlyExpanded(job: Job): boolean {
  return job.type === 'ocr_box' || job.type === 'translate_box';
}

export function summarizeTaskCounts(tasks: JobTaskRun[]): TaskCounts {
  const counts: TaskCounts = {
    queued: 0,
    running: 0,
    done: 0,
    failed: 0,
    canceled: 0,
  };

  for (const task of tasks) {
    const status = String(task.status || '').trim();
    if (status === 'queued') {
      counts.queued += 1;
    } else if (status === 'running') {
      counts.running += 1;
    } else if (status === 'canceled') {
      counts.canceled += 1;
    } else if (status === 'failed' || status === 'timed_out') {
      counts.failed += 1;
    } else if (TERMINAL_TASK_STATUSES.has(status)) {
      counts.done += 1;
    }
  }

  return counts;
}

export function formatTaskTitle(task: JobTaskRun): string {
  const stage = String(task.stage || '').trim();
  if (stage !== 'ocr') {
    const stageLabel = taskTypeLabel(task);
    if (task.profile_id) {
      return `${stageLabel} | ${task.profile_id}`;
    }
    return stageLabel;
  }
  const boxId =
    typeof task.box_id === 'number' && Number.isFinite(task.box_id)
      ? `box #${task.box_id}`
      : 'box ?';
  if (task.profile_id) {
    return `${boxId} | ${task.profile_id}`;
  }
  return boxId;
}

export function taskStatusBadgeClass(status: string): string {
  const normalized = status.trim();
  if (normalized === 'completed') {
    return `${ui.statusBadgeBase} ${ui.statusBadgeFinished}`;
  }
  if (normalized === 'failed' || normalized === 'timed_out') {
    return `${ui.statusBadgeBase} ${ui.statusBadgeFailed}`;
  }
  if (normalized === 'canceled') {
    return `${ui.statusBadgeBase} ${ui.statusBadgeCanceled}`;
  }
  return `${ui.statusBadgeBase} ${ui.statusBadgeRunning}`;
}

export function taskTypeLabel(task: JobTaskRun): string {
  const stage = String(task.stage || '').trim();
  if (stage === 'ocr') {
    return 'ocr_box';
  }
  if (stage === 'translate_page') {
    return 'translate_page';
  }
  if (stage === 'translate_box') {
    return 'translate_box';
  }
  if (stage === 'merge_state') {
    return 'merge_state';
  }
  return stage || 'task';
}

export function taskProgressValue(status: string): number {
  const normalized = status.trim();
  if (normalized === 'completed') {
    return 100;
  }
  if (normalized === 'running') {
    return 50;
  }
  if (normalized === 'queued') {
    return 0;
  }
  return 100;
}

export function taskMessage(task: JobTaskRun): string | null {
  const result = task.result_json;
  if (!result) {
    return null;
  }
  const rawMessage = result.message;
  if (typeof rawMessage === 'string' && rawMessage.trim()) {
    return rawMessage.trim();
  }
  const rawText = result.text;
  if (typeof rawText === 'string' && rawText.trim()) {
    const trimmed = rawText.trim();
    const preview = trimmed.length > 96 ? `${trimmed.slice(0, 96).trimEnd()}...` : trimmed;
    if (String(task.stage || '').trim() === 'ocr') {
      return `OCR done: ${preview}`;
    }
    return preview;
  }
  const rawTranslation = result.translation;
  if (typeof rawTranslation === 'string' && rawTranslation.trim()) {
    const trimmed = rawTranslation.trim();
    const preview = trimmed.length > 96 ? `${trimmed.slice(0, 96).trimEnd()}...` : trimmed;
    return `Translation done: ${preview}`;
  }
  const rawError = result.error_message;
  if (typeof rawError === 'string' && rawError.trim()) {
    return rawError.trim();
  }
  if (typeof task.error_code === 'string' && task.error_code.trim()) {
    return task.error_code.trim();
  }
  return null;
}

export function formatDurationMs(ms: number): string {
  const safeMs = Number.isFinite(ms) ? Math.max(0, Math.trunc(ms)) : 0;
  if (safeMs < 1000) {
    return `${safeMs}ms`;
  }
  const totalSeconds = Math.floor(safeMs / 1000);
  const seconds = totalSeconds % 60;
  const totalMinutes = Math.floor(totalSeconds / 60);
  const minutes = totalMinutes % 60;
  const hours = Math.floor(totalMinutes / 60);

  if (hours > 0) {
    return `${hours}h ${String(minutes).padStart(2, '0')}m ${String(seconds).padStart(2, '0')}s`;
  }
  if (minutes > 0) {
    return `${minutes}m ${String(seconds).padStart(2, '0')}s`;
  }
  return `${totalSeconds}s`;
}

export function computeJobDurationMs(job: Job, nowMs: number): number | null {
  const status = String(job.status || '').trim();
  if (status === 'queued') {
    // Queue wait time is not execution time; hide duration until work actually runs.
    return null;
  }
  const createdMs = Number(job.created_at) * 1000;
  const updatedMs = Number(job.updated_at) * 1000;
  if (!Number.isFinite(createdMs) || createdMs <= 0) {
    return null;
  }
  const isTerminal = TERMINAL_JOB_STATUSES.has(status);
  const endMs = isTerminal
    ? updatedMs
    : Math.max(createdMs, Number.isFinite(nowMs) ? nowMs : createdMs);
  if (!Number.isFinite(endMs) || endMs < createdMs) {
    return null;
  }
  return Math.max(0, Math.trunc(endMs - createdMs));
}

export function parseStageDurationsMs(job: Job): Record<string, number> {
  const result = job.result;
  if (!result || typeof result !== 'object') {
    return {};
  }
  const raw = (result as { stage_durations_ms?: unknown }).stage_durations_ms;
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return {};
  }
  const out: Record<string, number> = {};
  for (const [key, value] of Object.entries(raw)) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed < 0) {
      continue;
    }
    out[key] = Math.trunc(parsed);
  }
  return out;
}

function parsePositiveInt(value: unknown): number | null {
  const parsed =
    typeof value === 'number' ? value : typeof value === 'string' ? Number(value) : Number.NaN;
  if (!Number.isFinite(parsed)) {
    return null;
  }
  const rounded = Math.trunc(parsed);
  return rounded > 0 ? rounded : null;
}

function parseReasoning(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null;
  }
  const normalized = value.trim();
  return normalized ? normalized : null;
}

function parseAttemptParams(event: JobTaskAttemptEvent): {
  maxTokens: number | null;
  reasoning: string | null;
} {
  const params = event.params_snapshot;
  if (!params || typeof params !== 'object') {
    return { maxTokens: null, reasoning: null };
  }
  return {
    maxTokens: parsePositiveInt(params.max_output_tokens),
    reasoning: parseReasoning(params.reasoning_effort),
  };
}

export function formatAttemptEvent(
  event: JobTaskAttemptEvent,
  previous: JobTaskAttemptEvent | null,
  options?: {
    hasLaterAttempt?: boolean;
    taskRunning?: boolean;
  },
): string {
  const curr = parseAttemptParams(event);
  const prev = previous ? parseAttemptParams(previous) : null;
  const parts: string[] = [];

  const finishReason =
    typeof event.finish_reason === 'string' && event.finish_reason.trim()
      ? event.finish_reason.trim()
      : 'unknown';
  const shouldMarkRetrying =
    (finishReason === 'invalid' || finishReason === 'error' || finishReason === 'timed_out') &&
    (Boolean(options?.hasLaterAttempt) || Boolean(options?.taskRunning));
  parts.push(
    `Attempt ${Math.max(1, event.attempt)}: ${
      shouldMarkRetrying ? `${finishReason} (retrying)` : finishReason
    }`,
  );

  if (curr.maxTokens !== null) {
    if (prev && prev.maxTokens !== null) {
      if (prev.maxTokens !== curr.maxTokens) {
        parts.push(`max ${prev.maxTokens}->${curr.maxTokens}`);
      } else {
        parts.push(`max ${curr.maxTokens} (same)`);
      }
    } else {
      parts.push(`max ${curr.maxTokens}`);
    }
  }

  if (curr.reasoning) {
    if (prev?.reasoning) {
      if (prev.reasoning !== curr.reasoning) {
        parts.push(`reasoning ${prev.reasoning}->${curr.reasoning}`);
      } else {
        parts.push(`reasoning ${curr.reasoning} (same)`);
      }
    } else {
      parts.push(`reasoning ${curr.reasoning}`);
    }
  }

  if (event.model_id?.trim()) {
    parts.push(event.model_id.trim());
  }

  if (typeof event.latency_ms === 'number' && Number.isFinite(event.latency_ms)) {
    parts.push(`${Math.max(0, Math.trunc(event.latency_ms))}ms`);
  }

  if (event.error_detail?.trim()) {
    const err = event.error_detail.trim();
    const clipped = err.length > 120 ? `${err.slice(0, 120).trimEnd()}...` : err;
    parts.push(clipped);
  }

  return parts.join(' | ');
}

export function areTasksEqual(a: JobTaskRun[], b: JobTaskRun[]): boolean {
  if (a.length !== b.length) {
    return false;
  }
  for (let idx = 0; idx < a.length; idx += 1) {
    const left = a[idx];
    const right = b[idx];
    if (
      left.id !== right.id ||
      left.status !== right.status ||
      left.attempt !== right.attempt ||
      left.error_code !== right.error_code ||
      left.profile_id !== right.profile_id ||
      left.box_id !== right.box_id
    ) {
      return false;
    }
    const leftEvents = Array.isArray(left.attempt_events) ? left.attempt_events : [];
    const rightEvents = Array.isArray(right.attempt_events) ? right.attempt_events : [];
    if (leftEvents.length !== rightEvents.length) {
      return false;
    }
    for (let eventIdx = 0; eventIdx < leftEvents.length; eventIdx += 1) {
      const l = leftEvents[eventIdx];
      const r = rightEvents[eventIdx];
      if (
        l.id !== r.id ||
        l.attempt !== r.attempt ||
        l.finish_reason !== r.finish_reason ||
        l.latency_ms !== r.latency_ms ||
        l.error_detail !== r.error_detail
      ) {
        return false;
      }
      const lParams = l.params_snapshot ?? null;
      const rParams = r.params_snapshot ?? null;
      if (
        (lParams?.max_output_tokens ?? null) !== (rParams?.max_output_tokens ?? null) ||
        (lParams?.reasoning_effort ?? null) !== (rParams?.reasoning_effort ?? null)
      ) {
        return false;
      }
    }
  }
  return true;
}
