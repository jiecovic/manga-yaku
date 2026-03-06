export type AgentDraft = {
    model_id: string;
    max_output_tokens: string;
    reasoning_effort: string;
    temperature: string;
    max_turns: string;
};

export type OcrDraftProfile = {
    id: string;
    label: string;
    description?: string | null;
    kind: string;
    enabled: boolean;
    agent_enabled: boolean;
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

export function toIntWithFallback(value: string, fallback: number): number {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) {
        return fallback;
    }
    return Math.trunc(parsed);
}
