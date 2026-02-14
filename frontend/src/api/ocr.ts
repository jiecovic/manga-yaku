// src/api/ocr.ts
import type { OcrProvider } from "../types";
import type { CreateJobResponse } from "./jobs";
import { API_BASE, apiFetch, getJson } from "./client";

export interface CreateOcrBoxJobRequest {
    profileId: string;
    volumeId: string;
    filename: string;
    x: number;
    y: number;
    width: number;
    height: number;
    boxId?: number;
    boxOrder?: number;
}

export interface CreateOcrPageJobRequest {
    profileId: string;
    volumeId: string;
    filename: string;
    skipExisting?: boolean;
}

export function fetchOcrProviders(): Promise<OcrProvider[]> {
    return getJson<OcrProvider[]>(`${API_BASE}/api/ocr/providers`);
}

export async function createOcrBoxJob(
    payload: CreateOcrBoxJobRequest,
): Promise<CreateJobResponse> {
    const res = await apiFetch(`${API_BASE}/api/jobs/ocr_box`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
        },
        body: JSON.stringify(payload),
    });

    return res.json() as Promise<CreateJobResponse>;
}

export async function createOcrPageJob(
    payload: CreateOcrPageJobRequest,
): Promise<CreateJobResponse> {
    const res = await apiFetch(`${API_BASE}/api/jobs/ocr_page`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
        },
        body: JSON.stringify(payload),
    });

    return res.json() as Promise<CreateJobResponse>;
}
