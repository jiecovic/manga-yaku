// src/components/translation/TranslateLayout.tsx
import { useCallback, useEffect, useState } from "react";

import { JobsPanel } from "../JobsPanel";
import { MemoryModal } from "./MemoryModal";
import { PageDataPanel } from "./PageDataPanel";
import { PageViewer } from "./PageViewer";
import { RightSidebarTabs } from "./RightSidebarTabs";
import { PageProvider } from "../../context/PageContext";
import { useLibrary } from "../../context/useLibrary";
import { usePageWorkspace } from "../../hooks/usePageWorkspace";
import { Button, Field } from "../../ui/primitives";
import { ui } from "../../ui/tokens";
import type {
    BoxDetectionProfile,
    OcrProvider,
    PageInfo,
    TranslationProvider,
    Volume,
} from "../../types";

interface DraftInsertState {
    position: "before" | "after";
    anchorIndex: number | null;
}

interface TranslateInnerProps {
    volumes: Volume[];
    selectedVolumeId: string;
    pages: PageInfo[];
    pageIndex: number;
    pageCount: number;
    currentPageImageUrl: string | null;
    currentPageMissing: boolean;
    currentPageFilename: string;
    error: string | null;
    loadingVolumes: boolean;
    loadingPages: boolean;
    setSelectedVolumeId: (id: string) => void;
    setPageIndex: (i: number) => void;
    handlePrev: () => void;
    handleNext: () => void;
    refreshLibrary: () => void;
    createVolume: (name: string) => Promise<Volume>;
    addPageFromClipboard: (
        file: File,
        volumeIdOverride?: string,
        opts?: { insertBefore?: string; insertAfter?: string },
    ) => Promise<void>;
    draftInsert: DraftInsertState | null;
    setDraftInsert: (next: DraftInsertState | null) => void;
    importVolumesFromDisk: () => Promise<{
        volumesImported: number;
        pagesImported: number;
    }>;
    detectMissingVolumesInDb: () => Promise<{
        volumes: { id: string; name: string }[];
        pages: { volumeId: string; filename: string }[];
    }>;
    pruneMissingVolumesInDb: (
        ids: string[],
        pages: { volumeId: string; filename: string }[],
    ) => Promise<{ volumesDeleted: number; pagesDeleted: number }>;
    deletePageFromVolume: (volumeId: string, filename: string) => Promise<void>;
    boxDetectionProfiles: BoxDetectionProfile[];
    boxDetectionProfileId: string;
    setBoxDetectionProfileId: (id: string) => void;
    refreshBoxDetectionProfiles: () => Promise<void>;
    ocrProviders: OcrProvider[];
    ocrEngineId: string;
    setOcrEngineId: (id: string) => void;
    translationProviders: TranslationProvider[];
    translationProfileId: string;
    setTranslationProfileId: (id: string) => void;
}

