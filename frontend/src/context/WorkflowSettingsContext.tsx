// src/context/WorkflowSettingsContext.tsx
import type { ReactNode } from 'react';
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type {
  OcrProfileSettingsResponse,
  UpdateOcrProfileSettingsRequest,
} from '../api/ocrProfileSettings';
import { fetchOcrProfileSettings, updateOcrProfileSettings } from '../api/ocrProfileSettings';
import type {
  PageTranslationSettingsResponse,
  UpdatePageTranslationSettingsRequest,
} from '../api/pageTranslationSettings';
import {
  fetchPageTranslationSettings,
  updatePageTranslationSettings,
} from '../api/pageTranslationSettings';
import type {
  TranslationProfileSettingsResponse,
  UpdateTranslationProfileSettingsRequest,
} from '../api/translationProfileSettings';
import {
  fetchTranslationProfileSettings,
  updateTranslationProfileSettings,
} from '../api/translationProfileSettings';

interface WorkflowSettingsContextValue {
  pageTranslation: PageTranslationSettingsResponse | null;
  ocrProfiles: OcrProfileSettingsResponse | null;
  translationProfiles: TranslationProfileSettingsResponse | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  savePageTranslation: (values: UpdatePageTranslationSettingsRequest) => Promise<void>;
  saveOcrProfiles: (payload: UpdateOcrProfileSettingsRequest) => Promise<void>;
  saveTranslationProfiles: (payload: UpdateTranslationProfileSettingsRequest) => Promise<void>;
}

const WorkflowSettingsContext = createContext<WorkflowSettingsContextValue | null>(null);

export function WorkflowSettingsProvider({ children }: { children: ReactNode }) {
  const [pageTranslation, setPageTranslation] = useState<PageTranslationSettingsResponse | null>(
    null,
  );
  const [ocrProfiles, setOcrProfiles] = useState<OcrProfileSettingsResponse | null>(null);
  const [translationProfiles, setTranslationProfiles] =
    useState<TranslationProfileSettingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [pageTranslationRes, ocrRes, translationRes] = await Promise.all([
        fetchPageTranslationSettings(),
        fetchOcrProfileSettings(),
        fetchTranslationProfileSettings(),
      ]);
      setPageTranslation(pageTranslationRes);
      setOcrProfiles(ocrRes);
      setTranslationProfiles(translationRes);
    } catch (err) {
      console.error('Failed to load workflow settings', err);
      setError('Failed to load workflow settings.');
    } finally {
      setLoading(false);
    }
  }, []);

  const savePageTranslation = useCallback(async (values: UpdatePageTranslationSettingsRequest) => {
    setLoading(true);
    setError(null);
    try {
      const response = await updatePageTranslationSettings(values);
      setPageTranslation(response);
    } catch (err) {
      console.error('Failed to update workflow settings', err);
      setError('Failed to update workflow settings.');
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const saveOcrProfiles = useCallback(async (payload: UpdateOcrProfileSettingsRequest) => {
    setLoading(true);
    setError(null);
    try {
      const response = await updateOcrProfileSettings(payload);
      setOcrProfiles(response);
    } catch (err) {
      console.error('Failed to update OCR profile settings', err);
      setError('Failed to update OCR profile settings.');
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const saveTranslationProfiles = useCallback(
    async (payload: UpdateTranslationProfileSettingsRequest) => {
      setLoading(true);
      setError(null);
      try {
        const response = await updateTranslationProfileSettings(payload);
        setTranslationProfiles(response);
      } catch (err) {
        console.error('Failed to update translation profile settings', err);
        setError('Failed to update translation profile settings.');
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const value = useMemo(
    () => ({
      pageTranslation,
      ocrProfiles,
      translationProfiles,
      loading,
      error,
      refresh: load,
      savePageTranslation,
      saveOcrProfiles,
      saveTranslationProfiles,
    }),
    [
      pageTranslation,
      ocrProfiles,
      translationProfiles,
      loading,
      error,
      load,
      savePageTranslation,
      saveOcrProfiles,
      saveTranslationProfiles,
    ],
  );

  return (
    <WorkflowSettingsContext.Provider value={value}>{children}</WorkflowSettingsContext.Provider>
  );
}

export function useWorkflowSettings() {
  const ctx = useContext(WorkflowSettingsContext);
  if (!ctx) {
    throw new Error('useWorkflowSettings must be used within WorkflowSettingsProvider');
  }
  return ctx;
}
