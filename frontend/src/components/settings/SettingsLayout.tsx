// src/components/settings/SettingsLayout.tsx
import { useCallback, useEffect, useMemo, useState } from "react";

import { fetchBoxDetectionProfiles, restartBackend } from "../../api";
import { useAgentSettings } from "../../context/AgentSettingsContext";
import { useSettings } from "../../context/SettingsContext";
import type { BoxDetectionProfile } from "../../types";
import { Button } from "../../ui/primitives";
import { ui } from "../../ui/tokens";
import { normalizeBoxType } from "../../utils/boxes";
import { JobsPanel } from "../JobsPanel";
import { DetectionDefaultsCard } from "./sections/DetectionDefaultsCard";
import { OcrParallelismCard } from "./sections/OcrParallelismCard";
import { OcrProfilesCard } from "./sections/OcrProfilesCard";
import { TranslationAgentCard } from "./sections/TranslationAgentCard";
import { type AgentDraft, type OcrDraftProfile, toIntWithFallback } from "./types";

const SETTINGS_AUTOSAVE_KEY = "settings.autosave.enabled";

export function SettingsLayout() {
    const {
        settings,
        loading: baseLoading,
        error: baseError,
        save,
        refresh,
    } = useSettings();
    const {
        agent,
        ocrProfiles,
        loading: agentLoading,
        error: agentError,
        refresh: refreshAgent,
        saveAgent,
        saveOcrProfiles,
    } = useAgentSettings();

    const [draft, setDraft] = useState<Record<string, unknown>>({});
    const [agentDraft, setAgentDraft] = useState<AgentDraft | null>(null);
    const [ocrDraft, setOcrDraft] = useState<OcrDraftProfile[]>([]);
    const [baseDirty, setBaseDirty] = useState(false);
    const [agentDirty, setAgentDirty] = useState(false);
    const [ocrDirty, setOcrDirty] = useState(false);
    const [baseAutoSaving, setBaseAutoSaving] = useState(false);
    const [agentAutoSaving, setAgentAutoSaving] = useState(false);
    const [ocrAutoSaving, setOcrAutoSaving] = useState(false);
    const [saving, setSaving] = useState(false);
    const [restartingBackend, setRestartingBackend] = useState(false);
    const [saveMessage, setSaveMessage] = useState<string | null>(null);
    const [autoSaveEnabled, setAutoSaveEnabled] = useState<boolean>(() => {
        if (typeof window === "undefined") {
            return true;
        }
        const raw = window.localStorage.getItem(SETTINGS_AUTOSAVE_KEY);
        if (raw === null) {
            return true;
        }
        const normalized = raw.trim().toLowerCase();
        return normalized !== "0" && normalized !== "false";
    });
    const [agentDetectionProfiles, setAgentDetectionProfiles] = useState<
        BoxDetectionProfile[]
    >([]);
    const [agentDetectionLoading, setAgentDetectionLoading] = useState(false);

    useEffect(() => {
        if (settings?.values) {
            setDraft(settings.values);
            setBaseDirty(false);
        }
    }, [settings]);

    useEffect(() => {
        if (agent?.value) {
            const value = agent.value;
            setAgentDraft({
                model_id: value.model_id ?? "",
                max_output_tokens:
                    value.max_output_tokens === null ||
                    value.max_output_tokens === undefined
                        ? ""
                        : String(value.max_output_tokens),
                reasoning_effort: value.reasoning_effort ?? "low",
                temperature:
                    value.temperature === null || value.temperature === undefined
                        ? ""
                        : String(value.temperature),
            });
            setAgentDirty(false);
        }
    }, [agent]);

    useEffect(() => {
        if (ocrProfiles?.profiles) {
            setOcrDraft(ocrProfiles.profiles.map((profile) => ({ ...profile })));
            setOcrDirty(false);
        }
    }, [ocrProfiles]);

    const agentModelOptions = useMemo(() => {
        const models = agent?.options?.models;
        return Array.isArray(models) ? models.map(String) : [];
    }, [agent]);

    const agentReasoningOptions = useMemo(() => {
        const raw = agent?.options?.reasoning_effort;
        return Array.isArray(raw) ? raw.map(String) : ["low", "medium", "high"];
    }, [agent]);

    const ocrModelOptions = useMemo(() => {
        const raw = ocrProfiles?.options?.models;
        return Array.isArray(raw) ? raw.map(String) : [];
    }, [ocrProfiles]);

    const ocrReasoningOptions = useMemo(() => {
        const raw = ocrProfiles?.options?.reasoning_effort;
        return Array.isArray(raw) ? raw.map(String) : ["low", "medium", "high"];
    }, [ocrProfiles]);

    const confThreshold = useMemo(() => {
        const value = draft["detection.conf_threshold"];
        return value === null || value === undefined ? "" : String(value);
    }, [draft]);

    const iouThreshold = useMemo(() => {
        const value = draft["detection.iou_threshold"];
        return value === null || value === undefined ? "" : String(value);
    }, [draft]);

    const agentDetectionProfileId = useMemo(() => {
        const value = draft["agent.translate.detection_profile_id"];
        return value === null || value === undefined ? "" : String(value);
    }, [draft]);

    const containmentThreshold = useMemo(() => {
        const value = draft["detection.containment_threshold"];
        return value === null || value === undefined ? "" : String(value);
    }, [draft]);

    const translateSingleBoxUseContext = useMemo(() => {
        const value = draft["translation.single_box.use_context"];
        if (typeof value === "boolean") {
            return value;
        }
        return true;
    }, [draft]);

    const ocrParallelismLocal = useMemo(() => {
        const value = draft["ocr.parallelism.local"];
        return value === null || value === undefined ? "" : String(value);
    }, [draft]);

    const ocrParallelismRemote = useMemo(() => {
        const value = draft["ocr.parallelism.remote"];
        return value === null || value === undefined ? "" : String(value);
    }, [draft]);

    const ocrParallelismMaxWorkers = useMemo(() => {
        const value = draft["ocr.parallelism.max_workers"];
        return value === null || value === undefined ? "" : String(value);
    }, [draft]);

    const ocrParallelismLeaseSeconds = useMemo(() => {
        const value = draft["ocr.parallelism.lease_seconds"];
        return value === null || value === undefined ? "" : String(value);
    }, [draft]);

    const ocrParallelismTaskTimeoutSeconds = useMemo(() => {
        const value = draft["ocr.parallelism.task_timeout_seconds"];
        return value === null || value === undefined ? "" : String(value);
    }, [draft]);

    const ocrParallelDefaults = useMemo(
        () => ({
            local: toIntWithFallback(
                String(settings?.defaults?.["ocr.parallelism.local"] ?? "4"),
                4,
            ),
            remote: toIntWithFallback(
                String(settings?.defaults?.["ocr.parallelism.remote"] ?? "2"),
                2,
            ),
            maxWorkers: toIntWithFallback(
                String(settings?.defaults?.["ocr.parallelism.max_workers"] ?? "6"),
                6,
            ),
            leaseSeconds: toIntWithFallback(
                String(settings?.defaults?.["ocr.parallelism.lease_seconds"] ?? "180"),
                180,
            ),
            taskTimeoutSeconds: toIntWithFallback(
                String(
                    settings?.defaults?.["ocr.parallelism.task_timeout_seconds"] ??
                        "180",
                ),
                180,
            ),
        }),
        [settings],
    );

    const buildBaseSettingsPayload = useCallback(
        () => ({
            "detection.conf_threshold": confThreshold ? Number(confThreshold) : null,
            "detection.iou_threshold": iouThreshold ? Number(iouThreshold) : null,
            "detection.containment_threshold": containmentThreshold
                ? Number(containmentThreshold)
                : null,
            "agent.translate.detection_profile_id": agentDetectionProfileId,
            "translation.single_box.use_context": translateSingleBoxUseContext,
            "ocr.parallelism.local": toIntWithFallback(
                ocrParallelismLocal,
                ocrParallelDefaults.local,
            ),
            "ocr.parallelism.remote": toIntWithFallback(
                ocrParallelismRemote,
                ocrParallelDefaults.remote,
            ),
            "ocr.parallelism.max_workers": toIntWithFallback(
                ocrParallelismMaxWorkers,
                ocrParallelDefaults.maxWorkers,
            ),
            "ocr.parallelism.lease_seconds": toIntWithFallback(
                ocrParallelismLeaseSeconds,
                ocrParallelDefaults.leaseSeconds,
            ),
            "ocr.parallelism.task_timeout_seconds": toIntWithFallback(
                ocrParallelismTaskTimeoutSeconds,
                ocrParallelDefaults.taskTimeoutSeconds,
            ),
        }),
        [
            confThreshold,
            iouThreshold,
            containmentThreshold,
            agentDetectionProfileId,
            translateSingleBoxUseContext,
            ocrParallelismLocal,
            ocrParallelismRemote,
            ocrParallelismMaxWorkers,
            ocrParallelismLeaseSeconds,
            ocrParallelismTaskTimeoutSeconds,
            ocrParallelDefaults,
        ],
    );

    const agentDetectionOptions = useMemo(() => {
        const normalizedTask = normalizeBoxType("text");
        const enabledProfiles = agentDetectionProfiles.filter(
            (profile) => profile.enabled,
        );
        const availableProfiles = enabledProfiles.filter((profile) => {
            const tasks = profile.tasks ?? [];
            if (tasks.length > 0) {
                return tasks.some((task) => normalizeBoxType(task) === normalizedTask);
            }
            const classes = profile.classes ?? [];
            if (classes.length === 0) {
                return true;
            }
            return classes.some((name) => normalizeBoxType(name) === normalizedTask);
        });
        if (
            agentDetectionProfileId &&
            !availableProfiles.some(
                (profile) => profile.id === agentDetectionProfileId,
            )
        ) {
            return [
                {
                    id: agentDetectionProfileId,
                    label: `${agentDetectionProfileId} (missing)`,
                    enabled: false,
                },
                ...availableProfiles,
            ];
        }
        return availableProfiles;
    }, [agentDetectionProfiles, agentDetectionProfileId]);

    const hasAgentDetectionOptions = agentDetectionOptions.length > 0;

    const updateDraft = (key: string, value: unknown) => {
        setDraft((prev) => ({ ...prev, [key]: value }));
        setBaseDirty(true);
    };

    const updateAgentDraft = (key: keyof AgentDraft, value: string) => {
        setAgentDraft((prev) => {
            if (!prev) {
                return null;
            }
            return {
                ...prev,
                [key]: value,
            };
        });
        setAgentDirty(true);
    };

    const updateOcrProfile = (id: string, updates: Partial<OcrDraftProfile>) => {
        setOcrDraft((prev) =>
            prev.map((profile) =>
                profile.id === id ? { ...profile, ...updates } : profile,
            ),
        );
        setOcrDirty(true);
    };

    const buildOcrPayload = useCallback(
        () => ({
            profiles: ocrDraft.map((profile) => ({
                profile_id: profile.id,
                agent_enabled: profile.agent_enabled,
                model_id: profile.model_id ?? null,
                max_output_tokens:
                    profile.max_output_tokens === null ||
                    profile.max_output_tokens === undefined
                        ? null
                        : Number(profile.max_output_tokens),
                reasoning_effort: profile.reasoning_effort ?? null,
                temperature:
                    profile.temperature === null ||
                    profile.temperature === undefined
                        ? null
                        : Number(profile.temperature),
            })),
        }),
        [ocrDraft],
    );

    const refreshDetectionProfiles = useCallback(async () => {
        setAgentDetectionLoading(true);
        try {
            const profiles = await fetchBoxDetectionProfiles();
            setAgentDetectionProfiles(profiles);
        } catch (err) {
            console.error("Failed to load box detection profiles", err);
        } finally {
            setAgentDetectionLoading(false);
        }
    }, []);

    useEffect(() => {
        void refreshDetectionProfiles();
    }, [refreshDetectionProfiles]);

    useEffect(() => {
        if (typeof window === "undefined") {
            return;
        }
        window.localStorage.setItem(
            SETTINGS_AUTOSAVE_KEY,
            autoSaveEnabled ? "1" : "0",
        );
    }, [autoSaveEnabled]);

    useEffect(() => {
        if (!baseDirty) {
            return;
        }
        if (!autoSaveEnabled) {
            return;
        }
        if (baseLoading) {
            return;
        }
        const handle = setTimeout(() => {
            setBaseAutoSaving(true);
            save(buildBaseSettingsPayload())
                .then(() => {
                    setSaveMessage("Base settings saved.");
                    setBaseDirty(false);
                })
                .catch(() => {
                    setSaveMessage(null);
                })
                .finally(() => {
                    setBaseAutoSaving(false);
                });
        }, 400);
        return () => clearTimeout(handle);
    }, [
        baseDirty,
        autoSaveEnabled,
        baseLoading,
        save,
        buildBaseSettingsPayload,
    ]);

    useEffect(() => {
        if (!agentDirty || !agentDraft) {
            return;
        }
        if (!autoSaveEnabled) {
            return;
        }
        if (agentLoading) {
            return;
        }
        const handle = setTimeout(() => {
            setAgentAutoSaving(true);
            saveAgent({
                model_id: agentDraft.model_id,
                reasoning_effort: agentDraft.reasoning_effort,
                max_output_tokens: agentDraft.max_output_tokens
                    ? Number(agentDraft.max_output_tokens)
                    : null,
                temperature: agentDraft.temperature
                    ? Number(agentDraft.temperature)
                    : null,
            })
                .then(() => {
                    setSaveMessage("Translation agent settings saved.");
                    setAgentDirty(false);
                })
                .catch(() => {
                    setSaveMessage(null);
                })
                .finally(() => {
                    setAgentAutoSaving(false);
                });
        }, 400);
        return () => clearTimeout(handle);
    }, [agentDirty, agentDraft, autoSaveEnabled, agentLoading, saveAgent]);

    useEffect(() => {
        if (!ocrDirty || ocrDraft.length === 0) {
            return;
        }
        if (!autoSaveEnabled) {
            return;
        }
        if (agentLoading) {
            return;
        }
        const handle = setTimeout(() => {
            setOcrAutoSaving(true);
            saveOcrProfiles(buildOcrPayload())
                .then(() => {
                    setSaveMessage("OCR settings saved.");
                    setOcrDirty(false);
                })
                .catch(() => {
                    setSaveMessage(null);
                })
                .finally(() => {
                    setOcrAutoSaving(false);
                });
        }, 400);
        return () => clearTimeout(handle);
    }, [
        ocrDirty,
        ocrDraft.length,
        autoSaveEnabled,
        agentLoading,
        saveOcrProfiles,
        buildOcrPayload,
    ]);

    const handleSave = async () => {
        setSaving(true);
        setSaveMessage(null);
        try {
            await save(buildBaseSettingsPayload());

            if (agentDraft) {
                await saveAgent({
                    model_id: agentDraft.model_id,
                    reasoning_effort: agentDraft.reasoning_effort,
                    max_output_tokens: agentDraft.max_output_tokens
                        ? Number(agentDraft.max_output_tokens)
                        : null,
                    temperature: agentDraft.temperature
                        ? Number(agentDraft.temperature)
                        : null,
                });
            }

            if (ocrDraft.length) {
                await saveOcrProfiles(buildOcrPayload());
            }

            setSaveMessage("Saved.");
            setBaseDirty(false);
            setAgentDirty(false);
            setOcrDirty(false);
        } catch {
            setSaveMessage(null);
        } finally {
            setSaving(false);
        }
    };

    const handleRestartBackend = async () => {
        if (typeof window !== "undefined") {
            const confirmed = window.confirm(
                "Restart backend now? Active requests may be interrupted.",
            );
            if (!confirmed) {
                return;
            }
        }
        setRestartingBackend(true);
        setSaveMessage(null);
        try {
            await restartBackend();
            setSaveMessage("Backend restart requested.");
        } catch (err) {
            console.error("Failed to request backend restart", err);
            const message =
                err instanceof Error && err.message
                    ? err.message
                    : "Failed to request backend restart.";
            setSaveMessage(message);
        } finally {
            setTimeout(() => {
                setRestartingBackend(false);
            }, 1000);
        }
    };

    const loading = baseLoading || agentLoading;
    const error = baseError || agentError;

    return (
        <div className="flex-1 flex overflow-hidden">
            <JobsPanel />
            <main className={ui.trainingMain}>
                <section className={ui.trainingSection}>
                    <div className={ui.trainingSectionHeader}>
                        <div>
                            <div className={ui.trainingSectionTitle}>Settings</div>
                            <div className={ui.trainingSectionMeta}>
                                Persisted in the database
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            <label className="inline-flex items-center gap-2 rounded-md border border-slate-700 px-2 py-1 text-[11px] text-slate-300">
                                <input
                                    type="checkbox"
                                    checked={autoSaveEnabled}
                                    onChange={(e) => setAutoSaveEnabled(e.target.checked)}
                                />
                                Auto-save
                            </label>
                            <Button
                                type="button"
                                variant="ghostSmall"
                                onClick={() => {
                                    void refresh();
                                    void refreshAgent();
                                    void refreshDetectionProfiles();
                                }}
                                disabled={loading}
                            >
                                Refresh
                            </Button>
                            <Button
                                type="button"
                                variant="ghostSmall"
                                onClick={handleRestartBackend}
                                disabled={loading || restartingBackend}
                            >
                                {restartingBackend ? "Restarting..." : "Restart backend"}
                            </Button>
                            <Button
                                type="button"
                                variant="actionEmerald"
                                onClick={handleSave}
                                disabled={loading || saving}
                            >
                                {saving ? "Saving..." : "Save changes"}
                            </Button>
                        </div>
                    </div>

                    {error && <div className={ui.trainingError}>{error}</div>}
                    {saveMessage && (
                        <div className={ui.trainingMetaSmall}>{saveMessage}</div>
                    )}
                    {!autoSaveEnabled && (
                        <div className={ui.trainingMetaSmall}>
                            Auto-save disabled. Use “Save changes” to persist edits.
                        </div>
                    )}
                    {baseAutoSaving && (
                        <div className={ui.trainingMetaSmall}>
                            Saving base settings…
                        </div>
                    )}
                    {agentAutoSaving && (
                        <div className={ui.trainingMetaSmall}>
                            Saving translation agent settings…
                        </div>
                    )}
                    {ocrAutoSaving && (
                        <div className={ui.trainingMetaSmall}>Saving OCR settings…</div>
                    )}

                    <div className="grid gap-4 lg:grid-cols-2 lg:items-start">
                        <div className="space-y-4">
                            <TranslationAgentCard
                                agentDraft={agentDraft}
                                agentModelOptions={agentModelOptions}
                                agentReasoningOptions={agentReasoningOptions}
                                onUpdateAgentDraft={updateAgentDraft}
                                agentDetectionProfileId={agentDetectionProfileId}
                                translateSingleBoxUseContext={translateSingleBoxUseContext}
                                onUpdateDraft={updateDraft}
                                agentDetectionLoading={agentDetectionLoading}
                                agentDetectionOptions={agentDetectionOptions}
                                hasAgentDetectionOptions={hasAgentDetectionOptions}
                            />

                            <DetectionDefaultsCard
                                confThreshold={confThreshold}
                                iouThreshold={iouThreshold}
                                containmentThreshold={containmentThreshold}
                                onUpdateDraft={updateDraft}
                            />
                        </div>

                        <div className="space-y-4">
                            <OcrProfilesCard
                                ocrDraft={ocrDraft}
                                ocrModelOptions={ocrModelOptions}
                                ocrReasoningOptions={ocrReasoningOptions}
                                onUpdateOcrProfile={updateOcrProfile}
                            />

                            <OcrParallelismCard
                                ocrParallelismLocal={ocrParallelismLocal}
                                ocrParallelismRemote={ocrParallelismRemote}
                                ocrParallelismMaxWorkers={ocrParallelismMaxWorkers}
                                ocrParallelismLeaseSeconds={ocrParallelismLeaseSeconds}
                                ocrParallelismTaskTimeoutSeconds={ocrParallelismTaskTimeoutSeconds}
                                onUpdateDraft={updateDraft}
                            />
                        </div>
                    </div>
                </section>
            </main>
        </div>
    );
}
