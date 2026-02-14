// src/utils/progress.ts
export interface ProgressDisplay {
    progress: number | null;
    label: string | null;
    width: number | null;
}

export const getProgressDisplay = (
    value: number | null | undefined,
): ProgressDisplay => {
    if (typeof value !== "number" || Number.isNaN(value)) {
        return { progress: null, label: null, width: null };
    }
    const progress = Math.max(0, Math.min(100, value));
    const label =
        progress > 0 && progress < 1 ? "<1%" : `${Math.round(progress)}%`;
    const width = progress > 0 && progress < 1 ? 1 : progress;
    return { progress, label, width };
};