function TranslateInner({
    volumes,
    selectedVolumeId,
    pages,
    pageIndex,
    pageCount,
    currentPageImageUrl,
    currentPageMissing,
    currentPageFilename,
    error,
    loadingVolumes,
    loadingPages,
    setSelectedVolumeId,
    setPageIndex,
    handlePrev,
    handleNext,
    refreshLibrary,
    createVolume,
    addPageFromClipboard,
    draftInsert,
    setDraftInsert,
    importVolumesFromDisk,
    detectMissingVolumesInDb,
    pruneMissingVolumesInDb,
    deletePageFromVolume,
    boxDetectionProfiles,
    boxDetectionProfileId,
    setBoxDetectionProfileId,
    refreshBoxDetectionProfiles,
    ocrProviders,
    ocrEngineId,
    setOcrEngineId,
    translationProviders,
    translationProfileId,
    setTranslationProfileId,
}: TranslateInnerProps) {
    // context usage settings (local UI state)
    const [pageDataCollapsed, setPageDataCollapsed] = useState(false);
    const [boxDetectionTask, setBoxDetectionTask] = useState("text");
    const [memoryOpen, setMemoryOpen] = useState(false);
    const isDraftPage = draftInsert !== null;
    const draftLabel = draftInsert
        ? draftInsert.anchorIndex === null
            ? "New page"
            : `New page (${draftInsert.position} page ${draftInsert.anchorIndex + 1})`
        : null;
    const emptyTitle = isDraftPage
        ? "New page"
        : currentPageMissing
        ? "Missing page"
        : "No page yet.";
    const emptySubtitle = isDraftPage
        ? "Paste an image (Ctrl+V) to add one."
        : currentPageMissing
        ? `File not found: ${currentPageFilename}`
        : "Paste an image (Ctrl+V) to add one.";

    const resolveDraftAnchor = useCallback(() => {
        if (!draftInsert || draftInsert.anchorIndex === null) {
            return null;
        }
        return pages[draftInsert.anchorIndex] ?? null;
    }, [draftInsert, pages]);

    const clearDraftInsert = useCallback(() => {
        setDraftInsert(null);
    }, [setDraftInsert]);

    useEffect(() => {
        if (!draftInsert) {
            return;
        }
        if (draftInsert.anchorIndex !== null && draftInsert.anchorIndex >= pages.length) {
            clearDraftInsert();
        }
    }, [draftInsert, pages.length, clearDraftInsert]);

    useEffect(() => {
        clearDraftInsert();
    }, [selectedVolumeId, clearDraftInsert]);

    const handleInsertBefore = () => {
        if (draftInsert) {
            return;
        }
        if (pages.length === 0) {
            setDraftInsert({position: "after", anchorIndex: null});
            return;
        }
        const anchorIndex = Math.min(pageIndex, pages.length - 1);
        setDraftInsert({position: "before", anchorIndex});
    };

    const handleInsertAfter = () => {
        if (draftInsert) {
            return;
        }
        if (pages.length === 0) {
            setDraftInsert({position: "after", anchorIndex: null});
            return;
        }
        const anchorIndex = Math.min(pageIndex, pages.length - 1);
        setDraftInsert({position: "after", anchorIndex});
    };

    const draftPrevIndex = (() => {
        if (!draftInsert || draftInsert.anchorIndex === null) {
            return null;
        }
        if (draftInsert.position === "before") {
            const prev = draftInsert.anchorIndex - 1;
            return prev >= 0 ? prev : null;
        }
        return draftInsert.anchorIndex;
    })();

    const draftNextIndex = (() => {
        if (!draftInsert || draftInsert.anchorIndex === null) {
            return null;
        }
        if (draftInsert.position === "before") {
            return draftInsert.anchorIndex;
        }
        const next = draftInsert.anchorIndex + 1;
        return next < pages.length ? next : null;
    })();

    const canPrev = draftInsert
        ? draftPrevIndex !== null
        : pages.length > 0;
    const canNext = draftInsert
        ? draftNextIndex !== null
        : pages.length > 0;

    const handlePrevClick = () => {
        if (draftInsert) {
            if (draftPrevIndex !== null) {
                setPageIndex(draftPrevIndex);
            }
            clearDraftInsert();
            return;
        }
        if (pageIndex > 0) {
            handlePrev();
            return;
        }
        if (pages.length > 0 && pageIndex === 0) {
            setDraftInsert({position: "before", anchorIndex: 0});
        }
    };

    const handleNextClick = () => {
        if (draftInsert) {
            if (draftNextIndex !== null) {
                setPageIndex(draftNextIndex);
            }
            clearDraftInsert();
            return;
        }
        if (pageIndex < pages.length - 1) {
            handleNext();
            return;
        }
        if (pages.length > 0 && pageIndex === pages.length - 1) {
            setDraftInsert({position: "after", anchorIndex: pages.length - 1});
            return;
        }
        if (pages.length === 0) {
            setDraftInsert({position: "after", anchorIndex: null});
        }
    };

    // page workspace (boxes, per-page context, actions)
    const {
        boxesByType,
        runtimeProbeBoxes,
        handleChangeBoxesForType,
        activeBoxType,
        setActiveBoxType,
        visibleBoxTypes,
        toggleVisibleBoxType,
        pageDataProps,
        pageActions,
    } = usePageWorkspace({
        ocrProfileId: ocrEngineId,
        translationProfileId,
        boxDetectionProfileId,
        boxDetectionTask,
    });
    const currentVolumeName =
        volumes.find((volume) => volume.id === selectedVolumeId)?.name ??
        selectedVolumeId;

    const [pasteCreateOpen, setPasteCreateOpen] = useState(false);
    const [pasteCreateName, setPasteCreateName] = useState("");
    const [pasteCreateError, setPasteCreateError] = useState<string | null>(null);
    const [pasteCreating, setPasteCreating] = useState(false);
    const [pendingPasteFile, setPendingPasteFile] = useState<File | null>(null);

    const closePasteCreate = () => {
        if (pasteCreating) {
            return;
        }
        setPasteCreateOpen(false);
        setPasteCreateError(null);
        setPendingPasteFile(null);
        setPasteCreateName("");
    };

    const handlePasteCreate = async () => {
        const trimmed = pasteCreateName.trim();
        if (!trimmed) {
            setPasteCreateError("Enter a volume name.");
            return;
        }
        if (!pendingPasteFile) {
            setPasteCreateError("No image found to paste.");
            return;
        }

        setPasteCreating(true);
        setPasteCreateError(null);
        try {
            const volume = await createVolume(trimmed);
            await addPageFromClipboard(pendingPasteFile, volume.id);
            closePasteCreate();
        } catch (err) {
            if (err instanceof Error && err.message) {
                setPasteCreateError(err.message.replace("Failed to create volume: ", ""));
            } else {
                setPasteCreateError("Failed to create volume.");
            }
        } finally {
            setPasteCreating(false);
        }
    };

    const handlePaste = useCallback(
        (event: ClipboardEvent) => {
            const target = event.target as HTMLElement | null;
            if (target) {
                const tag = target.tagName;
                if (
                    tag === "INPUT" ||
                    tag === "TEXTAREA" ||
                    target.isContentEditable
                ) {
                    return;
                }
            }

            const items = event.clipboardData?.items;
            if (!items) {
                return;
            }

            for (const item of items) {
                if (item.type.startsWith("image/")) {
                    const file = item.getAsFile();
                    if (file) {
                        if (!selectedVolumeId) {
                            setPendingPasteFile(file);
                            setPasteCreateName("");
                            setPasteCreateError(null);
                            setPasteCreateOpen(true);
                        } else {
                            const anchor = resolveDraftAnchor();
                            const insertBefore =
                                draftInsert?.position === "before"
                                    ? anchor?.filename
                                    : undefined;
                            const insertAfter =
                                draftInsert?.position === "after"
                                    ? anchor?.filename
                                    : undefined;
                            void addPageFromClipboard(file, undefined, {
                                insertBefore,
                                insertAfter,
                            }).finally(() => {
                                clearDraftInsert();
                            });
                        }
                        event.preventDefault();
                    }
                    break;
                }
            }
        },
        [
            addPageFromClipboard,
            clearDraftInsert,
            draftInsert,
            resolveDraftAnchor,
            selectedVolumeId,
        ],
    );

    useEffect(() => {
        if (typeof window === "undefined") {
            return undefined;
        }
        window.addEventListener("paste", handlePaste);
        return () => window.removeEventListener("paste", handlePaste);
    }, [handlePaste]);

    const handleAgentPageSwitch = useCallback(
        (filename: string) => {
            const target = filename.trim();
            if (!target || pages.length === 0) {
                return;
            }
            const nextIndex = pages.findIndex((page) => page.filename === target);
            if (nextIndex < 0) {
                return;
            }
            clearDraftInsert();
            setPageIndex(nextIndex);
        },
        [clearDraftInsert, pages, setPageIndex],
    );

    return (
        <div className={ui.appBody}>
            {/* LEFT: Jobs */}
            <JobsPanel />

            {/* LEFT: Canvas / page viewer */}
            <div className="flex-1 flex">
                <PageViewer
                    imageUrl={isDraftPage ? null : currentPageImageUrl}
                    loadingPages={loadingPages}
                    error={error}
                    boxesByType={boxesByType}
                    runtimeProbeBoxes={runtimeProbeBoxes}
                    visibleBoxTypes={visibleBoxTypes}
                    activeBoxType={activeBoxType}
                    onChangeBoxesForType={handleChangeBoxesForType}
                    onToggleVisibleBoxType={toggleVisibleBoxType}
                    onChangeActiveBoxType={setActiveBoxType}
                    hasPrev={canPrev}
                    hasNext={canNext}
                    onPrev={handlePrevClick}
                    onNext={handleNextClick}
                    emptyTitle={emptyTitle}
                    emptySubtitle={emptySubtitle}
                />
            </div>

            {!pageDataCollapsed && (
                <aside className={ui.pageDataSidebar}>
                    <PageDataPanel
                        {...pageDataProps}
                        onToggleCollapse={() => setPageDataCollapsed(true)}
                        toggleLabel="Collapse"
                    />
                </aside>
            )}

            {/* RIGHT: Tabs (page / library / tools) */}
            <RightSidebarTabs
                pageDataProps={pageDataProps}
                pageDataCollapsed={pageDataCollapsed}
                onTogglePageDataCollapsed={setPageDataCollapsed}
                // library
                volumes={volumes}
                selectedVolumeId={selectedVolumeId}
                loadingVolumes={loadingVolumes}
                loadingPages={loadingPages}
                onChangeVolume={setSelectedVolumeId}
                onRefreshPages={refreshLibrary}
                onCreateVolume={createVolume}
                onImportVolumes={importVolumesFromDisk}
                onDetectMissingVolumes={detectMissingVolumesInDb}
                onPruneMissingVolumes={pruneMissingVolumesInDb}
                // page navigation
                pageIndex={pageIndex}
                pageCount={pageCount}
                pageFilenames={pages.map((page) => page.filename)}
                hasPrev={canPrev}
                hasNext={canNext}
                onPrev={handlePrevClick}
                onNext={handleNextClick}
                onChangePage={(i) => {
                    clearDraftInsert();
                    setPageIndex(i);
                }}
                isDraftPage={isDraftPage}
                draftLabel={draftLabel}
                onInsertBefore={handleInsertBefore}
                onInsertAfter={handleInsertAfter}
                onCancelDraft={clearDraftInsert}
                currentPageFilename={currentPageFilename}
                onDeletePage={() => {
                    if (!currentPageFilename || !selectedVolumeId) {
                        return;
                    }
                    void deletePageFromVolume(selectedVolumeId, currentPageFilename);
                }}
                // profiles
                boxDetectionProfiles={boxDetectionProfiles}
                boxDetectionProfileId={boxDetectionProfileId}
                onChangeBoxDetectionProfile={setBoxDetectionProfileId}
                boxDetectionTask={boxDetectionTask}
                onChangeBoxDetectionTask={setBoxDetectionTask}
                onRefreshBoxDetectionProfiles={refreshBoxDetectionProfiles}
                ocrProviders={ocrProviders}
                translationProviders={translationProviders}
                ocrEngineId={ocrEngineId}
                translationProfileId={translationProfileId}
                onChangeOcrEngine={setOcrEngineId}
                onChangeTranslationProfile={setTranslationProfileId}
                // page actions
                onOcrPage={pageActions.onOcrPage}
                onTranslatePage={pageActions.onTranslatePage}
                onAgentTranslatePage={pageActions.onAgentTranslatePage}
                onClearBoxes={pageActions.onClearBoxes}
                onClearOcrText={pageActions.onClearOcrText}
                onClearTranslationText={pageActions.onClearTranslationText}
                onAutoDetectBoxes={pageActions.onAutoDetectBoxes}
                onDetectMissingBoxes={pageActions.onDetectMissingBoxes}
                onRefreshPageState={pageActions.onRefreshPageState}
                onAgentPageSwitch={handleAgentPageSwitch}
                onOpenMemory={() => setMemoryOpen(true)}
                canOpenMemory={Boolean(selectedVolumeId)}
            />

            {pasteCreateOpen && (
                <div className={ui.modalOverlay}>
                    <div className={ui.modalPanel}>
                        <div className={ui.modalTitle}>
                            Create new volume
                        </div>
                        <div className={ui.modalText}>
                            Enter a name to save your pasted page.
                        </div>
                        <div className="mt-3 space-y-2">
                            <Field label="Name" labelClassName={ui.labelSmall}>
                                <input
                                    type="text"
                                    value={pasteCreateName}
                                    onChange={(e) =>
                                        setPasteCreateName(e.target.value)
                                    }
                                    onKeyDown={(e) => {
                                        if (e.key === "Enter") {
                                            e.preventDefault();
                                            void handlePasteCreate();
                                        }
                                    }}
                                    className={ui.input}
                                    placeholder="My Manga Volume"
                                    autoFocus
                                />
                            </Field>
                            {pasteCreateError && (
                                <div className={ui.warningTextTiny}>
                                    {pasteCreateError}
                                </div>
                            )}
                        </div>
                        <div className={ui.modalActions}>
                            <Button
                                type="button"
                                onClick={closePasteCreate}
                                variant="modalCancel"
                                disabled={pasteCreating}
                            >
                                Cancel
                            </Button>
                            <Button
                                type="button"
                                onClick={handlePasteCreate}
                                variant="modalPrimary"
                                disabled={pasteCreating}
                            >
                                {pasteCreating ? "Creating..." : "Create & Paste"}
                            </Button>
                        </div>
                    </div>
                </div>
            )}

            <MemoryModal
                open={memoryOpen}
                volumeId={selectedVolumeId}
                volumeName={currentVolumeName}
                filename={currentPageFilename}
                pageIndex={pageIndex}
                pageCount={pageCount}
                onClose={() => setMemoryOpen(false)}
            />
        </div>
    );
}

