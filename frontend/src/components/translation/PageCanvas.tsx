// src/components/translation/PageCanvas.tsx
import { useState, useCallback, useMemo, Fragment } from "react";
import { Stage, Layer, Image as KonvaImage, Rect, Label, Tag, Text, Group } from "react-konva";
import useImage from "use-image";

import type { Box, BoxType } from "../../types";
import { useCanvasLayout } from "../../hooks/useCanvasLayout";
import { useBoxDrawing } from "../../hooks/useBoxDrawing";
import { ui } from "../../ui/tokens";
import { BOX_RENDER_ORDER, BOX_TYPES } from "../../utils/boxes";

interface PageCanvasProps {
    imageUrl: string | null;
    boxesByType: Record<BoxType, Box[]>;
    visibleBoxTypes: BoxType[];
    activeBoxType: BoxType;
    editableBoxTypes: BoxType[];
    onChangeBoxesForType: (type: BoxType, boxes: Box[]) => void;
    onToggleVisibleBoxType: (type: BoxType) => void;
    onChangeActiveBoxType: (type: BoxType) => void;
    hasPrev: boolean;
    hasNext: boolean;
    onPrev?: () => void;
    onNext?: () => void;
    emptyTitle?: string;
    emptySubtitle?: string;
}

// Tooltip layout constants
const MIN_TOOLTIP_WIDTH = 200;
const MAX_TOOLTIP_WIDTH = 280;
const TOOLTIP_MARGIN = 8;
const TOOLTIP_PADDING = 8;

/**
 * Canvas for a single manga page:
 * - Renders the image and selection boxes
 * - Handles drawing new boxes
 * - Provides prev/next navigation arrows
 */
