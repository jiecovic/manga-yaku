import { useCallback, useEffect, useMemo, useState } from "react";

import { fetchBoxDetectionProfiles, restartBackend } from "../../api";
import { useAgentSettings } from "../../context/AgentSettingsContext";
import { useSettings } from "../../context/SettingsContext";
import type { BoxDetectionProfile } from "../../types";
import { normalizeBoxType } from "../../utils/boxes";
import type { SettingsTab } from "./SettingsTabs";
import { draftBoolean, draftString } from "./draftUtils";
import {
    type AgentDraft,
    type OcrDraftProfile,
    type TranslationDraftProfile,
    toIntWithFallback,
} from "./types";

const SETTINGS_AUTOSAVE_KEY = "settings.autosave.enabled";

export function useSettingsLayoutState() {
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
        translationProfiles,
        loading: agentLoading,
        error: agentError,
        refresh: refreshAgent,
        saveAgent,
        saveOcrProfiles,
        saveTranslationProfiles,
    } = useAgentSettings();

    const [draft, setDraft] = useState<Record<string, unknown>>({});
    const [agentDraft, setAgentDraft] = useState<AgentDraft | null>(null);
    const [ocrDraft, setOcrDraft] = useState<OcrDraftProfile[]>([]);
    const [translationDraft, setTranslationDraft] = useState<TranslationDraftProfile[]>(
        [],
    );
    const [baseDirty, setBaseDirty] = useState(false);
    const [agentDirty, setAgentDirty] = useState(false);
    const [ocrDirty, setOcrDirty] = useState(false);
    const [translationDirty, setTranslationDirty] = useState(false);
    const [baseAutoSaving, setBaseAutoSaving] = useState(false);
    const [agentAutoSaving, setAgentAutoSaving] = useState(false);
    const [ocrAutoSaving, setOcrAutoSaving] = useState(false);
    const [translationAutoSaving, setTranslationAutoSaving] = useState(false);
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
    const [activeTab, setActiveTab] = useState<SettingsTab>("translation");

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

    useEffect(() => {
        if (translationProfiles?.profiles) {
            setTranslationDraft(
                translationProfiles.profiles.map((profile) => ({ ...profile })),
            );
            setTranslationDirty(false);
        }
    }, [translationProfiles]);

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

    const translationModelOptions = useMemo(() => {
        const raw = translationProfiles?.options?.models;
        return Array.isArray(raw) ? raw.map(String) : [];
    }, [translationProfiles]);

    const translationReasoningOptions = useMemo(() => {
        const raw = translationProfiles?.options?.reasoning_effort;
        return Array.isArray(raw) ? raw.map(String) : ["low", "medium", "high"];
    }, [translationProfiles]);

    const confThreshold = useMemo(
        () => draftString(draft, "detection.conf_threshold"),
        [draft],
    );
    const iouThreshold = useMemo(
        () => draftString(draft, "detection.iou_threshold"),
        [draft],
    );
    const agentDetectionProfileId = useMemo(
        () => draftString(draft, "agent.translate.detection_profile_id"),
        [draft],
    );
    const containmentThreshold = useMemo(
        () => draftString(draft, "detection.containment_threshold"),
        [draft],
    );
    const translateSingleBoxUseContext = useMemo(
        () => draftBoolean(draft, "translation.single_box.use_context", true),
        [draft],
    );
    const includePriorContextSummary = useMemo(
        () =>
            draftBoolean(
                draft,
                "agent.translate.include_prior_context_summary",
                true,
            ),
        [draft],
    );
    const includePriorCharacters = useMemo(
        () => draftBoolean(draft, "agent.translate.include_prior_characters", true),
        [draft],
    );
    const includePriorOpenThreads = useMemo(
        () =>
            draftBoolean(draft, "agent.translate.include_prior_open_threads", true),
        [draft],
    );
    const includePriorGlossary = useMemo(
        () => draftBoolean(draft, "agent.translate.include_prior_glossary", true),
        [draft],
    );
    const ocrParallelismLocal = useMemo(
        () => draftString(draft, "ocr.parallelism.local"),
        [draft],
    );
    const ocrParallelismRemote = useMemo(
        () => draftString(draft, "ocr.parallelism.remote"),
        [draft],
    );
    const ocrParallelismMaxWorkers = useMemo(
        () => draftString(draft, "ocr.parallelism.max_workers"),
        [draft],
    );
    const ocrParallelismLeaseSeconds = useMemo(
        () => draftString(draft, "ocr.parallelism.lease_seconds"),
        [draft],
    );
    const ocrParallelismTaskTimeoutSeconds = useMemo(
        () => draftString(draft, "ocr.parallelism.task_timeout_seconds"),
        [draft],
    );

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
            "agent.translate.include_prior_context_summary":
                includePriorContextSummary,
            "agent.translate.include_prior_characters": includePriorCharacters,
            "agent.translate.include_prior_open_threads": includePriorOpenThreads,
            "agent.translate.include_prior_glossary": includePriorGlossary,
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
            includePriorContextSummary,
            includePriorCharacters,
            includePriorOpenThreads,
            includePriorGlossary,
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

    const updateTranslationProfile = (
        id: string,
        updates: Partial<TranslationDraftProfile>,
    ) => {
        setTranslationDraft((prev) =>
            prev.map((profile) =>
                profile.id === id ? { ...profile, ...updates } : profile,
            ),
        );
        setTranslationDirty(true);
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

    const buildTranslationPayload = useCallback(
        () => ({
            profiles: translationDraft.map((profile) => ({
                profile_id: profile.id,
                single_box_enabled: profile.single_box_enabled,
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
        [translationDraft],
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

    useEffect(() => {
        if (!translationDirty || translationDraft.length === 0) {
            return;
        }
        if (!autoSaveEnabled) {
            return;
        }
        if (agentLoading) {
            return;
        }
        const handle = setTimeout(() => {
            setTranslationAutoSaving(true);
            saveTranslationProfiles(buildTranslationPayload())
                .then(() => {
                    setSaveMessage("Translation profile settings saved.");
                    setTranslationDirty(false);
                })
                .catch(() => {
                    setSaveMessage(null);
                })
                .finally(() => {
                    setTranslationAutoSaving(false);
                });
        }, 400);
        return () => clearTimeout(handle);
    }, [
        translationDirty,
        translationDraft.length,
        autoSaveEnabled,
        agentLoading,
        saveTranslationProfiles,
        buildTranslationPayload,
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

            if (translationDraft.length) {
                await saveTranslationProfiles(buildTranslationPayload());
            }

            setSaveMessage("Saved.");
            setBaseDirty(false);
            setAgentDirty(false);
            setOcrDirty(false);
            setTranslationDirty(false);
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

    const handleRefresh = () => {
        void refresh();
        void refreshAgent();
        void refreshDetectionProfiles();
    };

    const loading = baseLoading || agentLoading;
    const error = baseError || agentError;

    return {
        loading,
        error,
        activeTab,
        setActiveTab,
        autoSaveEnabled,
        setAutoSaveEnabled,
        baseAutoSaving,
        agentAutoSaving,
        ocrAutoSaving,
        translationAutoSaving,
        saving,
        restartingBackend,
        saveMessage,
        handleSave,
        handleRestartBackend,
        handleRefresh,
        confThreshold,
        iouThreshold,
        containmentThreshold,
        updateDraft,
        agentDraft,
        agentModelOptions,
        agentReasoningOptions,
        updateAgentDraft,
        agentDetectionProfileId,
        translateSingleBoxUseContext,
        includePriorContextSummary,
        includePriorCharacters,
        includePriorOpenThreads,
        includePriorGlossary,
        agentDetectionLoading,
        agentDetectionOptions,
        hasAgentDetectionOptions,
        translationDraft,
        translationModelOptions,
        translationReasoningOptions,
        updateTranslationProfile,
        ocrDraft,
        ocrModelOptions,
        ocrReasoningOptions,
        updateOcrProfile,
        ocrParallelismLocal,
        ocrParallelismRemote,
        ocrParallelismMaxWorkers,
        ocrParallelismLeaseSeconds,
        ocrParallelismTaskTimeoutSeconds,
    };
}
