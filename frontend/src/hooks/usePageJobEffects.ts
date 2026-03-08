// src/hooks/usePageJobEffects.ts
import {useEffect, useRef} from "react";
import type {Box} from "../types";
import type {Job} from "../api";
import { loadPageState } from "../api/boxes";
import {usePage} from "../context/usePage";
import { normalizeBox, normalizeBoxType } from "../utils/boxes";

interface UsePageJobEffectsArgs {
    pageKey: string;
    boxes: Box[];
    jobs: Job[];
    setPageBoxesLocal: (updater: (prev: Box[]) => Box[]) => void;
}

interface OcrJobPayload {
    volumeId?: string;
    volume_id?: string;
    filename?: string;
    file_name?: string;
    boxId?: number;
    box_id?: number;
    x?: number;
    y?: number;
    width?: number;
    height?: number;
    request?: Record<string, unknown>;
}

interface OcrJobResult {
    text?: string;
}

interface TranslateJobPayload {
    volumeId?: string;
    volume_id?: string;
    filename?: string;
    file_name?: string;
    boxId?: number;
    box_id?: number;
    request?: Record<string, unknown>;
}

interface TranslateJobResult {
    translation?: string;
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
        if (typeof raw === "string") {
            const trimmed = raw.trim();
            if (trimmed) {
                return trimmed;
            }
        }
    }
    return null;
}

function resolvePayloadPage(
    payload: Record<string, unknown> | null,
): {volumeId: string; filename: string} | null {
    if (!payload) {
        return null;
    }
    const nestedRequest = asRecord(payload.request);
    const candidates = [payload, nestedRequest];

    for (const candidate of candidates) {
        const resolvedVolumeId = readTrimmedString(candidate, [
            "volumeId",
            "volume_id",
        ]);
        const resolvedFilename = readTrimmedString(candidate, [
            "filename",
            "file_name",
        ]);
        if (resolvedVolumeId && resolvedFilename) {
            return {
                volumeId: resolvedVolumeId,
                filename: resolvedFilename,
            };
        }
    }
    return null;
}

function payloadMatchesPage(
    payload: Record<string, unknown> | null,
    volumeId: string,
    filename: string,
): boolean {
    const resolved = resolvePayloadPage(payload);
    if (!resolved) {
        return false;
    }
    return resolved.volumeId === volumeId && resolved.filename === filename;
}

// Helper: find box by coordinates (as stored in OCR job payload)
function findMatchingBoxIndex(boxes: Box[], payload: OcrJobPayload): number {
    const x = Number(payload.x);
    const y = Number(payload.y);
    const width = Number(payload.width);
    const height = Number(payload.height);
    const EPS = 1e-3;

    return boxes.findIndex(
        (b) =>
            normalizeBoxType(b.type) === "text" &&
            Math.abs(b.x - x) < EPS &&
            Math.abs(b.y - y) < EPS &&
            Math.abs(b.width - width) < EPS &&
            Math.abs(b.height - height) < EPS,
    );
}

