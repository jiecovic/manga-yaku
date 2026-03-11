// src/context/HealthContext.tsx
import type { ReactNode } from 'react';
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ApiErrorDetail } from '../api/client';
import { appConfig } from '../config';

type HealthStatus = 'unknown' | 'ok' | 'degraded' | 'down';
type DatabaseStatus = 'unknown' | 'ok' | 'unavailable';

interface HealthState {
  status: HealthStatus;
  database: DatabaseStatus;
  lastError: string | null;
  lastChecked: number | null;
}

interface HealthContextValue extends HealthState {
  apiBase: string;
  checkHealth: () => Promise<void>;
  clearLastError: () => void;
}

const HealthContext = createContext<HealthContextValue | null>(null);

export function HealthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<HealthState>({
    status: 'unknown',
    database: 'unknown',
    lastError: null,
    lastChecked: null,
  });

  const checkHealth = useCallback(async () => {
    try {
      const res = await fetch(`${appConfig.apiBase}/api/health`, {
        headers: { Accept: 'application/json' },
      });
      const payload = await res.json().catch(() => ({}));
      if (res.ok) {
        const nextDb =
          payload.database === 'unavailable'
            ? 'unavailable'
            : payload.database === 'ok'
              ? 'ok'
              : 'unknown';
        setState((prev) => ({
          ...prev,
          status: 'ok',
          database: nextDb === 'unknown' ? 'ok' : nextDb,
          lastChecked: Date.now(),
          lastError: null,
        }));
        return;
      }

      const resolvedStatus =
        payload.status === 'ok' ? 'ok' : payload.status === 'degraded' ? 'degraded' : 'unknown';
      setState((prev) => ({
        ...prev,
        status: resolvedStatus === 'unknown' ? 'degraded' : resolvedStatus,
        database:
          payload.database === 'unavailable'
            ? 'unavailable'
            : payload.database === 'ok'
              ? 'ok'
              : 'unknown',
        lastChecked: Date.now(),
      }));
    } catch {
      setState((prev) => ({
        ...prev,
        status: 'down',
        database: 'unknown',
        lastChecked: Date.now(),
      }));
    }
  }, []);

  const clearLastError = useCallback(() => {
    setState((prev) => ({ ...prev, lastError: null }));
  }, []);

  useEffect(() => {
    let alive = true;
    const run = async () => {
      if (!alive) return;
      await checkHealth();
      if (!alive) return;
      window.setTimeout(run, 15000);
    };
    void run();
    return () => {
      alive = false;
    };
  }, [checkHealth]);

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<ApiErrorDetail>).detail;
      if (!detail || !detail.message) {
        return;
      }
      setState((prev) => ({
        ...prev,
        lastError: detail.message,
      }));
    };
    window.addEventListener('api:error', handler as EventListener);
    return () => window.removeEventListener('api:error', handler as EventListener);
  }, []);

  const value = useMemo(
    () => ({
      ...state,
      apiBase: appConfig.apiBase,
      checkHealth,
      clearLastError,
    }),
    [state, checkHealth, clearLastError],
  );

  return <HealthContext.Provider value={value}>{children}</HealthContext.Provider>;
}

export function useHealth(): HealthContextValue {
  const ctx = useContext(HealthContext);
  if (!ctx) {
    throw new Error('useHealth must be used within HealthProvider');
  }
  return ctx;
}
