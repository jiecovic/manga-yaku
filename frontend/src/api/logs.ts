// src/api/logs.ts
import { API_BASE, apiFetch } from "./client";

export interface LogFileInfo {
    name: string;
    size: number;
    updated_at: number;
}

export interface LogListResponse {
    files: LogFileInfo[];
}

export interface LogFileContent {
    name: string;
    size: number;
    updated_at: number;
    is_json: boolean;
    content?: unknown;
    raw?: string;
}

export async function fetchAgentTranslateLogs(): Promise<LogFileInfo[]> {
    const res = await apiFetch(`${API_BASE}/api/logs/agent/translate_page`, {
        headers: { Accept: "application/json" },
    });
    const data = (await res.json()) as LogListResponse;
    return data.files ?? [];
}

export async function fetchAgentTranslateLog(
    filename: string,
): Promise<LogFileContent> {
    const res = await apiFetch(
        `${API_BASE}/api/logs/agent/translate_page/${encodeURIComponent(filename)}`,
        {
            headers: { Accept: "application/json" },
        },
    );
    return res.json() as Promise<LogFileContent>;
}

export async function deleteAgentTranslateLog(
    filename: string,
): Promise<void> {
    await apiFetch(
        `${API_BASE}/api/logs/agent/translate_page/${encodeURIComponent(filename)}`,
        {
            method: "DELETE",
            headers: { Accept: "application/json" },
        },
    );
}

export async function clearAgentTranslateLogs(): Promise<number> {
    const res = await apiFetch(`${API_BASE}/api/logs/agent/translate_page`, {
        method: "DELETE",
        headers: { Accept: "application/json" },
    });
    const data = (await res.json()) as { deleted?: number };
    return data.deleted ?? 0;
}
