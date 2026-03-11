// src/hooks/useTrainingSources.ts
import { useCallback, useEffect, useState } from 'react';

import { fetchTrainingSources } from '../api';
import type { TrainingSource } from '../types';

interface UseTrainingSourcesResult {
  sources: TrainingSource[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export function useTrainingSources(): UseTrainingSourcesResult {
  const [sources, setSources] = useState<TrainingSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchTrainingSources();
      setSources(data);
      setError(null);
    } catch (err) {
      console.error('Failed to load training sources', err);
      setError('Failed to load training sources');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return {
    sources,
    loading,
    error,
    refresh: load,
  };
}
