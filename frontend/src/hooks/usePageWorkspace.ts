// src/hooks/usePageWorkspace.ts
import { useMemo, useState } from "react";
import type { Box, BoxType } from "../types";
import { useJobs } from "../context/useJobs";
import { usePageBoxes } from "./usePageBoxes";
import { usePageJobActions } from "./usePageJobActions";
import { usePageJobEffects } from "./usePageJobEffects";
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
    onPageTranslationWorkflow: () => void;
    onClearBoxes: () => void;
    onClearOcrText: () => void;
    onClearTranslationText: () => void;

    onAutoDetectBoxes: () => void;
    onRefreshPageState: () => void;
}


export interface PageWorkspaceResult {
    boxes: Box[];
    boxesByType: Record<BoxType, Box[]>;
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

export function usePageWorkspace({
    ocrProfileId,
    translationProfileId,
    boxDetectionProfileId,
    boxDetectionTask,
}: UsePageWorkspaceArgs): PageWorkspaceResult {
    const { jobs } = useJobs();
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
        handlePageTranslationWorkflow,
    } = usePageJobActions({
        boxes,
        ocrProfileId,
        translationProfileId,
        boxDetectionProfileId,
    });

    const normalizedDetectionTask = normalizeBoxType(boxDetectionTask);

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
        onPageTranslationWorkflow: () => {
            void handlePageTranslationWorkflow();
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
        onRefreshPageState: () => {
            void handleRefreshPageState();
        },
    };


    return {
        boxes,
        boxesByType,
        handleChangeBoxesForType,
        activeBoxType,
        setActiveBoxType,
        visibleBoxTypes,
        toggleVisibleBoxType,
        pageDataProps,
        pageActions,
    };
}
