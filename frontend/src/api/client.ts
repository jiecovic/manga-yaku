// src/api/client.ts
import { appConfig } from '../config';

export const API_BASE = appConfig.apiBase;

export interface ApiErrorDetail {
  message: string;
  status?: number;
  code?: string;
  url?: string;
  rawMessage?: string;
}

export function emitApiError(detail: ApiErrorDetail) {
  if (typeof window === 'undefined') {
    return;
  }
  window.dispatchEvent(new CustomEvent('api:error', { detail }));
}

export function safeStringify(value: unknown): string {
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function truncate(value: string, max = 240): string {
  if (value.length <= max) {
    return value;
  }
  return `${value.slice(0, max - 3)}...`;
}

export async function extractErrorMessage(
  res: Response,
): Promise<{ message: string; code?: string }> {
  const text = await res.text().catch(() => '');
  if (!text) {
    return { message: `${res.status} ${res.statusText}` };
  }
  try {
    const parsed = JSON.parse(text) as {
      detail?: unknown;
      error?: { message?: unknown; code?: unknown };
    };
    const code = parsed?.error?.code ? String(parsed.error.code) : undefined;
    if (parsed?.error?.message) {
      return { message: String(parsed.error.message), code };
    }
    if (parsed?.detail) {
      const detail =
        typeof parsed.detail === 'string' ? parsed.detail : safeStringify(parsed.detail);
      return { message: detail, code };
    }
  } catch {
    // fall through to raw text
  }
  return { message: text };
}

export async function readApiErrorDetail(res: Response): Promise<ApiErrorDetail> {
  const { message, code } = await extractErrorMessage(res);
  const rawMessage = truncate(message);
  return {
    message: `HTTP ${res.status}: ${rawMessage}`,
    rawMessage,
    status: res.status,
    code,
    url: res.url,
  };
}

export async function apiFetch(url: string, options?: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(url, options);
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Network error';
    emitApiError({ message: truncate(message), url });
    throw err;
  }

  if (!res.ok) {
    const detail = await readApiErrorDetail(res);
    emitApiError(detail);
    throw new Error(detail.message);
  }

  return res;
}

export async function getJson<T>(url: string): Promise<T> {
  const res = await apiFetch(url, {
    headers: {
      Accept: 'application/json',
    },
  });

  return res.json() as Promise<T>;
}
