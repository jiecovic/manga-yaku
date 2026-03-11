// src/api/memory.ts
import { API_BASE, apiFetch, getJson } from './client';

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
  manualNotes: string;
  pageSummary: string;
  imageSummary: string;
  characters: CharacterMemory[];
  openThreads: string[];
  glossary: GlossaryEntry[];
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface ClearVolumeDerivedDataDetails {
  pagesTouched: number;
  boxesDeleted: number;
  detectionRunsDeleted: number;
  pageContextSnapshotsDeleted: number;
  pageNotesCleared: number;
  volumeContextDeleted: number;
  agentSessionsDeleted: number;
  workflowRunsDeleted: number;
  taskRunsDeleted: number;
  taskAttemptEventsDeleted: number;
  llmCallLogsDeleted: number;
  llmPayloadFilesDeleted: number;
  pageTranslationDebugFilesDeleted: number;
}

export interface ClearVolumeDerivedDataResponse {
  cleared: boolean;
  details: ClearVolumeDerivedDataDetails;
}

export async function fetchVolumeMemory(volumeId: string): Promise<VolumeMemory> {
  return getJson<VolumeMemory>(`${API_BASE}/api/volumes/${encodeURIComponent(volumeId)}/memory`);
}

export async function fetchPageMemory(volumeId: string, filename: string): Promise<PageMemory> {
  return getJson<PageMemory>(
    `${API_BASE}/api/volumes/${encodeURIComponent(
      volumeId,
    )}/pages/${encodeURIComponent(filename)}/memory`,
  );
}

export async function clearVolumeMemory(volumeId: string): Promise<void> {
  await apiFetch(`${API_BASE}/api/volumes/${encodeURIComponent(volumeId)}/memory`, {
    method: 'DELETE',
    headers: {
      Accept: 'application/json',
    },
  });
}

export async function clearPageMemory(volumeId: string, filename: string): Promise<void> {
  await apiFetch(
    `${API_BASE}/api/volumes/${encodeURIComponent(
      volumeId,
    )}/pages/${encodeURIComponent(filename)}/memory`,
    {
      method: 'DELETE',
      headers: {
        Accept: 'application/json',
      },
    },
  );
}

export async function clearVolumeDerivedData(
  volumeId: string,
): Promise<ClearVolumeDerivedDataResponse> {
  const res = await apiFetch(
    `${API_BASE}/api/volumes/${encodeURIComponent(volumeId)}/derived-data`,
    {
      method: 'DELETE',
      headers: {
        Accept: 'application/json',
      },
    },
  );
  return res.json() as Promise<ClearVolumeDerivedDataResponse>;
}
