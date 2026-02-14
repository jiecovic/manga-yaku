// src/api/jobs.ts
import { API_BASE, apiFetch } from "./client";

export interface CreateJobResponse {
    jobId: string;
}

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

export async function deleteJob(jobId: string): Promise<void> {
    await apiFetch(`${API_BASE}/api/jobs/${jobId}`, {
        method: "DELETE",
        headers: {
            Accept: "application/json",
        },
    });
}
