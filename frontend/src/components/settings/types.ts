export type ModelCapability = {
    model_id: string;
    applies_temperature: boolean;
    applies_reasoning_effort: boolean;
    temperature_support: string;
    notes: string[];
};

export type PageTranslationDraft = {
    model_id: string;
    max_output_tokens: string;
    reasoning_effort: string;
    temperature: string;
};

export type OcrDraftProfile = {
    id: string;
    label: string;
    description?: string | null;
    kind: string;
    enabled: boolean;
    page_translation_enabled: boolean;
    model_id?: string | null;
    max_output_tokens?: number | null;
    reasoning_effort?: string | null;
    temperature?: number | null;
};

export type TranslationDraftProfile = {
    id: string;
    label: string;
    description?: string | null;
    kind: string;
    enabled: boolean;
    single_box_enabled: boolean;
    effective_enabled: boolean;
    model_id?: string | null;
    max_output_tokens?: number | null;
    reasoning_effort?: string | null;
    temperature?: number | null;
};

export function coerceModelCapabilities(
    raw: unknown,
): Record<string, ModelCapability> {
    if (!raw || typeof raw !== "object") {
        return {};
    }
    const entries = Object.entries(raw as Record<string, unknown>);
    const result: Record<string, ModelCapability> = {};
    for (const [modelId, value] of entries) {
        if (!value || typeof value !== "object") {
            continue;
        }
        const record = value as Record<string, unknown>;
        result[modelId] = {
            model_id:
                typeof record.model_id === "string" ? record.model_id : modelId,
            applies_temperature: Boolean(record.applies_temperature),
            applies_reasoning_effort: Boolean(record.applies_reasoning_effort),
            temperature_support:
                typeof record.temperature_support === "string"
                    ? record.temperature_support
                    : "always",
            notes: Array.isArray(record.notes)
                ? record.notes.filter((item): item is string => typeof item === "string")
                : [],
        };
    }
    return result;
}

export function resolveModelCapability(
    capabilities: Record<string, ModelCapability>,
    modelId: string | null | undefined,
): ModelCapability {
    const normalized = typeof modelId === "string" ? modelId : "";
    return (
        capabilities[normalized] ?? {
            model_id: normalized,
            applies_temperature: true,
            applies_reasoning_effort: false,
            temperature_support: "always",
            notes: [],
        }
    );
}

export function toIntWithFallback(value: string, fallback: number): number {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) {
        return fallback;
    }
    return Math.trunc(parsed);
}