export function PageCanvas({
    imageUrl,
    boxesByType,
    visibleBoxTypes,
    activeBoxType,
    editableBoxTypes,
    onChangeBoxesForType,
    onToggleVisibleBoxType,
    onChangeActiveBoxType,
    hasPrev,
    hasNext,
    onPrev,
    onNext,
    emptyTitle,
    emptySubtitle,
}: PageCanvasProps) {
    const [image, status] = useImage(imageUrl || "");
    const hasImage = Boolean(image) && status === "loaded";
    const allBoxes = useMemo(
        () => BOX_TYPES.flatMap((type) => boxesByType[type] ?? []),
        [boxesByType],
    );

    // Layout + scaling logic
    const {containerRef, scale, stageSize} = useCanvasLayout(hasImage ? image : null);

    // Box drawing logic
    const {
        draftBox,
        handleMouseDown,
        handleMouseMove,
        handleMouseUp,
        toStageRect,
    } = useBoxDrawing({
        image,
        boxes: allBoxes,
        activeType: activeBoxType,
        editableTypes: editableBoxTypes,
        scale,
        onChangeBoxesForType,
    });

    // Hover state for tooltip
    const [hoveredBoxId, setHoveredBoxId] = useState<number | null>(null);

    const handlePrevClick = useCallback(() => {
        if (!hasPrev) return;
        onPrev?.();
    }, [hasPrev, onPrev]);

    const handleNextClick = useCallback(() => {
        if (!hasNext) return;
        onNext?.();
    }, [hasNext, onNext]);

    const visibleBoxes = useMemo(() => {
        const visible = new Set(visibleBoxTypes);
        return BOX_RENDER_ORDER.flatMap((type) =>
            visible.has(type) ? boxesByType[type] ?? [] : [],
        );
    }, [boxesByType, visibleBoxTypes]);

    const hoveredBox = useMemo(
        () => visibleBoxes.find((b) => b.id === hoveredBoxId),
        [visibleBoxes, hoveredBoxId],
    );
    const textIndexMap = useMemo(() => {
        const map = new Map<number, number>();
        boxesByType.text.forEach((box, index) => {
            const order =
                box.orderIndex && box.orderIndex > 0
                    ? box.orderIndex
                    : index + 1;
            map.set(box.id, order);
        });
        return map;
    }, [boxesByType.text]);

    const renderTooltip = () => {
        if (!hoveredBox || !hoveredBox.translation) return null;

        const rect = toStageRect(hoveredBox);

        // Decide tooltip text width independent of skinny boxes
        const tooltipWidth = Math.min(
            MAX_TOOLTIP_WIDTH,
            Math.max(MIN_TOOLTIP_WIDTH, rect.width),
        );
        const bubbleWidth = tooltipWidth + 2 * TOOLTIP_PADDING;

        // Center horizontally over the box, then clamp inside the stage
        const boxCenterX = rect.x + rect.width / 2;
        let tooltipX = boxCenterX - bubbleWidth / 2;

        if (tooltipX < TOOLTIP_MARGIN) {
            tooltipX = TOOLTIP_MARGIN;
        }
        if (tooltipX + bubbleWidth + TOOLTIP_MARGIN > stageSize.width) {
            tooltipX = Math.max(
                TOOLTIP_MARGIN,
                stageSize.width - bubbleWidth - TOOLTIP_MARGIN,
            );
        }

        // Vertical position: prefer above; if not possible, put below
        let tooltipY = rect.y - 40;
        if (tooltipY < TOOLTIP_MARGIN) {
            tooltipY = rect.y + TOOLTIP_MARGIN;
        }

        return (
            <Label x={tooltipX} y={tooltipY} listening={false}>
                <Tag
                    fill="rgba(255,255,255,0.92)"
                    cornerRadius={4}
                    shadowColor="black"
                    shadowBlur={6}
                    shadowOpacity={0.25}
                    lineJoin="round"
                />
                <Text
                    text={hoveredBox.translation}
                    padding={TOOLTIP_PADDING}
                    fontSize={14}
                    fontStyle="bold"
                    fill="#111827"
                    width={tooltipWidth}
                    wrap="word"
                    align="left"
                />
            </Label>
        );
    };

    const renderDraftBox = () => {
        if (!draftBox) return null;
        const rect = toStageRect(draftBox);
        const stroke =
            activeBoxType === "panel" ? "#22c55e" : "#f97316";
        return (
            <Rect
                x={rect.x}
                y={rect.y}
                width={rect.width}
                height={rect.height}
                stroke={stroke}
                strokeWidth={1}
                dash={[4, 4]}
            />
        );
    };

    const rowHeight = hasImage ? stageSize.height || 0 : "100%";
    const emptyTitleText = emptyTitle ?? "No page yet.";
    const emptySubtitleText =
        emptySubtitle ?? "Paste an image (Ctrl+V) to add one.";

    const layerTypes = useMemo(
        () =>
            BOX_RENDER_ORDER.filter(
                (type) =>
                    visibleBoxTypes.includes(type) ||
                    editableBoxTypes.includes(type) ||
                    (boxesByType[type] ?? []).length > 0,
            ),
        [boxesByType, editableBoxTypes, visibleBoxTypes],
    );

    return (
        <div ref={containerRef} className={ui.canvasWrap}>
            <div className={ui.layerPanel}>
                <div className={ui.layerTitle}>Layers</div>
                <div className={ui.layerGroup}>
                    {layerTypes.map((type) => (
                        <label key={type} className={ui.layerOption}>
                            <input
                                type="checkbox"
                                checked={visibleBoxTypes.includes(type)}
                                onChange={() => onToggleVisibleBoxType(type)}
                            />
                            <span className="uppercase">{type}</span>
                        </label>
                    ))}
                </div>
                <div className={ui.layerTitle}>Drawing</div>
                <div className={ui.layerGroup}>
                    {editableBoxTypes.map((type) => (
                        <label key={type} className={ui.layerOption}>
                            <input
                                type="radio"
                                name="active-layer"
                                checked={activeBoxType === type}
                                onChange={() => onChangeActiveBoxType(type)}
                            />
                            <span className="uppercase">{type}</span>
                        </label>
                    ))}
                </div>
            </div>
            {/* Row: [prev][stage][next] hugging image height */}
            <div
                className="flex items-center justify-center"
                style={{height: rowHeight}}
            >
                {/* Left arrow */}
                <button
                    type="button"
                    onClick={handlePrevClick}
                    disabled={!hasPrev}
                    style={{height: rowHeight}}
                    className={`${ui.canvasNavBase} ${
                        hasPrev ? ui.canvasNavEnabled : ui.canvasNavDisabled
                    }`}
                >
                    &lt;
                </button>

                {/* Stage container */}
                <div className="max-h-full max-w-full flex items-center justify-center">
                    {hasImage ? (
                        <Stage
                            width={stageSize.width}
                            height={stageSize.height}
                            onMouseDown={handleMouseDown}
                            onMouseMove={handleMouseMove}
                            onMouseUp={handleMouseUp}
                        >
                            <Layer>
                                {/* Page image */}
                                {image && (
                                    <KonvaImage
                                        image={image}
                                        width={stageSize.width}
                                        height={stageSize.height}
                                    />
                                )}

                                {/* Existing boxes + index badges */}
                                {visibleBoxes.map((box) => {
                                    const rect = toStageRect(box);
                                    const label =
                                        box.type === "text"
                                            ? String(textIndexMap.get(box.id) ?? "")
                                            : "";
                                    const style =
                                        box.type === "panel"
                                            ? {stroke: "#22c55e", strokeWidth: 2, dash: [6, 4]}
                                            : box.type === "face"
                                            ? {stroke: "#f472b6", strokeWidth: 2}
                                            : box.type === "body"
                                            ? {stroke: "#facc15", strokeWidth: 2}
                                            : {stroke: "#38bdf8", strokeWidth: 2};

                                    const badgeRadius = 9;
                                    const badgeDiameter = badgeRadius * 2;

                                    const badgeX = rect.x - badgeRadius + 2;
                                    const badgeY = rect.y - badgeRadius + 2;

                                    return (
                                        <Fragment key={box.id}>
                                            <Rect
                                                x={rect.x}
                                                y={rect.y}
                                                width={rect.width}
                                                height={rect.height}
                                                stroke={style.stroke}
                                                strokeWidth={style.strokeWidth}
                                                dash={style.dash}
                                                onMouseEnter={() =>
                                                    setHoveredBoxId(box.id)
                                                }
                                                onMouseLeave={() =>
                                                    setHoveredBoxId((current) =>
                                                        current === box.id
                                                            ? null
                                                            : current,
                                                    )
                                                }
                                            />
                                            {label && (
                                                <Group>
                                                    <Rect
                                                        x={badgeX}
                                                        y={badgeY}
                                                        width={badgeDiameter}
                                                        height={badgeDiameter}
                                                        cornerRadius={badgeRadius}
                                                        fill="#0f172a"
                                                        stroke={style.stroke}
                                                        strokeWidth={1}
                                                    />
                                                    <Text
                                                        x={badgeX}
                                                        y={badgeY}
                                                        width={badgeDiameter}
                                                        height={badgeDiameter}
                                                        text={label}
                                                        align="center"
                                                        verticalAlign="middle"
                                                        fontSize={11}
                                                        fill="#e5e7eb"
                                                    />
                                                </Group>
                                            )}
                                        </Fragment>
                                    );
                                })}

                                {/* Tooltip (on top of boxes) */}
                                {renderTooltip()}

                                {/* Draft box while drawing */}
                                {renderDraftBox()}
                            </Layer>
                        </Stage>
                    ) : (
                        <div className="w-full h-full flex items-center justify-center text-center">
                            <div className={ui.emptyState}>
                                <div>{emptyTitleText}</div>
                                <div className={ui.emptyStateSub}>
                                    {emptySubtitleText}
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {/* Right arrow */}
                <button
                    type="button"
                    onClick={handleNextClick}
                    disabled={!hasNext}
                    style={{height: rowHeight}}
                    className={`${ui.canvasNavBase} ${
                        hasNext ? ui.canvasNavEnabled : ui.canvasNavDisabled
                    }`}
                >
                    &gt;
                </button>
            </div>
        </div>
    );
}
