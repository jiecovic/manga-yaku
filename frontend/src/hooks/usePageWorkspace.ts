// src/hooks/usePageWorkspace.ts
import { useMemo, useState } from "react";
import type {Box, BoxType} from "../types";
import {useJobs} from "../context/useJobs";
import { usePage } from "../context/usePage";
import {usePageBoxes} from "./usePageBoxes";
import {usePageJobEffects} from "./usePageJobEffects";
import {usePageJobActions} from "./usePageJobActions";
import { EDITABLE_BOX_TYPES, normalizeBoxType } from "../utils/boxes";

export interface PageDataProps {
    boxes: Box[];
    onDeleteBox: (id: number) => void;
    onMoveBox: (id: number, dir: "up" | "down") => void;
    onUpdateBoxText: (
        id: number,
        field: "text" | "translation",
        value: string,
    ) => void;
    onOcrBox: (id: number) => void;
    onTranslateBox: (id: number) => void;
}

export interface PageActions {
    onOcrPage: () => void;
    onTranslatePage: () => void;
    onAgentTranslatePage: () => void;
    onClearBoxes: () => void;
    onClearOcrText: () => void;
    onClearTranslationText: () => void;

    onAutoDetectBoxes: () => void;
    onDetectMissingBoxes: () => void;
    onRefreshPageState: () => void;
}


export interface PageWorkspaceResult {
    boxes: Box[];
    boxesByType: Record<BoxType, Box[]>;
    runtimeProbeBoxes: Box[];
    handleChangeBoxesForType: (type: BoxType, next: Box[]) => void;
    activeBoxType: BoxType;
    setActiveBoxType: (type: BoxType) => void;
    visibleBoxTypes: BoxType[];
    toggleVisibleBoxType: (type: BoxType) => void;
    pageDataProps: PageDataProps;
    pageActions: PageActions;
}

interface UsePageWorkspaceArgs {
    ocrProfileId: string;
    translationProfileId: string;
    boxDetectionProfileId: string;
    boxDetectionTask: string;
}

function asRecord(value: unknown): Record<string, unknown> | null {
    if (value && typeof value === "object" && !Array.isArray(value)) {
        return value as Record<string, unknown>;
    }
    return null;
}

function readTrimmedString(
    source: Record<string, unknown> | null,
    keys: string[],
): string | null {
    if (!source) {
        return null;
    }
    for (const key of keys) {
        const raw = source[key];
        if (typeof raw !== "string") {
            continue;
        }
        const value = raw.trim();
        if (value) {
            return value;
        }
    }
    return null;
}

function payloadMatchesPage(
    payload: Record<string, unknown> | null,
    volumeId: string,
    filename: string,
): boolean {
    const nestedRequest = asRecord(payload?.request);
    const candidates = [payload, nestedRequest];
    for (const candidate of candidates) {
        const currentVolume = readTrimmedString(candidate, ["volumeId", "volume_id"]);
        const currentFilename = readTrimmedString(candidate, ["filename", "file_name"]);
        if (currentVolume === volumeId && currentFilename === filename) {
            return true;
        }
    }
    return false;
}

