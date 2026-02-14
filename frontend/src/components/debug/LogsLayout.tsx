// src/components/logs/LogsLayout.tsx
import { useEffect, useMemo, useState } from "react";
import {
    clearAgentTranslateLogs,
    deleteAgentTranslateLog,
    fetchAgentTranslateLog,
    fetchAgentTranslateLogs,
    type LogFileContent,
    type LogFileInfo,
} from "../../api";
import { JobsPanel } from "../JobsPanel";
import { Button } from "../../ui/primitives";
import { ui } from "../../ui/tokens";

function formatTimestamp(value: number): string {
    if (!value) return "-";
    const date = new Date(value * 1000);
    return date.toLocaleString();
}

function formatPrettyJson(text: string): string {
    const trimmed = text.trim();
    if (!trimmed) return "";
    try {
        const parsed = JSON.parse(trimmed);
        return JSON.stringify(parsed, null, 2);
    } catch {
        return text;
    }
}

export function LogsLayout() {
    const [logs, setLogs] = useState<LogFileInfo[]>([]);
    const [selected, setSelected] = useState<string | null>(null);
    const [content, setContent] = useState<LogFileContent | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [detailError, setDetailError] = useState<string | null>(null);
    const [deleting, setDeleting] = useState(false);
    const [showRaw, setShowRaw] = useState(false);
    const [copyMessage, setCopyMessage] = useState<string | null>(null);

    const refresh = async () => {
        setLoading(true);
        setError(null);
        try {
            const files = await fetchAgentTranslateLogs();
            setLogs(files);
            if (files.length === 0) {
                setSelected(null);
                setContent(null);
            } else if (!selected) {
                setSelected(files[0].name);
            } else if (!files.some((file) => file.name === selected)) {
                setSelected(files[0].name);
            }
        } catch (err) {
            console.error("Failed to load logs", err);
            setError("Failed to load logs.");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        void refresh();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
        if (!selected) {
            setContent(null);
            return;
        }
        setShowRaw(false);
        let cancelled = false;
        const load = async () => {
            setDetailError(null);
            try {
                const data = await fetchAgentTranslateLog(selected);
                if (cancelled) return;
                setContent(data);
            } catch (err) {
                console.error("Failed to load log detail", err);
                if (cancelled) return;
                setDetailError("Failed to load log.");
            }
        };
        void load();
        return () => {
            cancelled = true;
        };
    }, [selected]);

    const formattedContent = useMemo(() => {
        if (!content) return "";
        if (content.is_json && content.content) {
            return JSON.stringify(content.content, null, 2);
        }
        return content.raw ?? "";
    }, [content]);

    const parsed = useMemo(() => {
        if (!content || !content.is_json) return null;
        if (!content.content || typeof content.content !== "object") return null;
        return content.content as Record<string, unknown>;
    }, [content]);

    const systemPrompt = useMemo(() => {
        const value = parsed?.system_prompt;
        return typeof value === "string" ? value : "";
    }, [parsed]);

    const userPrompt = useMemo(() => {
        const value = parsed?.user_prompt;
        return typeof value === "string" ? formatPrettyJson(value) : "";
    }, [parsed]);

    const responseText = useMemo(() => {
        const value = parsed?.raw_output_text;
        return typeof value === "string" ? formatPrettyJson(value) : "";
    }, [parsed]);

    const handleCopy = async (label: string, text: string) => {
        if (!text) return;
        try {
            if (navigator.clipboard?.writeText) {
                await navigator.clipboard.writeText(text);
            } else {
                const textarea = document.createElement("textarea");
                textarea.value = text;
                textarea.style.position = "fixed";
                textarea.style.left = "-9999px";
                document.body.appendChild(textarea);
                textarea.focus();
                textarea.select();
                document.execCommand("copy");
                document.body.removeChild(textarea);
            }
            setCopyMessage(`${label} copied.`);
            setTimeout(() => setCopyMessage(null), 1500);
        } catch {
            setCopyMessage(null);
        }
    };

    const handleDelete = async () => {
        if (!selected) return;
        setDeleting(true);
        try {
            await deleteAgentTranslateLog(selected);
            await refresh();
        } catch (err) {
            console.error("Failed to delete log", err);
            setError("Failed to delete log.");
        } finally {
            setDeleting(false);
        }
    };

    const handleDeleteAll = async () => {
        setDeleting(true);
        try {
            await clearAgentTranslateLogs();
            await refresh();
        } catch (err) {
            console.error("Failed to delete logs", err);
            setError("Failed to delete logs.");
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
                            <div className={ui.trainingSectionTitle}>
                                Agent Debug Logs
                            </div>
                            <div className={ui.trainingSectionMeta}>
                                Translate-page snapshots
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
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

                    <div className="mt-4 grid gap-4 lg:grid-cols-[280px_1fr]">
                        <div className={ui.trainingCard}>
                            <div className={ui.trainingSubTitle}>Files</div>
                            <div className="mt-3 space-y-2">
                                {logs.length === 0 && (
                                    <div className={ui.trainingHelp}>
                                        No logs yet.
                                    </div>
                                )}
                                {logs.map((log) => {
                                    const active = selected === log.name;
                                    const label = log.name.split("_")[0];
                                    return (
                                        <button
                                            key={log.name}
                                            type="button"
                                            className={`w-full text-left rounded-md border px-2 py-1.5 text-xs ${
                                                active
                                                    ? "border-emerald-400 bg-emerald-500/10 text-emerald-100"
                                                    : "border-slate-800 bg-slate-950/60 text-slate-300 hover:border-slate-600"
                                            }`}
                                            onClick={() => setSelected(log.name)}
                                        >
                                            <div className="truncate font-medium">
                                                {label}
                                            </div>
                                            <div className={ui.trainingMetaSmall}>
                                                {formatTimestamp(log.updated_at)} ·{" "}
                                                {(log.size / 1024).toFixed(1)} KB
                                            </div>
                                        </button>
                                    );
                                })}
                            </div>
                        </div>

                        <div className={ui.trainingCard}>
                        <div className={ui.trainingSectionHeader}>
                            <div>
                                <div className={ui.trainingSectionTitle}>
                                    Detail
                                </div>
                                    <div className={ui.trainingSectionMeta}>
                                        {content
                                            ? `${content.name} · ${formatTimestamp(
                                                  content.updated_at,
                                              )}`
                                            : "Select a log"}
                                    </div>
                                </div>
                                <div className="flex items-center gap-2">
                                    {content && (
                                        <>
                                            <Button
                                                type="button"
                                                variant="ghostSmall"
                                                onClick={() => setShowRaw(false)}
                                                disabled={!showRaw}
                                            >
                                                Prompt view
                                            </Button>
                                            <Button
                                                type="button"
                                                variant="ghostSmall"
                                                onClick={() => setShowRaw(true)}
                                                disabled={showRaw}
                                            >
                                                Raw JSON
                                            </Button>
                                        </>
                                    )}
                                    <Button
                                        type="button"
                                        variant="actionDangerSmall"
                                        onClick={handleDelete}
                                        disabled={!selected || deleting}
                                    >
                                        Delete
                                    </Button>
                                </div>
                            </div>

                            {detailError && (
                                <div className={ui.trainingError}>
                                    {detailError}
                                </div>
                            )}

                            {copyMessage && (
                                <div className={ui.trainingMetaSmall}>
                                    {copyMessage}
                                </div>
                            )}

                            {!content && !detailError && (
                                <div className={ui.trainingHelp}>
                                    Pick a log file to view its contents.
                                </div>
                            )}

                            {content && (
                                <div className="mt-2 space-y-3">
                                    <div className={ui.trainingSubTitle}>
                                        Prompt + Response
                                    </div>

                                    {!showRaw && (
                                        <div className="space-y-3">
                                            <div>
                                                <div className="flex items-center justify-between">
                                                    <div className={ui.trainingLabelSmall}>
                                                    System prompt
                                                    </div>
                                                    <Button
                                                        type="button"
                                                        variant="ghostSmall"
                                                        onClick={() =>
                                                            void handleCopy(
                                                                "System prompt",
                                                                systemPrompt,
                                                            )
                                                        }
                                                        disabled={!systemPrompt}
                                                    >
                                                        Copy
                                                    </Button>
                                                </div>
                                                <pre
                                                    className={`${ui.trainingLogBox} mt-2 p-3 whitespace-pre-wrap break-words`}
                                                >
                                                    {systemPrompt || "-"}
                                                </pre>
                                            </div>
                                            <div>
                                                <div className="flex items-center justify-between">
                                                    <div className={ui.trainingLabelSmall}>
                                                    User prompt
                                                    </div>
                                                    <Button
                                                        type="button"
                                                        variant="ghostSmall"
                                                        onClick={() =>
                                                            void handleCopy(
                                                                "User prompt",
                                                                userPrompt,
                                                            )
                                                        }
                                                        disabled={!userPrompt}
                                                    >
                                                        Copy
                                                    </Button>
                                                </div>
                                                <pre
                                                    className={`${ui.trainingLogBox} mt-2 p-3 whitespace-pre-wrap break-words`}
                                                >
                                                    {userPrompt || "-"}
                                                </pre>
                                            </div>
                                            <div>
                                                <div className="flex items-center justify-between">
                                                    <div className={ui.trainingLabelSmall}>
                                                    Response
                                                    </div>
                                                    <Button
                                                        type="button"
                                                        variant="ghostSmall"
                                                        onClick={() =>
                                                            void handleCopy(
                                                                "Response",
                                                                responseText,
                                                            )
                                                        }
                                                        disabled={!responseText}
                                                    >
                                                        Copy
                                                    </Button>
                                                </div>
                                                <pre
                                                    className={`${ui.trainingLogBox} mt-2 p-3 whitespace-pre-wrap break-words`}
                                                >
                                                    {responseText || "-"}
                                                </pre>
                                            </div>
                                        </div>
                                    )}

                                    {showRaw && (
                                        <div className="space-y-2">
                                            <div className="flex items-center justify-end">
                                                <Button
                                                    type="button"
                                                    variant="ghostSmall"
                                                    onClick={() =>
                                                        void handleCopy(
                                                            "Raw JSON",
                                                            formattedContent,
                                                        )
                                                    }
                                                    disabled={!formattedContent}
                                                >
                                                    Copy raw
                                                </Button>
                                            </div>
                                            <pre
                                                className={`${ui.trainingLogBox} p-3 whitespace-pre-wrap break-words`}
                                            >
                                                {formattedContent}
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
