// src/hooks/usePageBoxes.ts
import { useEffect, useMemo, useRef, useState } from "react";
import type { Box, BoxType } from "../types";
import {
    loadPageState,
    savePageState,
    createBoxDetectionJob,
    patchBoxText,
} from "../api/boxes";
import { usePage } from "../context/usePage";
import { normalizeBox, normalizeBoxType } from "../utils/boxes";

export interface UsePageBoxesResult {
    pageKey: string;
    boxes: Box[];
    boxesByType: Record<BoxType, Box[]>;
    setPageBoxesLocal: (updater: (prev: Box[]) => Box[]) => void;
    handleChangeBoxesForType: (type: BoxType, next: Box[]) => void;
    handleDeleteBox: (type: BoxType, id: number) => void;
    handleClearBoxes: (type: BoxType) => void;
    handleMoveBox: (type: BoxType, id: number, dir: "up" | "down") => void;
    handleUpdateBoxText: (
        id: number,
        field: "text" | "translation",
        value: string,
    ) => void;
    handleClearTextField: (field: "text" | "translation") => void;

    handleAutoDetectBoxes: (profileId?: string, task?: string) => Promise<void>;
    handleRefreshPageState: () => Promise<void>;
}

export function usePageBoxes(): UsePageBoxesResult {
    const { volumeId, filename } = usePage();
    const pageKey = volumeId && filename ? `${volumeId}::${filename}` : "";

    // Per-page cache for boxes
    const [boxesByPage, setBoxesByPage] = useState<Record<string, Box[]>>({});

    const boxes = useMemo(
        () => (pageKey ? boxesByPage[pageKey] ?? [] : []),
        [pageKey, boxesByPage],
    );

    const boxesByType = useMemo(() => {
        const groups: Record<BoxType, Box[]> = {
            text: [],
            panel: [],
            face: [],
            body: [],
        };
        for (const box of boxes) {
            const type = normalizeBoxType(box.type);
            groups[type].push(box);
        }
        (Object.keys(groups) as BoxType[]).forEach((type) => {
            groups[type] = [...groups[type]].sort((a, b) => {
                const aOrder = a.orderIndex ?? Number.POSITIVE_INFINITY;
                const bOrder = b.orderIndex ?? Number.POSITIVE_INFINITY;
                if (aOrder !== bOrder) {
                    return aOrder - bOrder;
                }
                return a.id - b.id;
            });
        });
        return groups;
    }, [boxes]);

    // Debounce timer for full-page saves (structural changes)
    const debounceRef = useRef<number | null>(null);
    const textDebounceRef = useRef<number | null>(null);
    const pendingTextUpdatesRef = useRef<
        Record<number, { text?: string; translation?: string }>
    >({});
    const textUpdateChainRef = useRef<Promise<void>>(Promise.resolve());

    // -------------------------------
    // Load box state when page changes
    // -------------------------------
    useEffect(() => {
        if (!pageKey || !volumeId || !filename) return;

        // Already cached -> no refetch
        if (boxesByPage[pageKey] !== undefined) return;

        let cancelled = false;

        const load = async () => {
            try {
                const loaded = await loadPageState(volumeId, filename);
                if (cancelled) return;

                setBoxesByPage((prev) => ({
                    ...prev,
                    [pageKey]: loaded.map(normalizeBox),
                }));
            } catch (err) {
                console.error("Failed to load page state:", err);
            }
        };

        void load();

        return () => {
            cancelled = true;
        };
    }, [pageKey, volumeId, filename, boxesByPage]);

    // -------------------------------
    // Local-only state setter for boxes
    // -------------------------------
    const setPageBoxesLocal = (updater: (prev: Box[]) => Box[]) => {
        if (!pageKey) return;

        setBoxesByPage((prev) => {
            const old = prev[pageKey] ?? [];
            const next = updater(old).map(normalizeBox);

            return {
                ...prev,
                [pageKey]: next,
            };
        });
    };

    const persistBoxes = (next: Box[], immediate: boolean) => {
        if (!volumeId || !filename) return;

        if (debounceRef.current !== null) {
            window.clearTimeout(debounceRef.current);
            debounceRef.current = null;
        }

        if (immediate) {
            savePageState(volumeId, filename, next, { keepalive: true }).catch((err) =>
                console.error("Immediate save failed:", err),
            );
            return;
        }

        debounceRef.current = window.setTimeout(() => {
            savePageState(volumeId, filename, next).catch((err) =>
                console.error("Debounced text save failed:", err),
            );
        }, 600);
    };

    const queueTextPatch = (
        boxId: number,
        payload: { text?: string | null; translation?: string | null },
        keepalive: boolean,
    ) => {
        if (!volumeId || !filename) {
            return;
        }
        textUpdateChainRef.current = textUpdateChainRef.current
            .then(() => patchBoxText(volumeId, filename, boxId, payload, { keepalive }))
            .catch((err) => console.error("Text patch failed:", err));
    };

    const flushPendingTextUpdates = () => {
        const pending = pendingTextUpdatesRef.current;
        pendingTextUpdatesRef.current = {};
        Object.entries(pending).forEach(([rawId, entry]) => {
            const boxId = Number(rawId);
            if (!entry) {
                return;
            }
            if (entry.text === undefined && entry.translation === undefined) {
                return;
            }
            queueTextPatch(boxId, entry, false);
        });
    };

    const updateBoxesAndPersist = (next: Box[], immediate: boolean) => {
        if (!pageKey) return;
        const normalized = next.map(normalizeBox);
        const orderCounters: Record<BoxType, number> = {
            text: 0,
            panel: 0,
            face: 0,
            body: 0,
        };
        const withOrder = normalized.map((box) => {
            const type = normalizeBoxType(box.type);
            orderCounters[type] += 1;
            return {
                ...box,
                orderIndex: orderCounters[type],
            };
        });
        setBoxesByPage((prev) => ({
            ...prev,
            [pageKey]: withOrder,
        }));
        persistBoxes(withOrder, immediate);
    };

    // -------------------------------
    // Handlers for structural changes
    // -------------------------------
    const handleChangeBoxesForType = (type: BoxType, next: Box[]) => {
        const normalizedType = normalizeBoxType(type);
        const normalizedNext = next.map((box) => ({
            ...box,
            type: normalizedType,
        }));
        const others = boxes.filter(
            (box) => normalizeBoxType(box.type) !== normalizedType,
        );
        updateBoxesAndPersist([...others, ...normalizedNext], true);
    };

    const handleDeleteBox = (type: BoxType, id: number) => {
        const normalizedType = normalizeBoxType(type);
        const next = boxes.filter(
            (b) =>
                !(
                    normalizeBoxType(b.type) === normalizedType && b.id === id
                ),
        );
        updateBoxesAndPersist(next, true);
    };

    const handleClearBoxes = (type: BoxType) => {
        const normalizedType = normalizeBoxType(type);
        const next = boxes.filter(
            (b) => normalizeBoxType(b.type) !== normalizedType,
        );
        updateBoxesAndPersist(next, true);
    };

    const handleMoveBox = (type: BoxType, id: number, dir: "up" | "down") => {
        const normalizedType = normalizeBoxType(type);
        const layer = boxes.filter(
            (b) => normalizeBoxType(b.type) === normalizedType,
        );
        const idx = layer.findIndex((b) => b.id === id);
        if (idx === -1) return;

        const target = dir === "up" ? idx - 1 : idx + 1;
        if (target < 0 || target >= layer.length) return;

        const nextLayer = [...layer];
        [nextLayer[idx], nextLayer[target]] = [nextLayer[target], nextLayer[idx]];
        handleChangeBoxesForType(normalizedType, nextLayer);
    };

    // -------------------------------
    // Handlers for text changes (debounced)
    // -------------------------------
    const handleUpdateBoxText = (
        id: number,
        field: "text" | "translation",
        value: string,
    ) => {
        setPageBoxesLocal((prev) =>
            prev.map((b) =>
                b.id === id && normalizeBoxType(b.type) === "text"
                    ? { ...b, [field]: value }
                    : b,
            ),
        );

        if (!volumeId || !filename) {
            return;
        }

        const immediate = value.trim() === "";
        if (immediate) {
            const pending = pendingTextUpdatesRef.current[id] ?? {};
            if (field === "text") {
                delete pending.text;
            } else {
                delete pending.translation;
            }
            if (pending.text === undefined && pending.translation === undefined) {
                delete pendingTextUpdatesRef.current[id];
            } else {
                pendingTextUpdatesRef.current[id] = pending;
            }
            const payload =
                field === "text"
                    ? { text: value }
                    : { translation: value };
            queueTextPatch(id, payload, true);
            return;
        }

        const pending = pendingTextUpdatesRef.current[id] ?? {};
        if (field === "text") {
            pending.text = value;
        } else {
            pending.translation = value;
        }
        pendingTextUpdatesRef.current[id] = pending;

        if (textDebounceRef.current !== null) {
            window.clearTimeout(textDebounceRef.current);
        }
        textDebounceRef.current = window.setTimeout(() => {
            flushPendingTextUpdates();
        }, 600);
    };

    const handleClearTextField = (field: "text" | "translation") => {
        if (!boxes.length) return;
        let changed = false;
        const next = boxes.map((b) => {
            if (normalizeBoxType(b.type) !== "text") {
                return b;
            }
            const current = field === "text" ? b.text : b.translation;
            if (!current) {
                return b;
            }
            changed = true;
            return { ...b, [field]: "" };
        });
        if (!changed) {
            return;
        }
        updateBoxesAndPersist(next, true);
    };

    // NEW: call YOLO auto-detect endpoint and update boxes
    const handleAutoDetectBoxes = async (
        profileId?: string,
        task?: string,
    ) => {
        if (!volumeId || !filename || !pageKey) return;

        try {
            await createBoxDetectionJob({
                volumeId,
                filename,
                profileId,
                task,
                replaceExisting: false,
            });
        } catch (err) {
            console.error("Auto-detect boxes failed:", err);
        }
    };

    // NEW: full refresh from backend (boxes)
    const handleRefreshPageState = async () => {
        if (!volumeId || !filename || !pageKey) return;

        try {
            const loadedBoxes = await loadPageState(volumeId, filename);

            setBoxesByPage((prev) => ({
                ...prev,
                [pageKey]: loadedBoxes.map(normalizeBox),
            }));
        } catch (err) {
            console.error("Refresh page state failed:", err);
        }
    };

    return {
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
        handleRefreshPageState,
    };
}
