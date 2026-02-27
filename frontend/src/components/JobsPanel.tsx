// src/components/JobsPanel.tsx
import { useEffect, useMemo, useState } from "react";

import { useJobs } from "../context/useJobs";
import { ui } from "../ui/tokens";
import { getProgressDisplay } from "../utils/progress";
import {
    computeJobDurationMs,
    formatAttemptEvent,
    formatDurationMs,
    formatTaskTitle,
    isImplicitlyExpanded,
    isWorkflowJob,
    parseStageDurationsMs,
    summarizeTaskCounts,
    taskTypeLabel,
    taskMessage,
    taskProgressValue,
    taskStatusBadgeClass,
} from "./jobs/jobTaskUtils";
import { useJobTasks } from "./jobs/useJobTasks";

export function JobsPanel() {
    const { jobs, jobsError, jobsLoading, clearFinished, cancelJob, deleteJob } =
        useJobs();
    const [nowMs, setNowMs] = useState<number>(() => Date.now());

    const sortedJobs = useMemo(
        () => jobs.slice().sort((a, b) => b.created_at - a.created_at),
        [jobs],
    );
    const hasActiveJobs = useMemo(
        () =>
            sortedJobs.some(
                (job) => job.status === "running" || job.status === "queued",
            ),
        [sortedJobs],
    );

    useEffect(() => {
        if (!hasActiveJobs) {
            return undefined;
        }
        const timerId = window.setInterval(() => {
            setNowMs(Date.now());
        }, 1000);
        return () => window.clearInterval(timerId);
    }, [hasActiveJobs]);

    const { expandedJobs, setExpandedJobs, jobTasks } = useJobTasks(sortedJobs);

    return (
        <aside className={ui.jobsPanel}>
            <div className="flex-1 overflow-y-auto p-4">
                <div className={ui.jobsHeader}>
                    <h2 className={ui.jobsTitle}>Jobs</h2>
                    <div className="flex items-center gap-2">
                        {jobsLoading && (
                            <span className={ui.mutedTextMicro}>Loading...</span>
                        )}
                        <button
                            type="button"
                            className={ui.jobsButtonSmall}
                            onClick={clearFinished}
                        >
                            Clear done
                        </button>
                    </div>
                </div>

                {jobsError && <div className={`mb-2 ${ui.errorTextXs}`}>{jobsError}</div>}

                {sortedJobs.length === 0 && !jobsError && (
                    <div className={ui.mutedTextXs}>No jobs yet.</div>
                )}

                {sortedJobs.length > 0 && (
                    <ul className={ui.jobsList}>
                        {sortedJobs.map((job) => {
                            const payload = job.payload as {
                                dataset_id?: string;
                                filename?: string;
                                boxId?: number;
                                boxOrder?: number;
                                task?: string;
                                modelId?: string;
                                reasoningEffort?: string;
                                maxOutputTokens?: number;
                                model_id?: string;
                                reasoning_effort?: string;
                                max_output_tokens?: number;
                            };
                            const detailParts: string[] = [];
                            const isWorkflow = isWorkflowJob(job);
                            const tasksState = jobTasks[job.id];
                            const tasks = tasksState?.tasks ?? [];
                            const taskCounts = summarizeTaskCounts(tasks);
                            const taskTotal = tasks.length;
                            const forceExpanded = isImplicitlyExpanded(job);
                            const expanded = forceExpanded || Boolean(expandedJobs[job.id]);
                            const renderAsSingleTask = job.type === "ocr_box";
                            const singleTask = renderAsSingleTask ? tasks[0] : null;
                            const resultDurationRaw =
                                job.result && typeof job.result === "object"
                                    ? (job.result as { duration_ms?: unknown }).duration_ms
                                    : null;
                            const resultDurationMs = Number(resultDurationRaw);
                            const isTerminalJob =
                                job.status === "finished" ||
                                job.status === "failed" ||
                                job.status === "canceled";
                            const durationMs =
                                isTerminalJob && Number.isFinite(resultDurationMs)
                                    ? Math.max(0, Math.trunc(resultDurationMs))
                                    : computeJobDurationMs(job, nowMs);
                            const stageDurations =
                                job.type === "agent_translate_page"
                                    ? parseStageDurationsMs(job)
                                    : {};
                            const orderedStageIds = ["detect", "ocr", "translate", "commit"];
                            const orderedStageParts = orderedStageIds
                                .filter((stageId) => Number.isFinite(stageDurations[stageId]))
                                .map(
                                    (stageId) =>
                                        `${stageId} ${formatDurationMs(stageDurations[stageId])}`,
                                );
                            const extraStageParts = Object.entries(stageDurations)
                                .filter(([stageId, stageMs]) => {
                                    if (orderedStageIds.includes(stageId)) {
                                        return false;
                                    }
                                    return Number.isFinite(stageMs);
                                })
                                .map(
                                    ([stageId, stageMs]) =>
                                        `${stageId} ${formatDurationMs(stageMs)}`,
                                );
                            const stageDurationLine = [...orderedStageParts, ...extraStageParts];

                            if (
                                (job.type === "ocr_box" || job.type === "translate_box") &&
                                (Number.isFinite(Number(payload?.boxOrder)) ||
                                    Number.isFinite(Number(payload?.boxId)))
                            ) {
                                const orderValue = Number.isFinite(Number(payload?.boxOrder))
                                    ? Number(payload?.boxOrder)
                                    : Number(payload?.boxId);
                                detailParts.push(`box #${orderValue}`);
                            } else if (
                                (job.type === "prepare_dataset" ||
                                    job.type === "train_model") &&
                                payload?.dataset_id
                            ) {
                                detailParts.push(`dataset ${String(payload.dataset_id)}`);
                            } else if (job.type === "box_detection" && payload?.task) {
                                detailParts.push(String(payload.task));
                            }

                            if (payload?.filename) {
                                detailParts.push(String(payload.filename));
                            }

                            const detail = detailParts.join(" | ");
                            const singleTaskSummary =
                                singleTask && payload?.filename
                                    ? `${formatTaskTitle(singleTask)} | ${String(payload.filename)}`
                                    : singleTask
                                      ? formatTaskTitle(singleTask)
                                      : detail;
                            const modelId =
                                payload?.modelId ??
                                (payload as { model_id?: string })?.model_id;
                            const reasoningEffort =
                                payload?.reasoningEffort ??
                                (payload as { reasoning_effort?: string }).reasoning_effort;
                            const maxOutputTokensRaw =
                                payload?.maxOutputTokens ??
                                (payload as { max_output_tokens?: number }).max_output_tokens;
                            const maxOutputTokens = Number.isFinite(Number(maxOutputTokensRaw))
                                ? Number(maxOutputTokensRaw)
                                : null;
                            const modelMetaParts: string[] = [];
                            if (modelId) {
                                modelMetaParts.push(`Model: ${String(modelId)}`);
                            }
                            if (reasoningEffort) {
                                modelMetaParts.push(`Reasoning: ${String(reasoningEffort)}`);
                            }
                            if (maxOutputTokens !== null) {
                                modelMetaParts.push(`Max: ${maxOutputTokens}`);
                            }
                            const modelMeta =
                                modelMetaParts.length > 0 ? modelMetaParts.join(" | ") : "";
                            const canDelete =
                                job.status === "finished" ||
                                job.status === "failed" ||
                                job.status === "canceled";
                            const parentProgressDisplay = getProgressDisplay(job.progress);
                            const singleTaskProgressDisplay = singleTask
                                ? getProgressDisplay(taskProgressValue(String(singleTask.status)))
                                : null;
                            const singleTaskAttemptEvents =
                                singleTask && Array.isArray(singleTask.attempt_events)
                                    ? singleTask.attempt_events
                                          .slice()
                                          .sort((a, b) => {
                                              const attemptDelta = a.attempt - b.attempt;
                                              if (attemptDelta !== 0) {
                                                  return attemptDelta;
                                              }
                                              return a.id - b.id;
                                          })
                                    : [];
                            const singleTaskAttemptCount = singleTask
                                ? Math.max(
                                      1,
                                      Number.isFinite(Number(singleTask.attempt))
                                          ? Number(singleTask.attempt)
                                          : 0,
                                      singleTaskAttemptEvents.reduce(
                                          (max, event) =>
                                              Math.max(
                                                  max,
                                                  Number.isFinite(Number(event.attempt))
                                                      ? Number(event.attempt)
                                                      : 0,
                                              ),
                                          0,
                                      ),
                                  )
                                : null;
                            const singleTaskMessage = singleTask ? taskMessage(singleTask) : null;

                            return (
                                <li key={job.id} className={ui.jobsCard}>
                                    <div className="mb-0.5 flex items-center justify-between gap-2">
                                        <span className={ui.jobsType}>{job.type}</span>
                                        <div className="flex items-center gap-1">
                                            {job.status === "running" && (
                                                <button
                                                    type="button"
                                                    onClick={() => cancelJob(job.id)}
                                                    className={ui.button.jobsStop}
                                                >
                                                    Stop
                                                </button>
                                            )}
                                            {canDelete && (
                                                <button
                                                    type="button"
                                                    onClick={() => deleteJob(job.id)}
                                                    className={ui.jobsButtonTiny}
                                                    aria-label="Delete job"
                                                >
                                                    x
                                                </button>
                                            )}
                                            <span
                                                className={
                                                    ui.statusBadgeBase +
                                                    " " +
                                                    (job.status === "finished"
                                                        ? ui.statusBadgeFinished
                                                        : job.status === "failed"
                                                          ? ui.statusBadgeFailed
                                                          : job.status === "canceled"
                                                            ? ui.statusBadgeCanceled
                                                            : ui.statusBadgeRunning)
                                                }
                                            >
                                                {job.status}
                                            </span>
                                        </div>
                                    </div>

                                    {singleTask ? (
                                        <div className={ui.jobsDetail}>{singleTaskSummary}</div>
                                    ) : (
                                        detail && <div className={ui.jobsDetail}>{detail}</div>
                                    )}

                                    {modelMeta &&
                                        (job.type === "ocr_box" ||
                                            job.type === "translate_box") && (
                                            <div className={`mt-1 ${ui.jobsMeta}`}>{modelMeta}</div>
                                        )}
                                    {durationMs !== null && (
                                        <div className={`mt-1 ${ui.jobsMeta}`}>
                                            Duration: {formatDurationMs(durationMs)}
                                        </div>
                                    )}
                                    {stageDurationLine.length > 0 && (
                                        <div className={`mt-1 ${ui.jobsMeta}`}>
                                            Stages: {stageDurationLine.join(" | ")}
                                        </div>
                                    )}

                                    {job.type === "train_model" && job.metrics?.device && (
                                        <div className={`mt-1 ${ui.jobsMeta}`}>
                                            Device: {String(job.metrics.device)}
                                        </div>
                                    )}

                                    {(singleTaskMessage || job.message) && (
                                        <div className={ui.jobsMessage}>
                                            {singleTaskMessage || job.message}
                                        </div>
                                    )}

                                    {job.warnings && job.warnings.length > 0 && (
                                        <div className={`mt-1 ${ui.warningTextTiny}`}>
                                            {job.warnings.join(" | ")}
                                        </div>
                                    )}

                                    {singleTask &&
                                        typeof singleTaskAttemptCount === "number" && (
                                            <div className={`mt-1 ${ui.jobsMeta}`}>
                                                attempts {singleTaskAttemptCount} |{" "}
                                                {singleTask.profile_id || "unknown_profile"}
                                            </div>
                                        )}

                                    {singleTask && singleTaskAttemptEvents.length > 0 && (
                                        <div className="mt-1 space-y-0.5">
                                            {singleTaskAttemptEvents.map((event, eventIdx) => (
                                                <div
                                                    key={event.id}
                                                    className={ui.mutedTextMicro}
                                                >
                                                    {formatAttemptEvent(
                                                        event,
                                                        eventIdx > 0
                                                            ? singleTaskAttemptEvents[eventIdx - 1]
                                                            : null,
                                                        {
                                                            hasLaterAttempt:
                                                                eventIdx <
                                                                singleTaskAttemptEvents.length - 1,
                                                            taskRunning:
                                                                String(singleTask.status).trim() ===
                                                                "running",
                                                        },
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    )}

                                    {(singleTask
                                        ? singleTaskProgressDisplay?.progress
                                        : parentProgressDisplay.progress) !== null && (
                                        <div className="mt-1">
                                            <div className={ui.progressTrack}>
                                                <div
                                                    className={ui.progressFill}
                                                    style={{
                                                        width: `${
                                                            singleTask
                                                                ? singleTaskProgressDisplay?.width
                                                                : parentProgressDisplay.width
                                                        }%`,
                                                    }}
                                                />
                                            </div>
                                            <div className={`mt-1 ${ui.jobsMeta}`}>
                                                {singleTask
                                                    ? singleTaskProgressDisplay?.label
                                                    : parentProgressDisplay.label}
                                            </div>
                                        </div>
                                    )}

                                    {isWorkflow && !renderAsSingleTask && (
                                        <div className="mt-1">
                                            <div className="flex items-center justify-between gap-2">
                                                <div className={ui.jobsMeta}>
                                                    Tasks: {taskCounts.running} running |{" "}
                                                    {taskCounts.queued} queued | {taskCounts.done} done
                                                    {" | "}
                                                    {taskCounts.failed} failed | {taskCounts.canceled}{" "}
                                                    canceled
                                                    {taskTotal > 0 ? ` (${taskTotal})` : ""}
                                                </div>
                                                {!forceExpanded && (
                                                    <button
                                                        type="button"
                                                        className={ui.jobsButtonTiny}
                                                        onClick={() =>
                                                            setExpandedJobs((prev) => ({
                                                                ...prev,
                                                                [job.id]: !prev[job.id],
                                                            }))
                                                        }
                                                    >
                                                        {expanded ? "Hide" : "Show"}
                                                    </button>
                                                )}
                                            </div>
                                            {tasksState?.error && (
                                                <div className={`mt-1 ${ui.errorTextXs}`}>
                                                    {tasksState.error}
                                                </div>
                                            )}
                                            {expanded && (
                                                <div className="mt-1 max-h-56 overflow-y-auto rounded border border-slate-800 bg-slate-950/50 p-1">
                                                    {taskTotal === 0 && !tasksState?.loading && (
                                                        <div className={`px-1 py-1 ${ui.mutedTextTiny}`}>
                                                            No child tasks yet.
                                                        </div>
                                                    )}
                                                    {tasksState?.loading && taskTotal === 0 && (
                                                        <div className={`px-1 py-1 ${ui.mutedTextTiny}`}>
                                                            Loading tasks...
                                                        </div>
                                                    )}
                                                    {taskTotal > 0 && (
                                                        <ul className="space-y-1">
                                                            {tasks.map((task) => {
                                                                const attempt =
                                                                    typeof task.attempt === "number"
                                                                        ? task.attempt
                                                                        : 0;
                                                                const summary =
                                                                    formatTaskTitle(task) +
                                                                    (payload?.filename
                                                                        ? ` | ${String(payload.filename)}`
                                                                        : "");
                                                                const message = taskMessage(task);
                                                                const attemptEvents = Array.isArray(
                                                                    task.attempt_events,
                                                                )
                                                                    ? task.attempt_events
                                                                          .slice()
                                                                          .sort((a, b) => {
                                                                              const attemptDelta =
                                                                                  a.attempt - b.attempt;
                                                                              if (attemptDelta !== 0) {
                                                                                  return attemptDelta;
                                                                              }
                                                                              return a.id - b.id;
                                                                          })
                                                                    : [];
                                                                const attemptCountFromEvents =
                                                                    attemptEvents.reduce(
                                                                        (max, event) =>
                                                                            Math.max(
                                                                                max,
                                                                                Number.isFinite(
                                                                                    Number(event.attempt),
                                                                                )
                                                                                    ? Number(event.attempt)
                                                                                    : 0,
                                                                            ),
                                                                        0,
                                                                    );
                                                                const attemptCount = Math.max(
                                                                    Math.max(1, attempt),
                                                                    attemptCountFromEvents,
                                                                );
                                                                const progressDisplay = getProgressDisplay(
                                                                    taskProgressValue(
                                                                        String(task.status),
                                                                    ),
                                                                );
                                                                return (
                                                                    <li
                                                                        key={task.id}
                                                                        className={ui.jobsCard}
                                                                    >
                                                                        <div className="mb-0.5 flex items-center justify-between gap-2">
                                                                            <span className={ui.jobsType}>
                                                                                {taskTypeLabel(task)}
                                                                            </span>
                                                                            <span
                                                                                className={taskStatusBadgeClass(
                                                                                    String(task.status),
                                                                                )}
                                                                            >
                                                                                {task.status}
                                                                            </span>
                                                                        </div>
                                                                        <div className={ui.jobsDetail}>
                                                                            {summary}
                                                                        </div>
                                                                        {message && (
                                                                            <div className={ui.jobsMessage}>
                                                                                {message}
                                                                            </div>
                                                                        )}
                                                                        <div className={`mt-1 ${ui.jobsMeta}`}>
                                                                            attempts {attemptCount}
                                                                            {task.profile_id
                                                                                ? ` | ${task.profile_id}`
                                                                                : ""}
                                                                        </div>
                                                                        {attemptEvents.length > 0 && (
                                                                            <div className="mt-1 space-y-0.5">
                                                                                {attemptEvents.map(
                                                                                    (event, eventIdx) => (
                                                                                        <div
                                                                                            key={event.id}
                                                                                            className={
                                                                                                ui.mutedTextMicro
                                                                                            }
                                                                                        >
                                                                                            {formatAttemptEvent(
                                                                                                event,
                                                                                                eventIdx >
                                                                                                    0
                                                                                                    ? attemptEvents[
                                                                                                          eventIdx -
                                                                                                              1
                                                                                                      ]
                                                                                                    : null,
                                                                                                {
                                                                                                    hasLaterAttempt:
                                                                                                        eventIdx <
                                                                                                        attemptEvents.length -
                                                                                                            1,
                                                                                                    taskRunning:
                                                                                                        String(
                                                                                                            task.status,
                                                                                                        ).trim() ===
                                                                                                        "running",
                                                                                                },
                                                                                            )}
                                                                                        </div>
                                                                                    ),
                                                                                )}
                                                                            </div>
                                                                        )}
                                                                        {progressDisplay.progress !== null && (
                                                                            <div className="mt-1">
                                                                                <div
                                                                                    className={ui.progressTrack}
                                                                                >
                                                                                    <div
                                                                                        className={
                                                                                            ui.progressFill
                                                                                        }
                                                                                        style={{
                                                                                            width: `${progressDisplay.width}%`,
                                                                                        }}
                                                                                    />
                                                                                </div>
                                                                                <div
                                                                                    className={`mt-1 ${ui.jobsMeta}`}
                                                                                >
                                                                                    {
                                                                                        progressDisplay.label
                                                                                    }
                                                                                </div>
                                                                            </div>
                                                                        )}
                                                                    </li>
                                                                );
                                                            })}
                                                        </ul>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </li>
                            );
                        })}
                    </ul>
                )}
            </div>
        </aside>
    );
}
