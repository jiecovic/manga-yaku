// src/api/settings.ts
import { API_BASE, apiFetch } from "./client";

export interface SettingsResponse {
    scope: string;
    values: Record<string, unknown>;
    defaults: Record<string, unknown>;
    options: Record<string, unknown>;
}

export interface UpdateSettingsRequest {
    scope?: string;
    values: Record<string, unknown>;
}

export async function fetchSettings(
    scope = "global",
): Promise<SettingsResponse> {
    const url = new URL(`${API_BASE}/api/settings`);
    url.searchParams.set("scope", scope);

    const res = await apiFetch(url.toString(), {
        headers: { Accept: "application/json" },
    });

    return res.json() as Promise<SettingsResponse>;
}

export async function updateSettings(
    payload: UpdateSettingsRequest,
): Promise<SettingsResponse> {
    const res = await apiFetch(`${API_BASE}/api/settings`, {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
        },
        body: JSON.stringify(payload),
    });

    return res.json() as Promise<SettingsResponse>;
}
