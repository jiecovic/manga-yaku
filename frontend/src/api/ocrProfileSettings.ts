// src/api/ocrProfileSettings.ts
import { API_BASE, apiFetch, getJson } from "./client";

export interface OcrProfileSetting {
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
}

export interface OcrProfileSettingsResponse {
    profiles: OcrProfileSetting[];
    options: Record<string, unknown>;
}

export interface UpdateOcrProfileSetting {
    profile_id: string;
    agent_enabled?: boolean;
    model_id?: string | null;
    max_output_tokens?: number | null;
    reasoning_effort?: string | null;
    temperature?: number | null;
}

export interface UpdateOcrProfileSettingsRequest {
    profiles: UpdateOcrProfileSetting[];
}

export function fetchOcrProfileSettings(): Promise<OcrProfileSettingsResponse> {
    return getJson<OcrProfileSettingsResponse>(
        `${API_BASE}/api/settings/ocr-profiles`,
    );
}

export async function updateOcrProfileSettings(
    payload: UpdateOcrProfileSettingsRequest,
): Promise<OcrProfileSettingsResponse> {
    const res = await apiFetch(`${API_BASE}/api/settings/ocr-profiles`, {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
        },
        body: JSON.stringify(payload),
    });

    return res.json() as Promise<OcrProfileSettingsResponse>;
}
