// src/components/logs/LogsLayout.tsx
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  clearLlmCallLogs,
  deleteLlmCallLog,
  fetchLlmCallLog,
  fetchLlmCallLogs,
  type LlmCallLogDetailResponse,
  type LlmCallLogItem,
} from '../../api';
import { Button } from '../../ui/primitives';
import { ui } from '../../ui/tokens';
import { JobsPanel } from '../JobsPanel';

function formatTimestamp(value: number): string {
  if (!value) return '-';
  const date = new Date(value * 1000);
  return date.toLocaleString();
}

function formatJson(value: unknown): string {
  if (value === null || value === undefined) {
    return '';
  }
  if (typeof value === 'string') {
    const text = value.trim();
    if (!text) return '';
    try {
      return JSON.stringify(JSON.parse(text), null, 2);
    } catch {
      return text;
    }
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function compactCorrelation(log: LlmCallLogItem): string {
  const parts: string[] = [];
  if (log.volume_id || log.filename) {
    parts.push([log.volume_id, log.filename].filter((value) => Boolean(value)).join(' / '));
  }
  if (log.box_id !== null && log.box_id !== undefined) {
    parts.push(`box ${log.box_id}`);
  }
  if (log.profile_id) {
    parts.push(log.profile_id);
  }
  if (log.session_id) {
    parts.push(`session ${log.session_id}`);
  } else if (log.job_id) {
    parts.push(`job ${log.job_id}`);
  }
  return parts.join(' · ');
}

export function LogsLayout() {
  const [logs, setLogs] = useState<LlmCallLogItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<LlmCallLogDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<'all' | 'success' | 'error'>('all');
  const [showPayload, setShowPayload] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchLlmCallLogs({
        limit: 400,
        status: statusFilter === 'all' ? undefined : statusFilter,
      });
      setLogs(data);
      setSelectedId((currentId) => {
        if (data.length === 0) {
          return null;
        }
        if (!currentId || !data.some((item) => item.id === currentId)) {
          return data[0].id;
        }
        return currentId;
      });
      if (data.length === 0) {
        setDetail(null);
      }
    } catch (err) {
      console.error('Failed to load LLM logs', err);
      setError('Failed to load LLM logs.');
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    setShowPayload(false);
    let cancelled = false;
    const load = async () => {
      setDetailError(null);
      try {
        const data = await fetchLlmCallLog(selectedId);
        if (cancelled) return;
        setDetail(data);
      } catch (err) {
        console.error('Failed to load LLM log detail', err);
        if (cancelled) return;
        setDetailError('Failed to load log detail.');
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const selectedLog = useMemo(
    () => logs.find((log) => log.id === selectedId) ?? null,
    [logs, selectedId],
  );

  const paramsText = useMemo(() => formatJson(detail?.params_snapshot ?? null), [detail]);
  const payloadText = useMemo(() => {
    if (!detail) return '';
    const jsonText = formatJson(detail.payload_json);
    if (jsonText) return jsonText;
    return detail.payload_raw ?? '';
  }, [detail]);
  const requestText = useMemo(() => formatJson(detail?.request_excerpt ?? ''), [detail]);
  const responseText = useMemo(() => formatJson(detail?.response_excerpt ?? ''), [detail]);
  const correlationText = useMemo(() => {
    if (!detail) return '';
    const correlation = {
      job_id: detail.log.job_id ?? undefined,
      workflow_run_id: detail.log.workflow_run_id ?? undefined,
      task_run_id: detail.log.task_run_id ?? undefined,
      session_id: detail.log.session_id ?? undefined,
      volume_id: detail.log.volume_id ?? undefined,
      filename: detail.log.filename ?? undefined,
      box_id: detail.log.box_id ?? undefined,
      profile_id: detail.log.profile_id ?? undefined,
      request_id: detail.log.request_id ?? undefined,
    };
    return formatJson(correlation);
  }, [detail]);

  const handleCopy = async (label: string, value: string) => {
    if (!value.trim()) {
      return;
    }
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
      } else {
        const textarea = document.createElement('textarea');
        textarea.value = value;
        textarea.style.position = 'fixed';
        textarea.style.left = '-9999px';
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
      }
      setCopyMessage(`${label} copied.`);
      setTimeout(() => setCopyMessage(null), 1500);
    } catch {
      setCopyMessage(null);
    }
  };

  const handleDelete = async () => {
    if (!selectedId) return;
    setDeleting(true);
    try {
      await deleteLlmCallLog(selectedId);
      await refresh();
    } catch (err) {
      console.error('Failed to delete LLM log', err);
      setError('Failed to delete log.');
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteAll = async () => {
    setDeleting(true);
    try {
      await clearLlmCallLogs();
      await refresh();
    } catch (err) {
      console.error('Failed to clear LLM logs', err);
      setError('Failed to clear logs.');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="flex-1 flex overflow-hidden">
      <JobsPanel />
      <main className={ui.trainingMain}>
        <section className={ui.trainingSection}>
          <div className={ui.trainingSectionHeader}>
            <div>
              <div className={ui.trainingSectionTitle}>LLM Call Logs</div>
              <div className={ui.trainingSectionMeta}>
                Central request/response capture across OCR, translation, and agent flows
              </div>
            </div>
            <div className="flex items-center gap-2">
              <select
                className={`${ui.select} w-28`}
                value={statusFilter}
                onChange={(event) =>
                  setStatusFilter(event.target.value as 'all' | 'success' | 'error')
                }
              >
                <option value="all">All</option>
                <option value="success">Success</option>
                <option value="error">Error</option>
              </select>
              <Button
                type="button"
                variant="ghostSmall"
                onClick={() => void refresh()}
                disabled={loading}
              >
                Refresh
              </Button>
              <Button
                type="button"
                variant="actionDangerSmall"
                onClick={handleDeleteAll}
                disabled={loading || deleting || logs.length === 0}
              >
                Delete all
              </Button>
            </div>
          </div>

          {error && <div className={ui.trainingError}>{error}</div>}

          <div className="mt-4 grid gap-4 lg:grid-cols-[320px_1fr]">
            <div className={ui.trainingCard}>
              <div className={ui.trainingSubTitle}>Calls</div>
              <div className="mt-3 space-y-2 max-h-[70vh] overflow-y-auto pr-1">
                {logs.length === 0 && <div className={ui.trainingHelp}>No logs yet.</div>}
                {logs.map((log) => {
                  const active = selectedId === log.id;
                  return (
                    <button
                      key={log.id}
                      type="button"
                      className={`w-full text-left rounded-md border px-2 py-1.5 text-xs ${
                        active
                          ? 'border-emerald-400 bg-emerald-500/10 text-emerald-100'
                          : 'border-slate-800 bg-slate-950/60 text-slate-300 hover:border-slate-600'
                      }`}
                      onClick={() => setSelectedId(log.id)}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="truncate font-medium">{log.component}</div>
                        <div
                          className={`text-[10px] ${
                            log.status === 'success' ? 'text-emerald-300' : 'text-rose-300'
                          }`}
                        >
                          {log.status}
                        </div>
                      </div>
                      <div className={ui.trainingMetaSmall}>
                        {log.model_id || '-'} · {log.api}
                      </div>
                      <div className={ui.trainingMetaSmall}>{formatTimestamp(log.created_at)}</div>
                      {compactCorrelation(log) && (
                        <div className={ui.trainingMetaSmall}>{compactCorrelation(log)}</div>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className={ui.trainingCard}>
              <div className={ui.trainingSectionHeader}>
                <div>
                  <div className={ui.trainingSectionTitle}>Detail</div>
                  <div className={ui.trainingSectionMeta}>
                    {selectedLog
                      ? `${selectedLog.id} · ${formatTimestamp(selectedLog.created_at)}`
                      : 'Select a call'}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {detail && (
                    <>
                      <Button
                        type="button"
                        variant="ghostSmall"
                        onClick={() => setShowPayload(false)}
                        disabled={!showPayload}
                      >
                        Request/Response
                      </Button>
                      <Button
                        type="button"
                        variant="ghostSmall"
                        onClick={() => setShowPayload(true)}
                        disabled={showPayload}
                      >
                        Full payload
                      </Button>
                    </>
                  )}
                  <Button
                    type="button"
                    variant="actionDangerSmall"
                    onClick={handleDelete}
                    disabled={!selectedId || deleting}
                  >
                    Delete
                  </Button>
                </div>
              </div>

              {detailError && <div className={ui.trainingError}>{detailError}</div>}
              {copyMessage && <div className={ui.trainingMetaSmall}>{copyMessage}</div>}

              {!detail && !detailError && (
                <div className={ui.trainingHelp}>
                  Pick a log entry to inspect prompts and response.
                </div>
              )}

              {detail && (
                <div className="mt-2 space-y-3">
                  <div className={ui.trainingMetaSmall}>
                    Latency: {detail.log.latency_ms ?? '-'}ms · Tokens:{' '}
                    {detail.log.input_tokens ?? '-'} / {detail.log.output_tokens ?? '-'} /{' '}
                    {detail.log.total_tokens ?? '-'} · Finish: {detail.log.finish_reason || '-'}
                  </div>
                  {detail.log.error_detail && (
                    <div className={ui.trainingError}>{detail.log.error_detail}</div>
                  )}

                  {!showPayload && (
                    <div className="space-y-3">
                      <div>
                        <div className={ui.trainingLabelSmall}>Correlation</div>
                        <pre
                          className={`${ui.trainingLogBox} mt-2 p-3 whitespace-pre-wrap break-words`}
                        >
                          {correlationText || '-'}
                        </pre>
                      </div>
                      <div>
                        <div className="flex items-center justify-between">
                          <div className={ui.trainingLabelSmall}>Params snapshot</div>
                          <Button
                            type="button"
                            variant="ghostSmall"
                            onClick={() => void handleCopy('Params', paramsText)}
                            disabled={!paramsText}
                          >
                            Copy
                          </Button>
                        </div>
                        <pre
                          className={`${ui.trainingLogBox} mt-2 p-3 whitespace-pre-wrap break-words`}
                        >
                          {paramsText || '-'}
                        </pre>
                      </div>
                      <div>
                        <div className="flex items-center justify-between">
                          <div className={ui.trainingLabelSmall}>Request excerpt</div>
                          <Button
                            type="button"
                            variant="ghostSmall"
                            onClick={() => void handleCopy('Request', requestText)}
                            disabled={!requestText}
                          >
                            Copy
                          </Button>
                        </div>
                        <pre
                          className={`${ui.trainingLogBox} mt-2 p-3 whitespace-pre-wrap break-words`}
                        >
                          {requestText || '-'}
                        </pre>
                      </div>
                      <div>
                        <div className="flex items-center justify-between">
                          <div className={ui.trainingLabelSmall}>Response excerpt</div>
                          <Button
                            type="button"
                            variant="ghostSmall"
                            onClick={() => void handleCopy('Response', responseText)}
                            disabled={!responseText}
                          >
                            Copy
                          </Button>
                        </div>
                        <pre
                          className={`${ui.trainingLogBox} mt-2 p-3 whitespace-pre-wrap break-words`}
                        >
                          {responseText || '-'}
                        </pre>
                      </div>
                    </div>
                  )}

                  {showPayload && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-end">
                        <Button
                          type="button"
                          variant="ghostSmall"
                          onClick={() => void handleCopy('Full payload', payloadText)}
                          disabled={!payloadText}
                        >
                          Copy
                        </Button>
                      </div>
                      <pre className={`${ui.trainingLogBox} p-3 whitespace-pre-wrap break-words`}>
                        {payloadText || '-'}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
