import type { Box } from "../types";

function safePositiveInt(value: unknown): number | null {
    if (typeof value !== "number" || !Number.isFinite(value)) {
        return null;
    }
    const parsed = Math.trunc(value);
    return parsed > 0 ? parsed : null;
}

/**
 * Build a stable display index map for text boxes.
 *
 * Mirrors backend agent payload indexing behavior:
 * - Prefer existing positive orderIndex.
 * - If missing/invalid/duplicate, assign next available positive index.
 */
export function buildTextBoxIndexMap(textBoxes: Box[]): Map<number, number> {
    const sorted = [...textBoxes].sort((left, right) => {
        const leftOrder = safePositiveInt(left.orderIndex) ?? Number.POSITIVE_INFINITY;
        const rightOrder = safePositiveInt(right.orderIndex) ?? Number.POSITIVE_INFINITY;
        if (leftOrder !== rightOrder) {
            return leftOrder - rightOrder;
        }
        return left.id - right.id;
    });

    const idToIndex = new Map<number, number>();
    const used = new Set<number>();
    let nextIndex = 1;

    for (const box of sorted) {
        const preferred = safePositiveInt(box.orderIndex);
        let assigned = preferred ?? 0;

        if (assigned <= 0 || used.has(assigned)) {
            assigned = nextIndex;
            while (used.has(assigned)) {
                assigned += 1;
            }
        }

        idToIndex.set(box.id, assigned);
        used.add(assigned);
        nextIndex = Math.max(nextIndex, assigned + 1);
    }

    return idToIndex;
}
