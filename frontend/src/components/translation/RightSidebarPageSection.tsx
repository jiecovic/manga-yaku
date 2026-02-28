// src/components/translation/RightSidebarPageSection.tsx
import { useMemo, useState } from "react";
import { CollapsibleSection } from "./CollapsibleSection";
import { ui } from "../../ui/tokens";

interface PageSectionProps {
    pageIndex: number;
    pageCount: number;
    pageFilenames: string[];
    hasPrev: boolean;
    hasNext: boolean;
    loadingPages: boolean;
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
}

export function RightSidebarPageSection({
    pageIndex,
    pageCount,
    pageFilenames,
    hasPrev,
    hasNext,
    loadingPages,
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
}: PageSectionProps) {
    const pageNumbers = useMemo(
        () =>
            pageCount > 0
                ? Array.from({length: pageCount}, (_, i) => i + 1)
                : [],
        [pageCount],
    );
    const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
    const canDelete = !isDraftPage && pageCount > 0;
    const deleteLabel = currentPageFilename
        ? `Page ${pageIndex + 1} (${currentPageFilename})`
        : `Page ${pageIndex + 1}`;

    const handlePageSelect = (value: string) => {
        if (value === "new") {
            onInsertAfter();
            return;
        }
        const num = Number(value);
        if (!Number.isNaN(num) && num >= 1 && num <= pageCount) {
            onChangePage(num - 1);
        }
    };

    return (
        <CollapsibleSection title="Page" defaultOpen>
            <div className="space-y-3">
                {/* NAVIGATION */}
                <div className="flex items-center justify-between gap-2">
                    <button
                        onClick={onPrev}
                        disabled={!hasPrev}
                        className={
                            ui.button.navBase +
                            " " +
                            (hasPrev
                                ? ui.button.navEnabled
                                : ui.button.navDisabled)
                        }
                    >
                        &lt;- Prev
                    </button>

                    <select
                        disabled={loadingPages}
                        value={isDraftPage ? "new" : String(pageIndex + 1)}
                        onChange={(e) => handlePageSelect(e.target.value)}
                        className={`${ui.select} min-w-[80px]`}
                    >
                        {pageCount === 0 && (
                            <option value="new">New page</option>
                        )}
                        {pageNumbers.map((n) => (
                            <option key={n} value={n}>
                                {`Page ${n}${
                                    pageFilenames[n - 1]
                                        ? ` - ${pageFilenames[n - 1]}`
                                        : ""
                                }`}
                            </option>
                        ))}
                        {pageCount > 0 && (
                            <option value="new">New page</option>
                        )}
                    </select>

                    <button
                        onClick={onNext}
                        disabled={!hasNext}
                        className={
                            ui.button.navBase +
                            " " +
                            (hasNext
                                ? ui.button.navEnabled
                                : ui.button.navDisabled)
                        }
                    >
                        Next -&gt;
                    </button>
                </div>

                <div className="flex flex-wrap gap-2">
                    <button
                        type="button"
                        onClick={onInsertBefore}
                        disabled={isDraftPage || pageCount === 0}
                        className={
                            ui.button.insertBase +
                            " " +
                            (isDraftPage || pageCount === 0
                                ? ui.button.insertDisabled
                                : ui.button.insertEnabled)
                        }
                    >
                        Insert before
                    </button>
                    <button
                        type="button"
                        onClick={onInsertAfter}
                        disabled={isDraftPage}
                        className={
                            ui.button.insertBase +
                            " " +
                            (isDraftPage
                                ? ui.button.insertDisabled
                                : ui.button.insertEnabled)
                        }
                    >
                        Insert after
                    </button>
                    {isDraftPage && (
                        <button
                            type="button"
                            onClick={onCancelDraft}
                            className={ui.button.cancel}
                        >
                            Cancel
                        </button>
                    )}
                    <button
                        type="button"
                        onClick={() => setConfirmDeleteOpen(true)}
                        disabled={!canDelete}
                        className={
                            ui.button.deleteBase +
                            " " +
                            (canDelete
                                ? ui.button.deleteEnabled
                                : ui.button.deleteDisabled)
                        }
                    >
                        Delete page
                    </button>
                </div>

                <div className={ui.mutedTextTiny}>
                    {isDraftPage
                        ? `${draftLabel ?? "New page"} (paste to add)`
                        : `Page ${pageIndex + 1} / ${pageCount}`}
                </div>
                {!isDraftPage && currentPageFilename && (
                    <div className={ui.mutedTextTiny}>
                        File: {currentPageFilename}
                    </div>
                )}

            </div>
            {confirmDeleteOpen && (
                <div className={ui.modalOverlay}>
                    <div className={ui.modalPanel}>
                        <div className={ui.modalTitle}>
                            Delete page?
                        </div>
                        <div className={ui.modalText}>
                            This removes the page image, boxes, and translations.
                            <div className={`mt-1 ${ui.textBodySm}`}>
                                {deleteLabel}
                            </div>
                        </div>
                        <div className={ui.modalActions}>
                            <button
                                type="button"
                                onClick={() => setConfirmDeleteOpen(false)}
                                className={ui.button.modalCancel}
                            >
                                Cancel
                            </button>
                            <button
                                type="button"
                                onClick={() => {
                                    setConfirmDeleteOpen(false);
                                    onDeletePage();
                                }}
                                className={ui.button.modalDanger}
                            >
                                Delete
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </CollapsibleSection>
    );
}
