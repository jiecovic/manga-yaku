// src/api/pageTranslationSettings.ts
import { API_BASE, apiFetch, getJson } from './client';

export interface PageTranslationSettingsValue {
  model_id: string;
  max_output_tokens?: number | null;
  reasoning_effort?: string | null;
  temperature?: number | null;
}

export interface PageTranslationSettingsResponse {
  value: PageTranslationSettingsValue;
  defaults: PageTranslationSettingsValue;
  options: Record<string, unknown>;
}

export type UpdatePageTranslationSettingsRequest = Partial<PageTranslationSettingsValue>;

export function fetchPageTranslationSettings(): Promise<PageTranslationSettingsResponse> {
  return getJson<PageTranslationSettingsResponse>(`${API_BASE}/api/settings/page-translation`);
}

export async function updatePageTranslationSettings(
  payload: UpdatePageTranslationSettingsRequest,
): Promise<PageTranslationSettingsResponse> {
  const res = await apiFetch(`${API_BASE}/api/settings/page-translation`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
  });

  return res.json() as Promise<PageTranslationSettingsResponse>;
}
