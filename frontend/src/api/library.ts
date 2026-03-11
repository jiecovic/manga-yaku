// src/api/library.ts
import type { MissingPage, MissingVolume, PageInfo, Volume } from '../types';
import { API_BASE, apiFetch, emitApiError, getJson, readApiErrorDetail } from './client';

export function fetchVolumes(): Promise<Volume[]> {
  return getJson<Volume[]>(`${API_BASE}/api/volumes`);
}

export function fetchPages(volumeId: string): Promise<PageInfo[]> {
  return getJson<PageInfo[]>(`${API_BASE}/api/volumes/${encodeURIComponent(volumeId)}/pages`);
}

export async function deleteVolumePage(
  volumeId: string,
  filename: string,
): Promise<{ deleted: boolean; missingFile?: boolean }> {
  const res = await fetch(
    `${API_BASE}/api/volumes/${encodeURIComponent(volumeId)}/pages/${encodeURIComponent(filename)}`,
    {
      method: 'DELETE',
      headers: {
        Accept: 'application/json',
      },
    },
  );

  if (!res.ok) {
    const detail = await readApiErrorDetail(res);
    emitApiError(detail);
    const message = detail.rawMessage ?? detail.message;
    throw new Error(`Failed to delete page: ${message}`);
  }

  return res.json() as Promise<{ deleted: boolean; missingFile?: boolean }>;
}

export function absolutizeImageUrl(page: PageInfo): string | null {
  if (page.missing || !page.imageUrl) {
    return null;
  }
  return `${API_BASE}/api${page.imageUrl}`;
}

export async function createVolume(name: string): Promise<Volume> {
  const res = await fetch(`${API_BASE}/api/volumes`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ name }),
  });

  if (!res.ok) {
    const detail = await readApiErrorDetail(res);
    emitApiError(detail);
    const message = detail.rawMessage ?? detail.message;
    throw new Error(`Failed to create volume: ${message}`);
  }

  return res.json() as Promise<Volume>;
}

export async function uploadVolumePage(
  volumeId: string,
  file: File,
  opts?: {
    insertBefore?: string;
    insertAfter?: string;
  },
): Promise<PageInfo> {
  const formData = new FormData();
  formData.append('file', file, file.name || 'clipboard.png');

  const params = new URLSearchParams();
  if (opts?.insertBefore) {
    params.set('insert_before', opts.insertBefore);
  }
  if (opts?.insertAfter) {
    params.set('insert_after', opts.insertAfter);
  }
  const query = params.toString();

  const res = await fetch(
    `${API_BASE}/api/volumes/${encodeURIComponent(volumeId)}/pages/upload${
      query ? `?${query}` : ''
    }`,
    {
      method: 'POST',
      body: formData,
    },
  );

  if (!res.ok) {
    const detail = await readApiErrorDetail(res);
    emitApiError(detail);
    const message = detail.rawMessage ?? detail.message;
    throw new Error(`Failed to upload page: ${message}`);
  }

  return res.json() as Promise<PageInfo>;
}

export async function importVolumes(): Promise<{
  imported: number;
  ids: string[];
}> {
  const res = await apiFetch(`${API_BASE}/api/volumes/sync/import`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
    },
  });

  return res.json() as Promise<{ imported: number; ids: string[] }>;
}

export async function detectMissingVolumes(): Promise<MissingVolume[]> {
  return getJson<MissingVolume[]>(`${API_BASE}/api/volumes/sync/missing`);
}

export async function pruneMissingVolumes(ids: string[]): Promise<{ deleted: number }> {
  const res = await apiFetch(`${API_BASE}/api/volumes/sync/prune`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ ids }),
  });

  return res.json() as Promise<{ deleted: number }>;
}

export async function importPages(): Promise<{ imported: number }> {
  const res = await apiFetch(`${API_BASE}/api/volumes/sync/pages/import`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
    },
  });

  return res.json() as Promise<{ imported: number }>;
}

export async function detectMissingPages(): Promise<MissingPage[]> {
  return getJson<MissingPage[]>(`${API_BASE}/api/volumes/sync/pages/missing`);
}

export async function pruneMissingPages(pages: MissingPage[]): Promise<{ deleted: number }> {
  const res = await apiFetch(`${API_BASE}/api/volumes/sync/pages/prune`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ pages }),
  });

  return res.json() as Promise<{ deleted: number }>;
}