export function usePageJobEffects({
    pageKey,
    boxes,
    jobs,
    setPageBoxesLocal,
}: UsePageJobEffectsArgs): void {
    const {volumeId, filename} = usePage();

    // Track which jobs we've already applied.
    const appliedOcrJobIdsRef = useRef<Set<string>>(new Set());
    const appliedTranslateJobIdsRef = useRef<Set<string>>(new Set());
    const appliedRefreshJobIdsRef = useRef<Set<string>>(new Set());
    const appliedAgentDetectRefreshRef = useRef<Set<string>>(new Set());
    const appliedAgentOcrRefreshRef = useRef<Set<string>>(new Set());
    const agentProgressRef = useRef<Record<string, { progress: number; ts: number }>>(
        {},
    );
    const pageLoadAtRef = useRef<number>(0);

    useEffect(() => {
        pageLoadAtRef.current = Date.now() / 1000;
    }, [pageKey]);

    // =======================================================
    // React to finished OCR jobs
    // =======================================================
    useEffect(() => {
        if (!volumeId || !filename || !pageKey) return;
        if (boxes.length === 0) return;

        const appliedIds = appliedOcrJobIdsRef.current;

        jobs.forEach((job) => {
            if (job.type !== "ocr_box") return;
            if (job.status !== "finished") return;
            if (!job.result) return;
            if (appliedIds.has(job.id)) return;
            if ((job.updated_at ?? 0) < pageLoadAtRef.current) return;

            const payload = job.payload as OcrJobPayload;
            const result = job.result as OcrJobResult;

            // Only apply to this page
            if (!payloadMatchesPage(asRecord(payload), volumeId, filename)) {
                return;
            }

            const text = typeof result?.text === "string" ? result.text : "";
            if (!text) {
                appliedIds.add(job.id);
                return;
            }

            setPageBoxesLocal((currentBoxes) => {
                const payloadBoxId = Number(payload.boxId ?? payload.box_id);
                const idx = Number.isFinite(payloadBoxId)
                    ? currentBoxes.findIndex(
                          (b) =>
                              b.id === payloadBoxId &&
                              normalizeBoxType(b.type) === "text",
                      )
                    : findMatchingBoxIndex(currentBoxes, payload);
                if (idx === -1) {
                    return currentBoxes;
                }

                const target = currentBoxes[idx];

                // If there's already text, don't overwrite (for now)
                if (target.text && String(target.text).trim().length > 0) {
                    return currentBoxes;
                }

                const updated = [...currentBoxes];
                updated[idx] = {...target, text};

                return updated;
            });

            appliedIds.add(job.id);
        });
    }, [jobs, volumeId, filename, pageKey, boxes.length, setPageBoxesLocal]);

    // =======================================================
    // React to finished TRANSLATE jobs
    // =======================================================
    useEffect(() => {
        if (!volumeId || !filename || !pageKey) return;
        if (boxes.length === 0) return;

        const appliedIds = appliedTranslateJobIdsRef.current;

        jobs.forEach((job) => {
            if (job.type !== "translate_box") return;
            if (job.status !== "finished") return;
            if (!job.result) return;
            if (appliedIds.has(job.id)) return;
            if ((job.updated_at ?? 0) < pageLoadAtRef.current) return;

            const payload = job.payload as TranslateJobPayload;
            const result = job.result as TranslateJobResult;

            // Only apply to this page
            if (!payloadMatchesPage(asRecord(payload), volumeId, filename)) {
                return;
            }

            const boxId = Number(payload.boxId ?? payload.box_id);
            if (!Number.isFinite(boxId)) {
                appliedIds.add(job.id);
                return;
            }

            const translation =
                typeof result?.translation === "string"
                    ? result.translation
                    : "";
            if (!translation) {
                appliedIds.add(job.id);
                return;
            }

            setPageBoxesLocal((currentBoxes) => {
                const idx = currentBoxes.findIndex(
                    (b) =>
                        b.id === boxId && normalizeBoxType(b.type) === "text",
                );
                if (idx === -1) {
                    return currentBoxes;
                }

                const target = currentBoxes[idx];

                // If there's already a translation, don't overwrite (for now)
                if (
                    target.translation &&
                    String(target.translation).trim().length > 0
                ) {
                    return currentBoxes;
                }

                const updated = [...currentBoxes];
                updated[idx] = {
                    ...target,
                    translation,
                };

                return updated;
            });

            appliedIds.add(job.id);
        });
    }, [jobs, volumeId, filename, pageKey, boxes.length, setPageBoxesLocal]);

    // =======================================================
    // React to finished BOX DETECTION jobs
    // =======================================================
    useEffect(() => {
        if (!volumeId || !filename || !pageKey) return;

        const appliedIds = appliedRefreshJobIdsRef.current;
        const pending = jobs.filter(
            (job) =>
                (job.type === "box_detection" ||
                    job.type === "ocr_box" ||
                    job.type === "translate_box" ||
                    job.type === "ocr_page" ||
                    job.type === "page_translation") &&
                job.status === "finished" &&
                !appliedIds.has(job.id) &&
                (job.updated_at ?? 0) >= pageLoadAtRef.current,
        );

        if (pending.length === 0) {
            return;
        }

        const matchesPage = pending.some((job) =>
            payloadMatchesPage(asRecord(job.payload), volumeId, filename),
        );

        if (!matchesPage) {
            pending.forEach((job) => {
                if (resolvePayloadPage(asRecord(job.payload))) {
                    appliedIds.add(job.id);
                }
            });
            return;
        }

        pending.forEach((job) => appliedIds.add(job.id));

        let cancelled = false;
        const refresh = async () => {
            try {
                const loadedBoxes = await loadPageState(volumeId, filename);
                if (cancelled) return;
                setPageBoxesLocal(() => loadedBoxes.map(normalizeBox));
            } catch (err) {
                console.error("Failed to refresh boxes after detection job", err);
            }
        };

        void refresh();

        return () => {
            cancelled = true;
        };
    }, [jobs, volumeId, filename, pageKey, setPageBoxesLocal]);

    // =======================================================
    // Refresh after page-translation detection stage (running job)
    // =======================================================
    useEffect(() => {
        if (!volumeId || !filename || !pageKey) return;

        const appliedIds = appliedAgentDetectRefreshRef.current;
        const pending = jobs.filter(
            (job) =>
                job.type === "page_translation" &&
                job.status === "running" &&
                !appliedIds.has(job.id) &&
                (job.progress ?? 0) >= 15,
        );

        if (pending.length === 0) {
            return;
        }

        const matchesPage = pending.some((job) =>
            payloadMatchesPage(asRecord(job.payload), volumeId, filename),
        );

        if (!matchesPage) {
            pending.forEach((job) => {
                if (resolvePayloadPage(asRecord(job.payload))) {
                    appliedIds.add(job.id);
                }
            });
            return;
        }

        pending.forEach((job) => appliedIds.add(job.id));

        let cancelled = false;
        const refresh = async () => {
            try {
                const loadedBoxes = await loadPageState(volumeId, filename);
                if (cancelled) return;
                setPageBoxesLocal(() => loadedBoxes.map(normalizeBox));
            } catch (err) {
                console.error("Failed to refresh boxes after page-translation detect", err);
            }
        };

        void refresh();

        return () => {
            cancelled = true;
        };
    }, [jobs, volumeId, filename, pageKey, setPageBoxesLocal]);

    // =======================================================
    // Refresh after page-translation OCR stage (running job)
    // =======================================================
    useEffect(() => {
        if (!volumeId || !filename || !pageKey) return;

        const appliedIds = appliedAgentOcrRefreshRef.current;
        const pending = jobs.filter(
            (job) =>
                job.type === "page_translation" &&
                job.status === "running" &&
                !appliedIds.has(job.id) &&
                (job.progress ?? 0) >= 60,
        );

        if (pending.length === 0) {
            return;
        }

        const matchesPage = pending.some((job) =>
            payloadMatchesPage(asRecord(job.payload), volumeId, filename),
        );

        if (!matchesPage) {
            pending.forEach((job) => {
                if (resolvePayloadPage(asRecord(job.payload))) {
                    appliedIds.add(job.id);
                }
            });
            return;
        }

        pending.forEach((job) => appliedIds.add(job.id));

        let cancelled = false;
        const refresh = async () => {
            try {
                const loadedBoxes = await loadPageState(volumeId, filename);
                if (cancelled) return;
                setPageBoxesLocal(() => loadedBoxes.map(normalizeBox));
            } catch (err) {
                console.error("Failed to refresh boxes after page-translation OCR", err);
            }
        };

        void refresh();

        return () => {
            cancelled = true;
        };
    }, [jobs, volumeId, filename, pageKey, setPageBoxesLocal]);

    // =======================================================
    // Incremental refresh during page-translation OCR (show text as it arrives)
    // =======================================================
    useEffect(() => {
        if (!volumeId || !filename || !pageKey) return;

        const now = Date.now();
        const pending = jobs.filter(
            (job) =>
                job.type === "page_translation" &&
                job.status === "running" &&
                (job.progress ?? 0) >= 15 &&
                (job.progress ?? 0) < 65 &&
                String(job.message || "").startsWith("OCR "),
        );

        if (pending.length === 0) {
            return;
        }

        const matchesPage = pending.some((job) =>
            payloadMatchesPage(asRecord(job.payload), volumeId, filename),
        );

        if (!matchesPage) {
            return;
        }

        const shouldRefresh = pending.some((job) => {
            const progress = Number(job.progress ?? 0);
            const entry = agentProgressRef.current[job.id];
            if (!entry) {
                agentProgressRef.current[job.id] = { progress, ts: now };
                return true;
            }
            const progressed = progress - entry.progress >= 3;
            const waited = now - entry.ts >= 500;
            if (progressed && waited) {
                agentProgressRef.current[job.id] = { progress, ts: now };
                return true;
            }
            return false;
        });

        if (!shouldRefresh) {
            return;
        }

        let cancelled = false;
        const refresh = async () => {
            try {
                const loadedBoxes = await loadPageState(volumeId, filename);
                if (cancelled) return;
                setPageBoxesLocal(() => loadedBoxes.map(normalizeBox));
            } catch (err) {
                console.error("Failed to refresh boxes during page-translation OCR", err);
            }
        };

        void refresh();

        return () => {
            cancelled = true;
        };
    }, [jobs, volumeId, filename, pageKey, setPageBoxesLocal]);
}
