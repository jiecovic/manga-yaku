// src/api/boxes.ts
import type { Box, BoxDetectionProfile } from "../types";
import type { CreateJobResponse } from "./jobs";
import { API_BASE, apiFetch, emitApiError, getJson, readApiErrorDetail } from "./client";

const BASE = API_BASE;

// Only boxes live here. pageContext is handled via other endpoints.
export async function loadPageState(
    volumeId: string,
    filename: string,
): Promise<Box[]> {
    const res = await fetch(
        `${BASE}/api/boxes/${encodeURIComponent(volumeId)}/${encodeURIComponent(
            filename,
        )}`,
        {
            headers: {
                Accept: "application/json",
            },
        },
    );

    if (!res.ok) {
        if (res.status === 404) {
            return [];
        }
        const detail = await readApiErrorDetail(res);
        emitApiError(detail);
        throw new Error(`Failed to load page state: ${detail.rawMessage ?? detail.message}`);
    }

    const data = await res.json();
    return (data.boxes as Box[]) ?? [];
}

export async function savePageState(
    volumeId: string,
    filename: string,
    boxes: Box[],
    options?: { keepalive?: boolean },
): Promise<void> {
    await apiFetch(
        `${BASE}/api/boxes/${encodeURIComponent(volumeId)}/${encodeURIComponent(
            filename,
        )}`,
        {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            keepalive: options?.keepalive ?? false,
            body: JSON.stringify({ boxes }),
        },
    );
}

export async function patchBoxText(
    volumeId: string,
    filename: string,
    boxId: number,
    payload: { text?: string | null; translation?: string | null },
    options?: { keepalive?: boolean },
): Promise<void> {
    await apiFetch(
        `${BASE}/api/boxes/${encodeURIComponent(volumeId)}/${encodeURIComponent(
            filename,
        )}/${boxId}`,
        {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            keepalive: options?.keepalive ?? false,
            body: JSON.stringify(payload),
        },
    );
}


export async function autoDetectBoxes(
    volumeId: string,
    filename: string,
    profileId?: string,
    task?: string,
): Promise<Box[]> {
    const params = new URLSearchParams();
    if (profileId) {
        params.set("profile_id", profileId);
    }
    if (task) {
        params.set("task", task);
    }
    const query = params.toString();
    const res = await apiFetch(
        `${BASE}/api/pages/${encodeURIComponent(volumeId)}/${encodeURIComponent(
            filename,
        )}/auto-detect${query ? `?${query}` : ""}`,
        {
            method: "POST",
        },
    );

    const data = await res.json();
    return (data.boxes as Box[]) ?? [];
}

export interface CreateBoxDetectionJobRequest {
    volumeId: string;
    filename: string;
    profileId?: string;
    task?: string;
    replaceExisting?: boolean;
}

export async function createBoxDetectionJob(
    payload: CreateBoxDetectionJobRequest,
): Promise<CreateJobResponse> {
    const res = await apiFetch(`${API_BASE}/api/jobs/box_detection`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
        },
        body: JSON.stringify(payload),
    });

    return res.json() as Promise<CreateJobResponse>;
}

export function fetchBoxDetectionProfiles(): Promise<BoxDetectionProfile[]> {
    return getJson<BoxDetectionProfile[]>(`${API_BASE}/api/box-detection/profiles`);
}
