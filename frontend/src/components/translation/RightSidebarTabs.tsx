// src/components/translation/RightSidebarTabs.tsx
import { useState } from "react";
import type {
    BoxDetectionProfile,
    OcrProvider,
    TranslationProvider,
    Volume,
} from "../../types";
import { PageDataPanel } from "./PageDataPanel";
import type { PageDataPanelProps } from "./PageDataPanel";
import { RightSidebarActionsSection } from "./RightSidebarActionsSection";
import { RightSidebarChatSection } from "./RightSidebarChatSection";
import { RightSidebarLibrarySection } from "./RightSidebarLibrarySection";
import { RightSidebarPageSection } from "./RightSidebarPageSection";
import { RightSidebarProfilesSection } from "./RightSidebarProfilesSection";
import { ui } from "../../ui/tokens";

type SidebarTab = "library" | "tools" | "chat";

interface RightSidebarTabsProps {
    pageDataProps: PageDataPanelProps;
    pageDataCollapsed: boolean;
    onTogglePageDataCollapsed: (next: boolean) => void;

    // library
    volumes: Volume[];
    selectedVolumeId: string;
    loadingVolumes: boolean;
    loadingPages: boolean;
    onChangeVolume: (id: string) => void;
    onRefreshPages: () => void;
    onCreateVolume: (name: string) => Promise<Volume>;
    onImportVolumes: () => Promise<{
        volumesImported: number;
        pagesImported: number;
    }>;
    onDetectMissingVolumes: () => Promise<{
        volumes: { id: string; name: string }[];
        pages: { volumeId: string; filename: string }[];
    }>;
    onPruneMissingVolumes: (
        ids: string[],
        pages: { volumeId: string; filename: string }[],
    ) => Promise<{ volumesDeleted: number; pagesDeleted: number }>;

    // page navigation
    pageIndex: number;
    pageCount: number;
    hasPrev: boolean;
    hasNext: boolean;
    onPrev: () => void;
    onNext: () => void;
    onChangePage: (index: number) => void;
    isDraftPage: boolean;
    draftLabel: string | null;
    onInsertBefore: () => void;
    onInsertAfter: () => void;
    onCancelDraft: () => void;
    currentPageFilename: string;
    onDeletePage: () => void;

    // profiles
    boxDetectionProfiles: BoxDetectionProfile[];
    boxDetectionProfileId: string;
    onChangeBoxDetectionProfile: (id: string) => void;
    boxDetectionTask: string;
    onChangeBoxDetectionTask: (task: string) => void;
    onRefreshBoxDetectionProfiles: () => Promise<void>;
    ocrProviders: OcrProvider[];
    translationProviders: TranslationProvider[];
    ocrEngineId: string;
    translationProfileId: string;
    onChangeOcrEngine: (id: string) => void;
    onChangeTranslationProfile: (id: string) => void;

    // actions
    onOcrPage: () => void;
    onTranslatePage: () => void;
    onAgentTranslatePage: () => void;
    onAgentRetranslatePage: () => void;
    onClearBoxes: () => void;
    onClearOcrText: () => void;
    onClearTranslationText: () => void;
    onAutoDetectBoxes: () => void;
    onRefreshPageState: () => void;
    onOpenMemory: () => void;
    canOpenMemory: boolean;
}

