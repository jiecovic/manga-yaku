// src/hooks/useBoxDrawing.ts
import {useCallback, useState} from "react";
import type {KonvaEventObject} from "konva/lib/Node";
import type {Box, BoxType} from "../types";
import { normalizeBoxType } from "../utils/boxes";

interface UseBoxDrawingArgs {
    image: HTMLImageElement | null | undefined;
    boxes: Box[];
    activeType: BoxType;
    editableTypes: BoxType[];
    scale: number;
    onChangeBoxesForType: (type: BoxType, boxes: Box[]) => void;
}

export function useBoxDrawing({
                                  image,
                                  boxes,
                                  activeType,
                                  editableTypes,
                                  scale,
                                  onChangeBoxesForType,
                              }: UseBoxDrawingArgs) {
    const [isDrawing, setIsDrawing] = useState(false);
    const [draftBox, setDraftBox] = useState<Box | null>(null);
    const activeBoxes = boxes.filter(
        (box) => normalizeBoxType(box.type) === activeType,
    );

    // Mouse handlers for drawing boxes (image coordinates)
    const handleMouseDown = useCallback(
        (e: KonvaEventObject<MouseEvent>) => {
            if (!image) return;
            if (!editableTypes.includes(activeType)) return;

            const stage = e.target.getStage();
            if (!stage) return;

            const pointer = stage.getPointerPosition();
            if (!pointer) return;

            const {x: sx, y: sy} = pointer;

            // Convert stage coords -> image coords
            const ix = sx / scale;
            const iy = sy / scale;

            const newId =
                boxes.length > 0 ? Math.max(...boxes.map((b) => b.id)) + 1 : 1;

            const box: Box = {
                id: newId,
                x: ix,
                y: iy,
                width: 0,
                height: 0,
                type: activeType,
                source: "manual",
            };

            setDraftBox(box);
            setIsDrawing(true);
        },
        [image, boxes, scale, activeType, editableTypes],
    );

    const handleMouseMove = useCallback(
        (e: KonvaEventObject<MouseEvent>) => {
            if (!isDrawing || !draftBox || !image) return;

            const stage = e.target.getStage();
            if (!stage) return;

            const pointer = stage.getPointerPosition();
            if (!pointer) return;

            const {x: sx, y: sy} = pointer;

            // Convert stage coords -> image coords
            const ix = sx / scale;
            const iy = sy / scale;

            const width = ix - draftBox.x;
            const height = iy - draftBox.y;

            setDraftBox({
                ...draftBox,
                width,
                height,
            });
        },
        [isDrawing, draftBox, scale, image],
    );

    const handleMouseUp = useCallback(() => {
        if (!isDrawing || !draftBox) {
            setIsDrawing(false);
            setDraftBox(null);
            return;
        }

        // Normalize so width/height are positive (still in image coords)
        const normalized: Box = {
            ...draftBox,
            width: Math.abs(draftBox.width),
            height: Math.abs(draftBox.height),
            x: draftBox.width < 0 ? draftBox.x + draftBox.width : draftBox.x,
            y: draftBox.height < 0 ? draftBox.y + draftBox.height : draftBox.y,
        };

        if (normalized.width <= 0 || normalized.height <= 0) {
            setIsDrawing(false);
            setDraftBox(null);
            return;
        }

        onChangeBoxesForType(activeType, [...activeBoxes, normalized]);

        setIsDrawing(false);
        setDraftBox(null);
    }, [isDrawing, draftBox, activeBoxes, onChangeBoxesForType, activeType]);

    // Helper: map image-space box -> stage-space rect
    const toStageRect = (box: Box) => {
        return {
            x: box.x * scale,
            y: box.y * scale,
            width: box.width * scale,
            height: box.height * scale,
        };
    };

    return {
        draftBox,
        handleMouseDown,
        handleMouseMove,
        handleMouseUp,
        toStageRect,
    };
}
