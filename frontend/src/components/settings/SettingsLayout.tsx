// src/components/settings/SettingsLayout.tsx
import { useCallback, useEffect, useMemo, useState } from "react";
import { JobsPanel } from "../JobsPanel";
import { useSettings } from "../../context/SettingsContext";
import { useAgentSettings } from "../../context/AgentSettingsContext";
import { fetchBoxDetectionProfiles } from "../../api";
import type { BoxDetectionProfile } from "../../types";
import { normalizeBoxType } from "../../utils/boxes";
import { Button, Field, Select } from "../../ui/primitives";
import { ui } from "../../ui/tokens";

type AgentDraft = {
    model_id: string;
    max_output_tokens: string;
    reasoning_effort: string;
    temperature: string;
};

type OcrDraftProfile = {
    id: string;
    label: string;
    description?: string | null;
    kind: string;
    enabled: boolean;
    agent_enabled: boolean;
    model_id?: string | null;
    max_output_tokens?: number | null;
    reasoning_effort?: string | null;
    temperature?: number | null;
};

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
    const [saveMessage, setSaveMessage] = useState<string | null>(null);
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

    const agentDetectionOptions = useMemo(() => {
        const normalizedTask = normalizeBoxType("text");
        const enabledProfiles = agentDetectionProfiles.filter(
            (profile) => profile.enabled,
        );
        const availableProfiles = enabledProfiles.filter((profile) => {
            const tasks = profile.tasks ?? [];
            if (tasks.length > 0) {
                return tasks.some(
                    (task) => normalizeBoxType(task) === normalizedTask,
                );
            }
            const classes = profile.classes ?? [];
            if (classes.length === 0) {
                return true;
            }
            return classes.some(
                (name) => normalizeBoxType(name) === normalizedTask,
            );
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

    const updateOcrProfile = (
        id: string,
        updates: Partial<OcrDraftProfile>,
    ) => {
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
        if (!baseDirty) {
            return;
        }
        if (baseLoading) {
            return;
        }
        const handle = setTimeout(() => {
            setBaseAutoSaving(true);
            save({
                "detection.conf_threshold": confThreshold
                    ? Number(confThreshold)
                    : null,
                "detection.iou_threshold": iouThreshold ? Number(iouThreshold) : null,
                "agent.translate.detection_profile_id": agentDetectionProfileId,
            })
                .then(() => {
                    setSaveMessage("Detection settings saved.");
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
    }, [baseDirty, baseLoading, save, confThreshold, iouThreshold, agentDetectionProfileId]);

    useEffect(() => {
        if (!agentDirty || !agentDraft) {
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
    }, [agentDirty, agentDraft, agentLoading, saveAgent]);

    useEffect(() => {
        if (!ocrDirty || ocrDraft.length === 0) {
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
    }, [ocrDirty, ocrDraft.length, agentLoading, saveOcrProfiles, buildOcrPayload]);

    const handleSave = async () => {
        setSaving(true);
        setSaveMessage(null);
        try {
            await save({
                "detection.conf_threshold": confThreshold
                    ? Number(confThreshold)
                    : null,
                "detection.iou_threshold": iouThreshold ? Number(iouThreshold) : null,
                "agent.translate.detection_profile_id": agentDetectionProfileId,
            });

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

    const loading = baseLoading || agentLoading;
    const error = baseError || agentError;

    return (
        <div className="flex-1 flex overflow-hidden">
            <JobsPanel />
            <main className={ui.trainingMain}>
                <section className={ui.trainingSection}>
                    <div className={ui.trainingSectionHeader}>
                        <div>
                            <div className={ui.trainingSectionTitle}>
                                Settings
                            </div>
                            <div className={ui.trainingSectionMeta}>
                                Persisted in the database
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
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
                    {baseAutoSaving && (
                        <div className={ui.trainingMetaSmall}>
                            Saving detection settings…
                        </div>
                    )}
                    {agentAutoSaving && (
                        <div className={ui.trainingMetaSmall}>
                            Saving translation agent settings…
                        </div>
                    )}
                    {ocrAutoSaving && (
                        <div className={ui.trainingMetaSmall}>
                            Saving OCR settings…
                        </div>
                    )}

                    <div className="grid gap-4 lg:grid-cols-2">
                        <div className={ui.trainingCard}>
                            <div className={ui.trainingSubTitle}>
                                Translation Agent
                            </div>
                            <div className="mt-3 space-y-3">
                                <Field
                                    label="Model"
                                    layout="row"
                                    labelClassName={ui.label}
                                >
                                    <Select
                                        value={agentDraft?.model_id ?? ""}
                                        onChange={(e) =>
                                            updateAgentDraft(
                                                "model_id",
                                                e.target.value,
                                            )
                                        }
                                    >
                                        {agentModelOptions.map((model) => (
                                            <option key={model} value={model}>
                                                {model}
                                            </option>
                                        ))}
                                    </Select>
                                </Field>

                                <Field
                                    label="Detection"
                                    layout="row"
                                    labelClassName={ui.label}
                                >
                                    <Select
                                        value={agentDetectionProfileId}
                                        onChange={(e) =>
                                            updateDraft(
                                                "agent.translate.detection_profile_id",
                                                e.target.value,
                                            )
                                        }
                                        disabled={agentDetectionLoading}
                                    >
                                        <option value="">
                                            Use sidebar selection
                                        </option>
                                        {agentDetectionOptions.map((profile) => (
                                            <option key={profile.id} value={profile.id}>
                                                {profile.label}
                                            </option>
                                        ))}
                                    </Select>
                                </Field>
                                {!agentDetectionLoading &&
                                    !hasAgentDetectionOptions && (
                                        <div className={ui.trainingHelp}>
                                            No text detection models available. Train a model to enable agent detection.
                                        </div>
                                    )}

                                <Field
                                    label="Reasoning"
                                    layout="row"
                                    labelClassName={ui.label}
                                >
                                    <Select
                                        value={agentDraft?.reasoning_effort ?? "low"}
                                        onChange={(e) =>
                                            updateAgentDraft(
                                                "reasoning_effort",
                                                e.target.value,
                                            )
                                        }
                                    >
                                        {agentReasoningOptions.map((option) => (
                                            <option key={option} value={option}>
                                                {option}
                                            </option>
                                        ))}
                                    </Select>
                                </Field>

                                <Field
                                    label="Max output"
                                    layout="row"
                                    labelClassName={ui.label}
                                >
                                    <input
                                        className={ui.trainingInput}
                                        type="number"
                                        min={128}
                                        value={agentDraft?.max_output_tokens ?? ""}
                                        onChange={(e) =>
                                            updateAgentDraft(
                                                "max_output_tokens",
                                                e.target.value,
                                            )
                                        }
                                    />
                                </Field>

                                <Field
                                    label="Temperature"
                                    layout="row"
                                    labelClassName={ui.label}
                                >
                                    <input
                                        className={ui.trainingInput}
                                        type="number"
                                        step="0.1"
                                        min={0}
                                        max={2}
                                        value={agentDraft?.temperature ?? ""}
                                        onChange={(e) =>
                                            updateAgentDraft(
                                                "temperature",
                                                e.target.value,
                                            )
                                        }
                                    />
                                </Field>
                                <div className={ui.trainingHelp}>
                                    Temperature is ignored by GPT-5 models.
                                </div>
                            </div>
                        </div>

                        <div className={ui.trainingCard}>
                            <div className={ui.trainingSubTitle}>LLM OCR</div>
                            <div className="mt-3 space-y-2">
                                {ocrDraft.map((profile) => {
                                    const isLocal = profile.kind === "local";
                                    const options = new Set(ocrModelOptions);
                                    if (profile.model_id) {
                                        options.add(profile.model_id);
                                    }
                                    return (
                                        <div
                                            key={profile.id}
                                            className="flex flex-col gap-2 rounded-md border border-slate-800 bg-slate-950/60 p-2"
                                        >
                                            <label
                                                className={`flex items-center gap-2 text-xs ${
                                                    profile.enabled
                                                        ? "text-slate-200"
                                                        : "text-slate-500"
                                                }`}
                                            >
                                                <input
                                                    type="checkbox"
                                                    checked={profile.agent_enabled}
                                                    disabled={!profile.enabled}
                                                    onChange={(e) =>
                                                        updateOcrProfile(profile.id, {
                                                            agent_enabled:
                                                                e.target.checked,
                                                        })
                                                    }
                                                />
                                                {profile.label}
                                            </label>

                                            {isLocal ? (
                                                <div className={ui.trainingLabelTiny}>
                                                    Local OCR
                                                </div>
                                            ) : (
                                                <div className="grid gap-2 md:grid-cols-2">
                                                    <Field
                                                        label="Model"
                                                        layout="stack"
                                                        labelClassName={
                                                            ui.trainingLabelTiny
                                                        }
                                                    >
                                                        <Select
                                                            variant="training"
                                                            value={
                                                                profile.model_id ??
                                                                ""
                                                            }
                                                            onChange={(e) =>
                                                                updateOcrProfile(
                                                                    profile.id,
                                                                    {
                                                                        model_id:
                                                                            e.target
                                                                                .value ||
                                                                            null,
                                                                    },
                                                                )
                                                            }
                                                        >
                                                            {Array.from(options).map(
                                                                (model) => (
                                                                    <option
                                                                        key={model}
                                                                        value={model}
                                                                    >
                                                                        {model}
                                                                    </option>
                                                                ),
                                                            )}
                                                        </Select>
                                                    </Field>

                                                    <Field
                                                        label="Max output"
                                                        layout="stack"
                                                        labelClassName={
                                                            ui.trainingLabelTiny
                                                        }
                                                    >
                                                        <input
                                                            className={ui.trainingInput}
                                                            type="number"
                                                            min={1}
                                                            value={
                                                                profile.max_output_tokens ??
                                                                ""
                                                            }
                                                            onChange={(e) =>
                                                                updateOcrProfile(
                                                                    profile.id,
                                                                    {
                                                                        max_output_tokens:
                                                                            e.target
                                                                                .value ===
                                                                            ""
                                                                                ? null
                                                                                : Number(
                                                                                      e
                                                                                          .target
                                                                                          .value,
                                                                                  ),
                                                                    },
                                                                )
                                                            }
                                                        />
                                                    </Field>

                                                    <Field
                                                        label="Reasoning"
                                                        layout="stack"
                                                        labelClassName={
                                                            ui.trainingLabelTiny
                                                        }
                                                    >
                                                        <Select
                                                            variant="training"
                                                            value={
                                                                profile.reasoning_effort ??
                                                                ""
                                                            }
                                                            onChange={(e) =>
                                                                updateOcrProfile(
                                                                    profile.id,
                                                                    {
                                                                        reasoning_effort:
                                                                            e.target
                                                                                .value ||
                                                                            null,
                                                                    },
                                                                )
                                                            }
                                                        >
                                                            <option value="">
                                                                default
                                                            </option>
                                                            {ocrReasoningOptions.map(
                                                                (option) => (
                                                                    <option
                                                                        key={option}
                                                                        value={option}
                                                                    >
                                                                        {option}
                                                                    </option>
                                                                ),
                                                            )}
                                                        </Select>
                                                    </Field>

                                                    <Field
                                                        label="Temperature"
                                                        layout="stack"
                                                        labelClassName={
                                                            ui.trainingLabelTiny
                                                        }
                                                    >
                                                        <input
                                                            className={ui.trainingInput}
                                                            type="number"
                                                            step="0.1"
                                                            min={0}
                                                            max={2}
                                                            value={
                                                                profile.temperature ??
                                                                ""
                                                            }
                                                            onChange={(e) =>
                                                                updateOcrProfile(
                                                                    profile.id,
                                                                    {
                                                                        temperature:
                                                                            e.target
                                                                                .value ===
                                                                            ""
                                                                                ? null
                                                                                : Number(
                                                                                      e
                                                                                          .target
                                                                                          .value,
                                                                                  ),
                                                                    },
                                                                )
                                                            }
                                                        />
                                                    </Field>
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                            <div className={ui.trainingHelp}>
                                Toggle which OCR profiles the agent may use.
                            </div>
                        </div>

                        <div className={ui.trainingCard}>
                            <div className={ui.trainingSubTitle}>
                                Detection Defaults (YOLO)
                            </div>
                            <div className="mt-3 space-y-3">
                                <Field
                                    label="Conf threshold"
                                    layout="row"
                                    labelClassName={ui.label}
                                >
                                    <input
                                        className={ui.trainingInput}
                                        type="number"
                                        step="0.01"
                                        min={0}
                                        max={1}
                                        value={confThreshold}
                                        onChange={(e) =>
                                            updateDraft(
                                                "detection.conf_threshold",
                                                e.target.value,
                                            )
                                        }
                                    />
                                </Field>

                                <Field
                                    label="IOU threshold"
                                    layout="row"
                                    labelClassName={ui.label}
                                >
                                    <input
                                        className={ui.trainingInput}
                                        type="number"
                                        step="0.01"
                                        min={0}
                                        max={1}
                                        value={iouThreshold}
                                        onChange={(e) =>
                                            updateDraft(
                                                "detection.iou_threshold",
                                                e.target.value,
                                            )
                                        }
                                    />
                                </Field>
                                <div className={ui.trainingHelp}>
                                    Leave blank to use Ultralytics defaults
                                    (conf 0.25, IoU 0.45).
                                </div>
                            </div>
                        </div>
                    </div>
                </section>
            </main>
        </div>
    );
}