export function RightSidebarTabs({
    pageDataProps,
    pageDataCollapsed,
    onTogglePageDataCollapsed,
    volumes,
    selectedVolumeId,
    loadingVolumes,
    loadingPages,
    onChangeVolume,
    onRefreshPages,
    onCreateVolume,
    onImportVolumes,
    onDetectMissingVolumes,
    onPruneMissingVolumes,
    pageIndex,
    pageCount,
    hasPrev,
    hasNext,
    onPrev,
    onNext,
    onChangePage,
    isDraftPage,
    draftLabel,
    onInsertBefore,
    onInsertAfter,
    onCancelDraft,
    currentPageFilename,
    onDeletePage,
    boxDetectionProfiles,
    boxDetectionProfileId,
    onChangeBoxDetectionProfile,
    boxDetectionTask,
    onChangeBoxDetectionTask,
    onRefreshBoxDetectionProfiles,
    ocrProviders,
    translationProviders,
    ocrEngineId,
    translationProfileId,
    onChangeOcrEngine,
    onChangeTranslationProfile,
    onOcrPage,
    onTranslatePage,
    onAgentTranslatePage,
    onAgentRetranslatePage,
    onClearBoxes,
    onClearOcrText,
    onClearTranslationText,
    onAutoDetectBoxes,
    onRefreshPageState,
    onOpenMemory,
    canOpenMemory,
}: RightSidebarTabsProps) {
    const [activeTab, setActiveTab] = useState<SidebarTab>("library");

    const tabButton = (tab: SidebarTab, label: string) => {
        const isActive = activeTab === tab;
        return (
            <button
                key={tab}
                type="button"
                onClick={() => setActiveTab(tab)}
                className={
                    ui.tabButtonBase +
                    " " +
                    (isActive
                        ? ui.tabButtonActive
                        : ui.tabButtonInactive)
                }
            >
                {label}
            </button>
        );
    };

    return (
        <aside className={ui.sidebar}>
            <div className={ui.sidebarTabs}>
                <div className="flex gap-2">
                    {tabButton("library", "Library")}
                    {tabButton("tools", "Tools")}
                    {tabButton("chat", "Chat")}
                </div>
            </div>

            <div className="flex-1 overflow-hidden">
                {activeTab === "library" && (
                    <div className="h-full overflow-y-auto space-y-2">
                        <RightSidebarLibrarySection
                            volumes={volumes}
                            selectedVolumeId={selectedVolumeId}
                            loadingVolumes={loadingVolumes}
                            loadingPages={loadingPages}
                            onChangeVolume={onChangeVolume}
                            onRefreshPages={onRefreshPages}
                            onCreateVolume={onCreateVolume}
                            onImportVolumes={onImportVolumes}
                            onDetectMissingVolumes={onDetectMissingVolumes}
                            onPruneMissingVolumes={onPruneMissingVolumes}
                        />
                        <RightSidebarPageSection
                            pageIndex={pageIndex}
                            pageCount={pageCount}
                            hasPrev={hasPrev}
                            hasNext={hasNext}
                            loadingPages={loadingPages}
                            onPrev={onPrev}
                            onNext={onNext}
                            onChangePage={onChangePage}
                            isDraftPage={isDraftPage}
                            draftLabel={draftLabel}
                            onInsertBefore={onInsertBefore}
                            onInsertAfter={onInsertAfter}
                            onCancelDraft={onCancelDraft}
                            currentPageFilename={currentPageFilename}
                            onDeletePage={onDeletePage}
                        />
                        {pageDataCollapsed && (
                            <div className="flex-1 overflow-hidden">
                                <PageDataPanel
                                    {...pageDataProps}
                                    onToggleCollapse={() =>
                                        onTogglePageDataCollapsed(false)
                                    }
                                    toggleLabel="Expand"
                                />
                            </div>
                        )}
                    </div>
                )}

                {activeTab === "tools" && (
                    <div className="h-full overflow-y-auto">
                        <RightSidebarProfilesSection
                            ocrProviders={ocrProviders}
                            translationProviders={translationProviders}
                            ocrEngineId={ocrEngineId}
                            translationProfileId={translationProfileId}
                            onChangeOcrEngine={onChangeOcrEngine}
                            onChangeTranslationProfile={onChangeTranslationProfile}
                        />
                        <RightSidebarActionsSection
                            selectedVolumeId={selectedVolumeId}
                            boxDetectionProfiles={boxDetectionProfiles}
                            boxDetectionProfileId={boxDetectionProfileId}
                            onChangeBoxDetectionProfile={onChangeBoxDetectionProfile}
                            boxDetectionTask={boxDetectionTask}
                            onChangeBoxDetectionTask={onChangeBoxDetectionTask}
                            onRefreshBoxDetectionProfiles={onRefreshBoxDetectionProfiles}
                            onOcrPage={onOcrPage}
                            onTranslatePage={onTranslatePage}
                            onAgentTranslatePage={onAgentTranslatePage}
                            onAgentRetranslatePage={onAgentRetranslatePage}
                            onClearBoxes={onClearBoxes}
                            onClearOcrText={onClearOcrText}
                            onClearTranslationText={onClearTranslationText}
                            onAutoDetectBoxes={onAutoDetectBoxes}
                            onRefreshPageState={onRefreshPageState}
                            onOpenMemory={onOpenMemory}
                            canOpenMemory={canOpenMemory}
                        />
                    </div>
                )}

                {activeTab === "chat" && (
                    <div className="h-full overflow-hidden">
                        <RightSidebarChatSection volumeId={selectedVolumeId} />
                    </div>
                )}
            </div>
        </aside>
    );
}
