import { API_BASE, apiFetch, getJson } from "./client";

export interface TranslationProfileSetting {
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
}

export interface TranslationProfileSettingsResponse {
    profiles: TranslationProfileSetting[];
    options: Record<string, unknown>;
}

export interface UpdateTranslationProfileSetting {
    profile_id: string;
    single_box_enabled?: boolean;
    model_id?: string | null;
    max_output_tokens?: number | null;
    reasoning_effort?: string | null;
    temperature?: number | null;
}

export interface UpdateTranslationProfileSettingsRequest {
    profiles: UpdateTranslationProfileSetting[];
}

export function fetchTranslationProfileSettings(): Promise<TranslationProfileSettingsResponse> {
    return getJson<TranslationProfileSettingsResponse>(
        `${API_BASE}/api/settings/translation-profiles`,
    );
}

export async function updateTranslationProfileSettings(
    payload: UpdateTranslationProfileSettingsRequest,
): Promise<TranslationProfileSettingsResponse> {
    const res = await apiFetch(`${API_BASE}/api/settings/translation-profiles`, {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
        },
        body: JSON.stringify(payload),
    });

    return res.json() as Promise<TranslationProfileSettingsResponse>;
}