export function TranslateLayout() {
    const [draftInsert, setDraftInsert] = useState<DraftInsertState | null>(null);
    const {
        volumes,
        selectedVolumeId,
        pages,
        pageIndex,
        currentPage,
        currentPageImageUrl,
        error,
        loadingVolumes,
        loadingPages,
        setSelectedVolumeId,
        setPageIndex,
        handlePrev,
        handleNext,
        refreshLibrary,
        createVolume,
        addPageFromClipboard,
        deletePageFromVolume,
        importVolumesFromDisk,
        detectMissingVolumesInDb,
        pruneMissingVolumesInDb,
        boxDetectionProfiles,
        boxDetectionProfileId,
        setBoxDetectionProfileId,
        refreshBoxDetectionProfiles,
        ocrProviders,
        ocrEngineId,
        setOcrEngineId,
        translationProviders,
        translationProfileId,
        setTranslationProfileId,
    } = useLibrary();

    const currentVolumeId = currentPage?.volumeId ?? selectedVolumeId ?? "";
    const currentFilename = draftInsert ? "" : currentPage?.filename ?? "";
    const currentPageMissing = Boolean(currentPage?.missing);

    return (
        <PageProvider volumeId={currentVolumeId} filename={currentFilename}>
            <TranslateInner
                volumes={volumes}
                selectedVolumeId={selectedVolumeId}
                pages={pages}
                pageIndex={pageIndex}
                pageCount={pages.length}
                currentPageImageUrl={currentPageImageUrl}
                currentPageMissing={currentPageMissing}
                currentPageFilename={currentFilename}
                error={error}
                loadingVolumes={loadingVolumes}
                loadingPages={loadingPages}
                setSelectedVolumeId={setSelectedVolumeId}
                setPageIndex={setPageIndex}
                handlePrev={handlePrev}
                handleNext={handleNext}
                refreshLibrary={refreshLibrary}
                createVolume={createVolume}
                addPageFromClipboard={addPageFromClipboard}
                deletePageFromVolume={deletePageFromVolume}
                draftInsert={draftInsert}
                setDraftInsert={setDraftInsert}
                importVolumesFromDisk={importVolumesFromDisk}
                detectMissingVolumesInDb={detectMissingVolumesInDb}
                pruneMissingVolumesInDb={pruneMissingVolumesInDb}
                boxDetectionProfiles={boxDetectionProfiles}
                boxDetectionProfileId={boxDetectionProfileId}
                setBoxDetectionProfileId={setBoxDetectionProfileId}
                refreshBoxDetectionProfiles={refreshBoxDetectionProfiles}
                ocrProviders={ocrProviders}
                ocrEngineId={ocrEngineId}
                setOcrEngineId={setOcrEngineId}
                translationProviders={translationProviders}
                translationProfileId={translationProfileId}
                setTranslationProfileId={setTranslationProfileId}
            />
        </PageProvider>
    );
}
