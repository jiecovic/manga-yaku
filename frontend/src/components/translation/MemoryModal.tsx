// src/components/translation/MemoryModal.tsx
import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { fetchPageMemory, fetchVolumeMemory } from "../../api/memory";
import type {
    CharacterMemory,
    GlossaryEntry,
    PageMemory,
    VolumeMemory,
} from "../../api/memory";
import { Button } from "../../ui/primitives";
import { ui } from "../../ui/tokens";

type MemoryTab = "volume" | "page";

interface MemoryModalProps {
    open: boolean;
    volumeId: string;
    volumeName?: string;
    filename: string;
    pageIndex: number;
    pageCount: number;
    onClose: () => void;
}

const emptyVolumeMemory: VolumeMemory = {
    rollingSummary: "",
    activeCharacters: [],
    openThreads: [],
    glossary: [],
};

const emptyPageMemory: PageMemory = {
    pageSummary: "",
    imageSummary: "",
    characters: [],
    openThreads: [],
    glossary: [],
};

function formatStamp(value?: string | null) {
    if (!value) {
        return "—";
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
        return value;
    }
    return parsed.toLocaleString();
}

function MemorySection({
    title,
    children,
}: {
    title: string;
    children: ReactNode;
}) {
    return (
        <div className="rounded-md border border-slate-800 bg-slate-950/60 p-3 space-y-2">
            <div className="text-[11px] uppercase tracking-wide text-slate-400">
                {title}
            </div>
            {children}
        </div>
    );
}

function MemoryList({
    items,
    emptyLabel,
}: {
    items: string[];
    emptyLabel: string;
}) {
    if (items.length === 0) {
        return <div className={ui.mutedTextTiny}>{emptyLabel}</div>;
    }
    return (
        <ul className="list-disc pl-5 text-xs text-slate-200 space-y-1">
            {items.map((item, idx) => (
                <li key={`${item}-${idx}`}>{item}</li>
            ))}
        </ul>
    );
}

function CharacterGrid({
    characters,
    emptyLabel,
}: {
    characters: CharacterMemory[];
    emptyLabel: string;
}) {
    if (characters.length === 0) {
        return <div className={ui.mutedTextTiny}>{emptyLabel}</div>;
    }
    return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {characters.map((char, idx) => (
                <div
                    key={`${char.name}-${idx}`}
                    className="rounded-md border border-slate-800 bg-slate-900/60 p-2"
                >
                    <div className="text-xs font-semibold text-slate-100">
                        {char.name || "unknown"}
                    </div>
                    <div className="text-[10px] text-slate-400">
                        {char.gender || "unknown"}
                    </div>
                    <div className="mt-1 text-[11px] text-slate-200 whitespace-pre-wrap">
                        {char.info || ""}
                    </div>
                </div>
            ))}
        </div>
    );
}

function GlossaryList({
    glossary,
    emptyLabel,
}: {
    glossary: GlossaryEntry[];
    emptyLabel: string;
}) {
    if (glossary.length === 0) {
        return <div className={ui.mutedTextTiny}>{emptyLabel}</div>;
    }
    return (
        <div className="space-y-2">
            {glossary.map((entry, idx) => (
                <div
                    key={`${entry.term}-${idx}`}
                    className="rounded-md border border-slate-800 bg-slate-900/60 p-2"
                >
                    <div className="text-xs font-semibold text-slate-100">
                        {entry.term} → {entry.translation}
                    </div>
                    {entry.note ? (
                        <div className="mt-1 text-[11px] text-slate-300">
                            {entry.note}
                        </div>
                    ) : null}
                </div>
            ))}
        </div>
    );
}

