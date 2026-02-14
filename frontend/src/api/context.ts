// src/api/context.ts
import { API_BASE, apiFetch, getJson } from "./client";

interface ContextResponse {
    context: string;
}

export async function fetchPageContext(
    volumeId: string,
    filename: string,
): Promise<string> {
    const data = await getJson<ContextResponse>(
        `${API_BASE}/api/volumes/${encodeURIComponent(
            volumeId,
        )}/pages/${encodeURIComponent(filename)}/context`,
    );
    return data.context ?? "";
}

export async function savePageContext(
    volumeId: string,
    filename: string,
    context: string,
): Promise<void> {
    await apiFetch(
        `${API_BASE}/api/volumes/${encodeURIComponent(
            volumeId,
        )}/pages/${encodeURIComponent(filename)}/context`,
        {
            method: "PUT",
            headers: {
                "Content-Type": "application/json",
                Accept: "application/json",
            },
            body: JSON.stringify({ context }),
        },
    );
}
