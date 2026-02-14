// src/components/translation/PageDataPanel.tsx
import { useCallback, useRef } from "react";
import type { Box } from "../../types";
import { PageBoxCard } from "./PageBoxCard";
import { ui } from "../../ui/tokens";

export interface PageDataPanelProps {
    boxes: Box[];
    onDeleteBox: (id: number) => void;
    onMoveBox: (id: number, dir: "up" | "down") => void;
    onUpdateBoxText: (id: number, field: "text" | "translation", value: string) => void;
    onOcrBox: (id: number) => void;
    onTranslateBox: (id: number) => void;
    onToggleCollapse?: () => void;
    toggleLabel?: string;
}

/**
 * Scrollable panel listing all box cards for the current page.
 */
export function PageDataPanel({
    boxes,
    onDeleteBox,
    onMoveBox,
    onUpdateBoxText,
    onOcrBox,
    onTranslateBox,
    onToggleCollapse,
    toggleLabel,
}: PageDataPanelProps) {
    const hasBoxes = boxes.length > 0;

    const scrollRef = useRef<HTMLDivElement | null>(null);

    /**
     * Autosize a textarea and, if the user is near the bottom of the list,
     * keep their scroll position anchored relative to the bottom.
     */
    const autoSize = useCallback((el: HTMLTextAreaElement | null) => {
        if (!el) return;

        const container = scrollRef.current;

        let prevScrollBottom: number | null = null;
        let prevDistanceToBottom: number | null = null;

        if (container) {
            const {scrollHeight, scrollTop, clientHeight} = container;
            // distance from top of viewport to bottom of content
            prevScrollBottom = scrollHeight - scrollTop;
            // how far the viewport bottom is from the content bottom
            prevDistanceToBottom = scrollHeight - scrollTop - clientHeight;
        }

        // normal textarea autosize
        el.style.height = "auto";
        el.style.height = el.scrollHeight + "px";

        if (!container || prevScrollBottom === null || prevDistanceToBottom === null) {
            return;
        }

        // If user was near the bottom before resize, keep them there.
        const NEAR_BOTTOM_THRESHOLD = 40; // px
        if (prevDistanceToBottom <= NEAR_BOTTOM_THRESHOLD) {
            const {scrollHeight} = container;
            // keep the same distance from the *bottom*
            const newScrollTop = scrollHeight - prevScrollBottom;
            container.scrollTop = newScrollTop;
        }
    }, []);

    return (
        <div className={ui.panel}>
            <div className={ui.panelHeader}>
                <h2 className={ui.panelTitle}>
                    Page Data
                </h2>
                {onToggleCollapse && (
                    <button
                        type="button"
                        onClick={onToggleCollapse}
                        className={ui.panelToggle}
                    >
                        {toggleLabel ?? "Toggle"}
                    </button>
                )}
            </div>

            {/* scrollable list of boxes */}
            <div
                ref={scrollRef}
                className={ui.panelList}
            >
                {!hasBoxes && (
                    <div className={ui.mutedTextXs}>
                        No text boxes yet... draw on the page to create some.
                    </div>
                )}

                {hasBoxes && (
                    <ul className="space-y-2">
                        {boxes.map((box, idx) => (
                            <PageBoxCard
                                key={box.id}
                                box={box}
                                index={idx}
                                total={boxes.length}
                                onMove={onMoveBox}
                                onDelete={onDeleteBox}
                                onUpdateText={onUpdateBoxText}
                                onOcrBox={onOcrBox}
                                onTranslateBox={onTranslateBox}
                                autoSize={autoSize}
                            />
                        ))}

                        {/* small spacer so the last box isn't glued to the bottom */}
                        <li aria-hidden="true" className="h-6" />
                    </ul>
                )}
            </div>
        </div>
    );
}