export function MemoryModal({
    open,
    volumeId,
    volumeName,
    filename,
    pageIndex,
    pageCount,
    onClose,
}: MemoryModalProps) {
    const [activeTab, setActiveTab] = useState<MemoryTab>("volume");
    const [volumeMemory, setVolumeMemory] = useState<VolumeMemory>(
        emptyVolumeMemory,
    );
    const [pageMemory, setPageMemory] = useState<PageMemory>(emptyPageMemory);
    const [volumeLoading, setVolumeLoading] = useState(false);
    const [pageLoading, setPageLoading] = useState(false);
    const [volumeError, setVolumeError] = useState<string | null>(null);
    const [pageError, setPageError] = useState<string | null>(null);

    const pageLabel = useMemo(() => {
        if (!filename) {
            return "No page selected";
        }
        const pageNum = pageCount > 0 ? `${pageIndex + 1}/${pageCount}` : "";
        return pageNum ? `Page ${pageNum} • ${filename}` : filename;
    }, [filename, pageCount, pageIndex]);

    const loadVolume = useCallback(async () => {
        if (!volumeId) {
            return;
        }
        setVolumeLoading(true);
        setVolumeError(null);
        try {
            const data = await fetchVolumeMemory(volumeId);
            setVolumeMemory(data);
        } catch (err) {
            if (err instanceof Error) {
                setVolumeError(err.message);
            } else {
                setVolumeError("Failed to load volume memory.");
            }
        } finally {
            setVolumeLoading(false);
        }
    }, [volumeId]);

    const loadPage = useCallback(async () => {
        if (!volumeId || !filename) {
            return;
        }
        setPageLoading(true);
        setPageError(null);
        try {
            const data = await fetchPageMemory(volumeId, filename);
            setPageMemory(data);
        } catch (err) {
            if (err instanceof Error) {
                setPageError(err.message);
            } else {
                setPageError("Failed to load page memory.");
            }
        } finally {
            setPageLoading(false);
        }
    }, [volumeId, filename]);

    useEffect(() => {
        if (!open) {
            return;
        }
        void loadVolume();
        void loadPage();
    }, [open, loadVolume, loadPage]);

    useEffect(() => {
        if (!open) {
            return;
        }
        const handleKey = (event: KeyboardEvent) => {
            if (event.key === "Escape") {
                onClose();
            }
        };
        window.addEventListener("keydown", handleKey);
        return () => window.removeEventListener("keydown", handleKey);
    }, [open, onClose]);

    if (!open) {
        return null;
    }

    return (
        <div
            className={ui.modalOverlay}
            onClick={() => onClose()}
            role="dialog"
            aria-modal="true"
        >
            <div
                className="w-full max-w-4xl rounded-lg border border-slate-700 bg-slate-900 p-4 shadow-xl"
                onClick={(event) => event.stopPropagation()}
            >
                <div className="flex items-start justify-between gap-3">
                    <div>
                        <div className={ui.modalTitle}>Story Memory</div>
                        <div className={ui.mutedTextTiny}>
                            {volumeName || volumeId || "No volume"} • {pageLabel}
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <Button
                            type="button"
                            variant="ghostSmall"
                            onClick={() => {
                                if (activeTab === "volume") {
                                    void loadVolume();
                                } else {
                                    void loadPage();
                                }
                            }}
                            disabled={
                                activeTab === "volume" ? volumeLoading : pageLoading
                            }
                        >
                            {activeTab === "volume"
                                ? volumeLoading
                                    ? "Refreshing..."
                                    : "Refresh"
                                : pageLoading
                                ? "Refreshing..."
                                : "Refresh"}
                        </Button>
                        <Button
                            type="button"
                            variant="modalCancel"
                            onClick={onClose}
                        >
                            Close
                        </Button>
                    </div>
                </div>

                <div className="mt-4 flex gap-2">
                    <button
                        type="button"
                        onClick={() => setActiveTab("volume")}
                        className={`${ui.tabButtonBase} ${
                            activeTab === "volume"
                                ? ui.tabButtonActive
                                : ui.tabButtonInactive
                        }`}
                    >
                        Volume
                    </button>
                    <button
                        type="button"
                        onClick={() => setActiveTab("page")}
                        className={`${ui.tabButtonBase} ${
                            activeTab === "page"
                                ? ui.tabButtonActive
                                : ui.tabButtonInactive
                        }`}
                        disabled={!filename}
                    >
                        Page
                    </button>
                </div>

                <div className="mt-4 max-h-[70vh] overflow-y-auto space-y-4">
                    {activeTab === "volume" && (
                        <>
                            {!volumeId && (
                                <div className={ui.mutedTextTiny}>
                                    Select a volume to view its memory.
                                </div>
                            )}
                            {volumeError && (
                                <div className={ui.errorTextXs}>
                                    {volumeError}
                                </div>
                            )}
                            {volumeId && !volumeError && (
                                <>
                                    <MemorySection title="Rolling summary">
                                        {volumeLoading ? (
                                            <div className={ui.mutedTextTiny}>
                                                Loading...
                                            </div>
                                        ) : volumeMemory.rollingSummary ? (
                                            <div className="text-xs text-slate-200 whitespace-pre-wrap">
                                                {volumeMemory.rollingSummary}
                                            </div>
                                        ) : (
                                            <div className={ui.mutedTextTiny}>
                                                No summary yet.
                                            </div>
                                        )}
                                    </MemorySection>

                                    <MemorySection title="Active characters">
                                        <CharacterGrid
                                            characters={volumeMemory.activeCharacters}
                                            emptyLabel="No active characters yet."
                                        />
                                    </MemorySection>

                                    <MemorySection title="Open threads">
                                        <MemoryList
                                            items={volumeMemory.openThreads}
                                            emptyLabel="No open threads yet."
                                        />
                                    </MemorySection>

                                    <MemorySection title="Glossary">
                                        <GlossaryList
                                            glossary={volumeMemory.glossary}
                                            emptyLabel="No glossary entries yet."
                                        />
                                    </MemorySection>

                                    <div className={ui.mutedTextMicro}>
                                        Last updated: {formatStamp(volumeMemory.updatedAt)}
                                    </div>
                                </>
                            )}
                        </>
                    )}

                    {activeTab === "page" && (
                        <>
                            {!filename && (
                                <div className={ui.mutedTextTiny}>
                                    Select a page to view its memory.
                                </div>
                            )}
                            {pageError && (
                                <div className={ui.errorTextXs}>{pageError}</div>
                            )}
                            {filename && !pageError && (
                                <>
                                    <MemorySection title="Page summary">
                                        {pageLoading ? (
                                            <div className={ui.mutedTextTiny}>
                                                Loading...
                                            </div>
                                        ) : pageMemory.pageSummary ? (
                                            <div className="text-xs text-slate-200 whitespace-pre-wrap">
                                                {pageMemory.pageSummary}
                                            </div>
                                        ) : (
                                            <div className={ui.mutedTextTiny}>
                                                No page summary yet.
                                            </div>
                                        )}
                                    </MemorySection>

                                    <MemorySection title="Image summary">
                                        {pageLoading ? (
                                            <div className={ui.mutedTextTiny}>
                                                Loading...
                                            </div>
                                        ) : pageMemory.imageSummary ? (
                                            <div className="text-xs text-slate-200 whitespace-pre-wrap">
                                                {pageMemory.imageSummary}
                                            </div>
                                        ) : (
                                            <div className={ui.mutedTextTiny}>
                                                No image summary yet.
                                            </div>
                                        )}
                                    </MemorySection>

                                    <MemorySection title="Characters (page)">
                                        <CharacterGrid
                                            characters={pageMemory.characters}
                                            emptyLabel="No page characters yet."
                                        />
                                    </MemorySection>

                                    <MemorySection title="Open threads (page)">
                                        <MemoryList
                                            items={pageMemory.openThreads}
                                            emptyLabel="No page threads yet."
                                        />
                                    </MemorySection>

                                    <MemorySection title="Glossary (page)">
                                        <GlossaryList
                                            glossary={pageMemory.glossary}
                                            emptyLabel="No page glossary yet."
                                        />
                                    </MemorySection>

                                    <div className={ui.mutedTextMicro}>
                                        Updated: {formatStamp(pageMemory.updatedAt)}
                                    </div>
                                </>
                            )}
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}
