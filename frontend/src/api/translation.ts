// src/api/translation.ts
import type { TranslationProvider } from "../types";
import type { CreateJobResponse } from "./jobs";
import { API_BASE, apiFetch, getJson } from "./client";

export interface CreateTranslateBoxJobRequest {
    profileId: string;
    volumeId: string;
    filename: string;
    boxId: number;
    usePageContext: boolean;
    boxOrder?: number;
}

export interface CreateTranslatePageJobRequest {
    profileId: string;
    volumeId: string;
    filename: string;
    usePageContext: boolean;
    skipExisting?: boolean;
}

export interface CreateAgentTranslatePageJobRequest {
    volumeId: string;
    filename: string;
    detectionProfileId?: string | null;
    ocrProfiles?: string[] | null;
    sourceLanguage?: string | null;
    targetLanguage?: string | null;
    modelId?: string | null;
}

export function fetchTranslationProviders(): Promise<TranslationProvider[]> {
    return getJson<TranslationProvider[]>(
        `${API_BASE}/api/translation/providers`,
    );
}

export async function createTranslateBoxJob(
    payload: CreateTranslateBoxJobRequest,
): Promise<CreateJobResponse> {
    const res = await apiFetch(`${API_BASE}/api/jobs/translate_box`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
        },
        body: JSON.stringify(payload),
    });

    return res.json() as Promise<CreateJobResponse>;
}

export async function createTranslatePageJob(
    payload: CreateTranslatePageJobRequest,
): Promise<CreateJobResponse> {
    const res = await apiFetch(`${API_BASE}/api/jobs/translate_page`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
        },
        body: JSON.stringify(payload),
    });

    return res.json() as Promise<CreateJobResponse>;
}

export async function createAgentTranslatePageJob(
    payload: CreateAgentTranslatePageJobRequest,
): Promise<CreateJobResponse> {
    const res = await apiFetch(`${API_BASE}/api/jobs/agent_translate_page`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
        },
        body: JSON.stringify(payload),
    });

    return res.json() as Promise<CreateJobResponse>;
}
