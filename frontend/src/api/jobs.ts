// src/api/jobs.ts
import { API_BASE, apiFetch } from "./client";

export interface CreateJobResponse {
    jobId: string;
}

export interface JobCapability {
    enabled: boolean;
    reason?: string | null;
}

export interface JobCapabilities {
    ocr_page: JobCapability;
    ocr_box: JobCapability;
    translate_page: JobCapability;
    translate_box: JobCapability;
    agent_translate_page: JobCapability;
}

export const DEFAULT_JOB_CAPABILITIES: JobCapabilities = {
    ocr_page: { enabled: true },
    ocr_box: { enabled: true },
    translate_page: {
        enabled: false,
        reason:
            "Standalone translation jobs are temporarily disabled during workflow rewrite. Use agent translate page workflow path.",
    },
    translate_box: { enabled: true },
    agent_translate_page: { enabled: true },
};

export type JobStatus = "queued" | "running" | "finished" | "failed" | "canceled";

export interface Job {
    id: string;
    type: string;
    status: JobStatus;
    created_at: number;
    updated_at: number;
    result?: Record<string, unknown> | null;
    error?: string | null;
    payload: Record<string, unknown>;
    progress?: number | null;
    message?: string | null;
    warnings?: string[] | null;
    metrics?: {
        epoch?: number | null;
        total_epochs?: number | null;
        batch?: number | null;
        batches?: number | null;
        device?: string | null;
        gpu_mem?: string | null;
        lr?: number | null;
        box_loss?: number | null;
        cls_loss?: number | null;
        dfl_loss?: number | null;
        map50?: number | null;
        map50_95?: number | null;
    } | null;
}

export interface JobTaskRun {
    id: string;
    stage: string;
    box_id?: number | null;
    profile_id?: string | null;
    status: string;
    attempt?: number;
    error_code?: string | null;
    result_json?: Record<string, unknown> | null;
    attempt_events?: JobTaskAttemptEvent[] | null;
    created_at?: string;
    updated_at?: string;
}

export interface JobTaskAttemptEvent {
    id: number;
    attempt: number;
    tool_name: string;
    model_id?: string | null;
    prompt_version?: string | null;
    params_snapshot?: Record<string, unknown> | null;
    token_usage?: Record<string, unknown> | null;
    finish_reason?: string | null;
    latency_ms?: number | null;
    error_detail?: string | null;
    created_at?: string;
}

export interface JobTasksResponse {
    workflowRunId: string | null;
    tasks: JobTaskRun[];
}

export async function fetchJobs(): Promise<Job[]> {
    const res = await apiFetch(`${API_BASE}/api/jobs`, {
        headers: {
            Accept: "application/json",
        },
    });

    return res.json() as Promise<Job[]>;
}

export async function clearFinishedJobs(): Promise<void> {
    await apiFetch(`${API_BASE}/api/jobs/finished`, {
        method: "DELETE",
        headers: {
            Accept: "application/json",
        },
    });
}

export async function cancelJob(jobId: string): Promise<void> {
    await apiFetch(`${API_BASE}/api/jobs/${jobId}/cancel`, {
        method: "POST",
        headers: {
            Accept: "application/json",
        },
    });
}

export async function resumeJob(jobId: string): Promise<CreateJobResponse> {
    const res = await apiFetch(`${API_BASE}/api/jobs/${jobId}/resume`, {
        method: "POST",
        headers: {
            Accept: "application/json",
        },
    });
    return res.json() as Promise<CreateJobResponse>;
}

export async function deleteJob(jobId: string): Promise<void> {
    await apiFetch(`${API_BASE}/api/jobs/${jobId}`, {
        method: "DELETE",
        headers: {
            Accept: "application/json",
        },
    });
}

export async function fetchJobTasks(jobId: string): Promise<JobTasksResponse> {
    const res = await apiFetch(`${API_BASE}/api/jobs/${jobId}/tasks`, {
        headers: {
            Accept: "application/json",
        },
    });
    return res.json() as Promise<JobTasksResponse>;
}

export async function fetchJobCapabilities(): Promise<JobCapabilities> {
    const res = await apiFetch(`${API_BASE}/api/jobs/capabilities`, {
        headers: {
            Accept: "application/json",
        },
    });
    return res.json() as Promise<JobCapabilities>;
}
