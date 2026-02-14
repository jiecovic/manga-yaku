// src/api/memory.ts
import { API_BASE, getJson } from "./client";

export interface CharacterMemory {
    name: string;
    gender: string;
    info: string;
}

export interface GlossaryEntry {
    term: string;
    translation: string;
    note: string;
}

export interface VolumeMemory {
    rollingSummary: string;
    activeCharacters: CharacterMemory[];
    openThreads: string[];
    glossary: GlossaryEntry[];
    lastPageIndex?: number | null;
    updatedAt?: string | null;
}

export interface PageMemory {
    pageSummary: string;
    imageSummary: string;
    characters: CharacterMemory[];
    openThreads: string[];
    glossary: GlossaryEntry[];
    createdAt?: string | null;
    updatedAt?: string | null;
}

export async function fetchVolumeMemory(volumeId: string): Promise<VolumeMemory> {
    return getJson<VolumeMemory>(
        `${API_BASE}/api/volumes/${encodeURIComponent(volumeId)}/memory`,
    );
}

export async function fetchPageMemory(
    volumeId: string,
    filename: string,
): Promise<PageMemory> {
    return getJson<PageMemory>(
        `${API_BASE}/api/volumes/${encodeURIComponent(
            volumeId,
        )}/pages/${encodeURIComponent(filename)}/memory`,
    );
}
