// src/components/JobsPanel.tsx
import { useJobs } from "../context/useJobs";
import { getProgressDisplay } from "../utils/progress";
import { ui } from "../ui/tokens";

export function JobsPanel() {
    const { jobs, jobsError, jobsLoading, clearFinished, cancelJob, deleteJob } =
        useJobs();

    return (
        <aside className={ui.jobsPanel}>
            <div className="flex-1 p-4 overflow-y-auto">
                <div className={ui.jobsHeader}>
                    <h2 className={ui.jobsTitle}>
                        Jobs
                    </h2>
                    <div className="flex items-center gap-2">
                        {jobsLoading && (
                            <span className={ui.mutedTextMicro}>
                                Loading...
                            </span>
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

                {jobsError && (
                    <div className={`mb-2 ${ui.errorTextXs}`}>
                        {jobsError}
                    </div>
                )}

                {jobs.length === 0 && !jobsError && (
                    <div className={ui.mutedTextXs}>No jobs yet.</div>
                )}

                {jobs.length > 0 && (
                    <ul className={ui.jobsList}>
                        {jobs
                            .slice()
                            .sort((a, b) => b.created_at - a.created_at)
                            .map((job) => {
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
                                const progressDisplay = getProgressDisplay(
                                    job.progress,
                                );
                                const detailParts: string[] = [];

                                if (
                                    job.type === "prepare_dataset" &&
                                    payload?.dataset_id
                                ) {
                                    detailParts.push(
                                        `dataset ${String(payload.dataset_id)}`,
                                    );
                                } else if (
                                    job.type === "train_model" &&
                                    payload?.dataset_id
                                ) {
                                    detailParts.push(
                                        `dataset ${String(payload.dataset_id)}`,
                                    );
                                } else if (
                                    (job.type === "ocr_box" ||
                                        job.type === "translate_box") &&
                                    (Number.isFinite(Number(payload?.boxOrder)) ||
                                        Number.isFinite(Number(payload?.boxId)))
                                ) {
                                    const orderValue = Number.isFinite(
                                        Number(payload?.boxOrder),
                                    )
                                        ? Number(payload?.boxOrder)
                                        : Number(payload?.boxId);
                                    detailParts.push(
                                        `box #${orderValue}`,
                                    );
                                } else if (job.type === "box_detection" && payload?.task) {
                                    detailParts.push(String(payload.task));
                                }

                                if (payload?.filename) {
                                    detailParts.push(String(payload.filename));
                                }

                                const detail = detailParts.join(" | ");
                                const modelId =
                                    payload?.modelId ??
                                    (payload as { model_id?: string })?.model_id;
                                const reasoningEffort =
                                    payload?.reasoningEffort ??
                                    (payload as { reasoning_effort?: string })
                                        ?.reasoning_effort;
                                const maxOutputTokensRaw =
                                    payload?.maxOutputTokens ??
                                    (payload as { max_output_tokens?: number })
                                        ?.max_output_tokens;
                                const maxOutputTokens = Number.isFinite(
                                    Number(maxOutputTokensRaw),
                                )
                                    ? Number(maxOutputTokensRaw)
                                    : null;
                                const modelMetaParts: string[] = [];
                                if (modelId) {
                                    modelMetaParts.push(`Model: ${String(modelId)}`);
                                }
                                if (reasoningEffort) {
                                    modelMetaParts.push(
                                        `Reasoning: ${String(reasoningEffort)}`,
                                    );
                                }
                                if (maxOutputTokens !== null) {
                                    modelMetaParts.push(`Max: ${maxOutputTokens}`);
                                }
                                const modelMeta =
                                    modelMetaParts.length > 0
                                        ? modelMetaParts.join(" | ")
                                        : "";
                                const canDelete =
                                    job.status === "finished" ||
                                    job.status === "failed" ||
                                    job.status === "canceled";

                                return (
                                    <li
                                        key={job.id}
                                        className={ui.jobsCard}
                                    >
                                        <div className="flex justify-between items-center mb-0.5 gap-2">
                                            <span className={ui.jobsType}>
                                                {job.type}
                                            </span>
                                            <div className="flex items-center gap-1">
                                                {job.status === "running" && (
                                                    <button
                                                        type="button"
                                                        onClick={() =>
                                                            cancelJob(job.id)
                                                        }
                                                        className={ui.button.jobsStop}
                                                    >
                                                        Stop
                                                    </button>
                                                )}
                                                {canDelete && (
                                                    <button
                                                        type="button"
                                                        onClick={() =>
                                                            deleteJob(job.id)
                                                        }
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
                                                        (job.status ===
                                                        "finished"
                                                            ? ui.statusBadgeFinished
                                                            : job.status ===
                                                              "failed"
                                                            ? ui.statusBadgeFailed
                                                            : job.status ===
                                                              "canceled"
                                                            ? ui.statusBadgeCanceled
                                                            : ui.statusBadgeRunning)
                                                    }
                                                >
                                                    {job.status}
                                                </span>
                                            </div>
                                        </div>
                                        {detail && (
                                            <div className={ui.jobsDetail}>
                                                {detail}
                                            </div>
                                        )}
                                        {modelMeta &&
                                            (job.type === "ocr_box" ||
                                                job.type === "translate_box") && (
                                                <div className={`mt-1 ${ui.jobsMeta}`}>
                                                    {modelMeta}
                                                </div>
                                            )}
                                        {job.type === "train_model" &&
                                            job.metrics?.device && (
                                                <div className={`mt-1 ${ui.jobsMeta}`}>
                                                    Device:{" "}
                                                    {String(job.metrics.device)}
                                                </div>
                                            )}
                                        {job.message && (
                                            <div className={ui.jobsMessage}>
                                                {job.message}
                                            </div>
                                        )}
                                        {job.warnings && job.warnings.length > 0 && (
                                            <div className={`mt-1 ${ui.warningTextTiny}`}>
                                                {job.warnings.join(" | ")}
                                            </div>
                                        )}
                                        {progressDisplay.progress !== null && (
                                            <div className="mt-1">
                                                <div className={ui.progressTrack}>
                                                    <div
                                                        className={ui.progressFill}
                                                        style={{
                                                            width: `${progressDisplay.width}%`,
                                                        }}
                                                    />
                                                </div>
                                                <div className={`mt-1 ${ui.jobsMeta}`}>
                                                    {progressDisplay.label}
                                                </div>
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
