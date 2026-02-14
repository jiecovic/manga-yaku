// src/components/translation/PageBoxCard.tsx
import type { Box } from "../../types";
import { ui } from "../../ui/tokens";

interface PageBoxCardProps {
    box: Box;
    index: number;
    total: number;
    onMove: (id: number, dir: "up" | "down") => void;
    onDelete: (id: number) => void;
    onUpdateText: (
        id: number,
        field: "text" | "translation",
        value: string,
    ) => void;
    onOcrBox: (id: number) => void;
    onTranslateBox: (id: number) => void;
    autoSize: (el: HTMLTextAreaElement | null) => void;
}

export function PageBoxCard({
    box,
    index,
    total,
    onMove,
    onDelete,
    onUpdateText,
    onOcrBox,
    onTranslateBox,
    autoSize,
}: PageBoxCardProps) {
    const canMoveUp = index > 0;
    const canMoveDown = index < total - 1;

    const ocrText = box.text ?? "";
    const transText = box.translation ?? "";

    const handleCopy = (text: string) => {
        if (!text) return;
        if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
            navigator.clipboard.writeText(text).catch((err) => {
                console.error("Failed to copy text", err);
            });
        }
    };

    return (
        <li className={ui.card}>
            {/* header row: index + controls */}
            <div className={ui.cardHeader}>
                <div className="flex items-center gap-2">
                    <span className={ui.cardIndex}>
                        #{index + 1}
                    </span>

                    <button
                        type="button"
                        className={
                            canMoveUp
                                ? ui.button.miniMoveEnabled
                                : ui.button.miniMoveDisabled
                        }
                        onClick={() => canMoveUp && onMove(box.id, "up")}
                        disabled={!canMoveUp}
                    >
                        ^
                    </button>
                    <button
                        type="button"
                        className={
                            canMoveDown
                                ? ui.button.miniMoveEnabled
                                : ui.button.miniMoveDisabled
                        }
                        onClick={() => canMoveDown && onMove(box.id, "down")}
                        disabled={!canMoveDown}
                    >
                        v
                    </button>
                </div>

                <div className="flex items-center gap-2">
                    <button
                        type="button"
                        className={ui.button.miniAmber}
                        onClick={() => onOcrBox(box.id)}
                    >
                        OCR
                    </button>
                    <button
                        type="button"
                        className={ui.button.miniEmerald}
                        onClick={() => onTranslateBox(box.id)}
                    >
                        Trans
                    </button>
                    <button
                        type="button"
                        className={ui.button.miniRed}
                        onClick={() => onDelete(box.id)}
                    >
                        Del
                    </button>
                </div>
            </div>

            {/* OCR text + copy + clear button */}
            <div className="space-y-1">
                <div className={`flex items-center justify-between ${ui.metaMicro}`}>
                    <span>OCR</span>
                    <div className="flex items-center gap-1">
                        <button
                            type="button"
                            className={ui.button.miniIcon}
                            title="Copy OCR"
                            onClick={() => handleCopy(ocrText)}
                            disabled={!ocrText}
                        >
                            C
                        </button>
                        <button
                            type="button"
                            className={ui.button.miniIconSmall}
                            title="Clear OCR"
                            onClick={() => onUpdateText(box.id, "text", "")}
                        >
                            x
                        </button>
                    </div>
                </div>
                <textarea
                    // callback ref -> autosize immediately on mount
                    ref={(el) => autoSize(el)}
                    className={ui.textareaSmall}
                    rows={1}
                    value={ocrText}
                    onChange={(e) => {
                        onUpdateText(box.id, "text", e.target.value);
                        autoSize(e.target); // autosize on every change
                    }}
                    placeholder="OCR text"
                />
            </div>

            {/* Translation text + copy + clear button */}
            <div className="space-y-1">
                <div className={`flex items-center justify-between ${ui.metaMicro}`}>
                    <span>Trans</span>
                    <div className="flex items-center gap-1">
                        <button
                            type="button"
                            className={ui.button.miniIcon}
                            title="Copy translation"
                            onClick={() => handleCopy(transText)}
                            disabled={!transText}
                        >
                            C
                        </button>
                        <button
                            type="button"
                            className={ui.button.miniIconSmall}
                            title="Clear translation"
                            onClick={() => onUpdateText(box.id, "translation", "")}
                        >
                            x
                        </button>
                    </div>
                </div>
                <textarea
                    ref={(el) => autoSize(el)}
                    className={ui.textareaSmall}
                    rows={1}
                    value={transText}
                    onChange={(e) => {
                        onUpdateText(box.id, "translation", e.target.value);
                        autoSize(e.target);
                    }}
                    placeholder="Translation"
                />
            </div>
        </li>
    );
}
