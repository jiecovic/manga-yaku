// src/hooks/useTrainingDatasets.ts
import { useCallback, useEffect, useState } from 'react';

import { fetchTrainingDatasets } from '../api';
import type { TrainingDataset } from '../types';

interface UseTrainingDatasetsResult {
  datasets: TrainingDataset[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export function useTrainingDatasets(): UseTrainingDatasetsResult {
  const [datasets, setDatasets] = useState<TrainingDataset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchTrainingDatasets();
      setDatasets(data);
      setError(null);
    } catch (err) {
      console.error('Failed to load training datasets', err);
      setError('Failed to load training datasets');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return {
    datasets,
    loading,
    error,
    refresh: load,
  };
}
