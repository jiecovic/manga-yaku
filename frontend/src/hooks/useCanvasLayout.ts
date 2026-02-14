// src/hooks/useCanvasLayout.ts
import {useLayoutEffect, useRef, useState, useMemo} from "react";

interface Size {
    width: number;
    height: number;
}

export function useCanvasLayout(image: HTMLImageElement | null | undefined) {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const [containerSize, setContainerSize] = useState<Size>({
        width: 900,
        height: 1200,
    });

    useLayoutEffect(() => {
        const el = containerRef.current;
        if (!el) return;

        const measure = () => {
            const rect = el.getBoundingClientRect();

            const viewportHeight =
                typeof window !== "undefined" ? window.innerHeight : rect.height;

            const width = Math.max(rect.width, 200);
            // Clamp height to viewport so the image never gets taller than the screen.
            const height = Math.max(
                200,
                Math.min(rect.height, viewportHeight),
            );

            setContainerSize((prev) =>
                prev.width === width && prev.height === height
                    ? prev
                    : {width, height},
            );
        };

        // initial measure
        measure();

        // react to actual element size changes
        const ro = new ResizeObserver(measure);
        ro.observe(el);

        // still react to window resizes
        window.addEventListener("resize", measure);

        return () => {
            ro.disconnect();
            window.removeEventListener("resize", measure);
        };
    }, []);

    // Scale factor: image space <-> stage space
    const scale = useMemo(() => {
        if (!image || image.width <= 0 || image.height <= 0) {
            return 1;
        }
        return Math.min(
            containerSize.width / image.width,
            containerSize.height / image.height,
        );
    }, [image, containerSize]);

    const stageSize = useMemo<Size>(() => {
        if (!image || image.width <= 0 || image.height <= 0) {
            return {
                width: containerSize.width,
                height: containerSize.height,
            };
        }
        return {
            width: image.width * scale,
            height: image.height * scale,
        };
    }, [image, containerSize, scale]);

    return {
        containerRef,
        scale,
        stageSize,
    };
}
