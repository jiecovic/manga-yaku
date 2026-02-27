// src/api/logs.ts
import { API_BASE, apiFetch } from "./client";

export interface LlmCallLogItem {
    id: string;
    provider: string;
    api: string;
    component: string;
    status: "success" | "error" | string;
    model_id?: string | null;
    job_id?: string | null;
    workflow_run_id?: string | null;
    task_run_id?: string | null;
    attempt?: number | null;
    latency_ms?: number | null;
    finish_reason?: string | null;
    input_tokens?: number | null;
    output_tokens?: number | null;
    total_tokens?: number | null;
    error_detail?: string | null;
    has_payload: boolean;
    created_at: number;
}

export interface LlmCallLogListResponse {
    logs: LlmCallLogItem[];
}

export interface LlmCallLogDetailResponse {
    log: LlmCallLogItem;
    params_snapshot?: Record<string, unknown> | null;
    request_excerpt?: string | null;
    response_excerpt?: string | null;
    payload_json?: unknown;
    payload_raw?: string | null;
}

export async function fetchLlmCallLogs(options?: {
    limit?: number;
    component?: string;
    status?: "success" | "error";
}): Promise<LlmCallLogItem[]> {
    const params = new URLSearchParams();
    if (options?.limit) {
        params.set("limit", String(options.limit));
    }
    if (options?.component) {
        params.set("component", options.component);
    }
    if (options?.status) {
        params.set("status", options.status);
    }
    const qs = params.toString();
    const url = `${API_BASE}/api/logs/llm-calls${qs ? `?${qs}` : ""}`;
    const res = await apiFetch(url, {
        headers: { Accept: "application/json" },
    });
    const data = (await res.json()) as LlmCallLogListResponse;
    return data.logs ?? [];
}

export async function fetchLlmCallLog(
    id: string,
): Promise<LlmCallLogDetailResponse> {
    const res = await apiFetch(
        `${API_BASE}/api/logs/llm-calls/${encodeURIComponent(id)}`,
        {
            headers: { Accept: "application/json" },
        },
    );
    return res.json() as Promise<LlmCallLogDetailResponse>;
}

export async function deleteLlmCallLog(id: string): Promise<void> {
    await apiFetch(`${API_BASE}/api/logs/llm-calls/${encodeURIComponent(id)}`, {
        method: "DELETE",
        headers: { Accept: "application/json" },
    });
}

export async function clearLlmCallLogs(): Promise<number> {
    const res = await apiFetch(`${API_BASE}/api/logs/llm-calls`, {
        method: "DELETE",
        headers: { Accept: "application/json" },
    });
    const data = (await res.json()) as { deleted?: number };
    return data.deleted ?? 0;
}
