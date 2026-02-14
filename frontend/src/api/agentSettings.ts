// src/api/agentSettings.ts
import { API_BASE, apiFetch, getJson } from "./client";

export interface AgentTranslateSettingsValue {
    model_id: string;
    max_output_tokens?: number | null;
    reasoning_effort?: string | null;
    temperature?: number | null;
}

export interface AgentTranslateSettingsResponse {
    value: AgentTranslateSettingsValue;
    defaults: AgentTranslateSettingsValue;
    options: Record<string, unknown>;
}

export type UpdateAgentTranslateSettingsRequest = Partial<AgentTranslateSettingsValue>;

export function fetchAgentTranslateSettings(): Promise<AgentTranslateSettingsResponse> {
    return getJson<AgentTranslateSettingsResponse>(
        `${API_BASE}/api/settings/agent-translate`,
    );
}

export async function updateAgentTranslateSettings(
    payload: UpdateAgentTranslateSettingsRequest,
): Promise<AgentTranslateSettingsResponse> {
    const res = await apiFetch(`${API_BASE}/api/settings/agent-translate`, {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
        },
        body: JSON.stringify(payload),
    });

    return res.json() as Promise<AgentTranslateSettingsResponse>;
}