export function usePageWorkspace({
                                     ocrProfileId,
                                     translationProfileId,
                                     boxDetectionProfileId,
                                     boxDetectionTask,
                                 }: UsePageWorkspaceArgs): PageWorkspaceResult {
    const {jobs} = useJobs();
    const { volumeId, filename } = usePage();
    const [activeBoxTypeByPage, setActiveBoxTypeByPage] = useState<
        Record<string, BoxType>
    >({});
    const [hiddenBoxTypes, setHiddenBoxTypes] = useState<BoxType[]>([]);

    const {
        pageKey,
        boxes,
        boxesByType,
        setPageBoxesLocal,
        handleChangeBoxesForType,
        handleDeleteBox,
        handleClearBoxes,
        handleMoveBox,
        handleUpdateBoxText,
        handleClearTextField,
        handleAutoDetectBoxes,
        handleDetectMissingBoxes,
        handleRefreshPageState,
    } = usePageBoxes();

    const activeBoxType = useMemo(() => {
        if (!pageKey) {
            return "text";
        }
        return activeBoxTypeByPage[pageKey] ?? "text";
    }, [activeBoxTypeByPage, pageKey]);

    const setActiveBoxType = (type: BoxType) => {
        if (!pageKey) {
            return;
        }
        setActiveBoxTypeByPage((prev) => {
            if (prev[pageKey] === type) {
                return prev;
            }
            return {
                ...prev,
                [pageKey]: type,
            };
        });
    };

    usePageJobEffects({
        pageKey,
        boxes,
        jobs,
        setPageBoxesLocal,
    });

    const {
        handleOcrPage,
        handleOcrBox,
        handleTranslateBox,
        handleTranslatePage,
        handleAgentTranslatePage,
    } = usePageJobActions({
        boxes,
        ocrProfileId,
        translationProfileId,
        boxDetectionProfileId,
    });

    const normalizedDetectionTask = normalizeBoxType(boxDetectionTask);

    const runtimeProbeBoxes = useMemo(() => {
        if (!volumeId || !filename) {
            return [];
        }

        const runningJobs = jobs.filter(
            (job) =>
                job.type === "detect_missing_boxes" &&
                (
                    job.status === "queued" ||
                    job.status === "running" ||
                    job.status === "finished"
                ) &&
                payloadMatchesPage(
                    asRecord(job.payload),
                    volumeId,
                    filename,
                ),
        );
        if (runningJobs.length === 0) {
            return [];
        }
        const latestJob = runningJobs.reduce((latest, current) =>
            current.updated_at > latest.updated_at ? current : latest,
        );
        const metrics = asRecord(latestJob.metrics);
        const runtime = asRecord(metrics?.missing_box_runtime);
        const trialHistory = Array.isArray(runtime?.trial_history)
            ? runtime?.trial_history
            : [];
        const trailProbeBoxes: Box[] = trialHistory
            .slice(-20)
            .reduce<Box[]>((acc, rawItem, index) => {
                const item = asRecord(rawItem);
                if (!item) {
                    return acc;
                }
                const x = Number(item.x);
                const y = Number(item.y);
                const width = Number(item.width);
                const height = Number(item.height);
                if (
                    !Number.isFinite(x) ||
                    !Number.isFinite(y) ||
                    !Number.isFinite(width) ||
                    !Number.isFinite(height) ||
                    width <= 0 ||
                    height <= 0
                ) {
                    return acc;
                }
                const status = String(item.status || "attempting").trim();
                const candidateIndex = Number(item.candidate_index ?? 0);
                const candidatesTotal = Number(item.candidates_total ?? 0);
                const attemptIndex = Number(item.attempt_index ?? 0);
                const attemptsPerCandidate = Number(item.attempts_per_candidate ?? 0);
                const probeLabel = [
                    Number.isFinite(candidateIndex) && candidateIndex > 0
                        ? `c${candidateIndex}/${Math.max(1, candidatesTotal)}`
                        : null,
                    Number.isFinite(attemptIndex) && attemptIndex > 0
                        ? `a${attemptIndex}/${Math.max(1, attemptsPerCandidate)}`
                        : null,
                    status,
                ]
                    .filter(Boolean)
                    .join(" ");
                acc.push({
                    id: -1000 - index,
                    orderIndex: 0,
                    x,
                    y,
                    width,
                    height,
                    type: "text" as const,
                    text: "",
                    translation: "",
                    note: probeLabel,
                });
                return acc;
            }, [])
        ;
        if (trailProbeBoxes.length > 0) {
            return trailProbeBoxes;
        }
        const latestTrial = asRecord(runtime?.latest_trial);
        if (!latestTrial) {
            return [];
        }

        const x = Number(latestTrial.x);
        const y = Number(latestTrial.y);
        const width = Number(latestTrial.width);
        const height = Number(latestTrial.height);
        if (
            !Number.isFinite(x) ||
            !Number.isFinite(y) ||
            !Number.isFinite(width) ||
            !Number.isFinite(height) ||
            width <= 0 ||
            height <= 0
        ) {
            return [];
        }

        const status = String(latestTrial.status || "attempting").trim();
        const candidateIndex = Number(latestTrial.candidate_index ?? 0);
        const candidatesTotal = Number(latestTrial.candidates_total ?? 0);
        const attemptIndex = Number(latestTrial.attempt_index ?? 0);
        const attemptsPerCandidate = Number(latestTrial.attempts_per_candidate ?? 0);
        const probeLabel = [
            Number.isFinite(candidateIndex) && candidateIndex > 0
                ? `c${candidateIndex}/${Math.max(1, candidatesTotal)}`
                : null,
            Number.isFinite(attemptIndex) && attemptIndex > 0
                ? `a${attemptIndex}/${Math.max(1, attemptsPerCandidate)}`
                : null,
            status,
        ]
            .filter(Boolean)
            .join(" ");

        return [
            {
                id: -1,
                orderIndex: 0,
                x,
                y,
                width,
                height,
                type: "text" as const,
                text: "",
                translation: "",
                note: probeLabel,
            },
        ];
    }, [jobs, volumeId, filename]);

    const visibleBoxTypes = useMemo(() => {
        const next = new Set<BoxType>(["text", "panel"]);
        (Object.keys(boxesByType) as BoxType[]).forEach((type) => {
            if (boxesByType[type].length > 0) {
                next.add(type);
            }
        });
        hiddenBoxTypes.forEach((type) => next.delete(type));
        return Array.from(next);
    }, [boxesByType, hiddenBoxTypes]);

    const toggleVisibleBoxType = (type: BoxType) => {
        setHiddenBoxTypes((prev) => {
            const next = new Set(prev);
            const willHide = !next.has(type);
            if (willHide) {
                next.add(type);
            } else {
                next.delete(type);
            }
            if (willHide && type === activeBoxType) {
                const fallback = EDITABLE_BOX_TYPES.find(
                    (item) => !next.has(item),
                );
                if (fallback) {
                    setActiveBoxType(fallback);
                }
            }
            return Array.from(next);
        });
    };

    const pageDataProps: PageDataProps = {
        boxes: boxesByType.text,
        onDeleteBox: (id: number) => handleDeleteBox("text", id),
        onMoveBox: (id: number, dir: "up" | "down") =>
            handleMoveBox("text", id, dir),
        onUpdateBoxText: handleUpdateBoxText,
        onOcrBox: (id: number) => {
            void handleOcrBox(id);
        },
        onTranslateBox: (id: number) => {
            void handleTranslateBox(id);
        },
    };

    const pageActions: PageActions = {
        onOcrPage: () => {
            void handleOcrPage();
        },
        onTranslatePage: () => {
            void handleTranslatePage();
        },
        onAgentTranslatePage: () => {
            void handleAgentTranslatePage();
        },
        onClearBoxes: () => {
            handleClearBoxes(normalizedDetectionTask);
        },
        onClearOcrText: () => {
            handleClearTextField("text");
        },
        onClearTranslationText: () => {
            handleClearTextField("translation");
        },

        // NEW
        onAutoDetectBoxes: () => {
            void handleAutoDetectBoxes(
                boxDetectionProfileId || undefined,
                boxDetectionTask || undefined,
            );
        },
        onDetectMissingBoxes: () => {
            void handleDetectMissingBoxes();
        },
        onRefreshPageState: () => {
            void handleRefreshPageState();
        },
    };


    return {
        boxes,
        boxesByType,
        runtimeProbeBoxes,
        handleChangeBoxesForType,
        activeBoxType,
        setActiveBoxType,
        visibleBoxTypes,
        toggleVisibleBoxType,
        pageDataProps,
        pageActions,
    };
}
