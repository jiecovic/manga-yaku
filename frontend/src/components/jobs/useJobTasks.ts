import { useCallback, useEffect, useRef, useState } from 'react';

import { fetchJobTasks, type Job, type JobTaskRun } from '../../api';
import { areTasksEqual, isImplicitlyExpanded, isJobActive, isWorkflowJob } from './jobTaskUtils';

export type JobTasksState = {
  loading: boolean;
  error: string | null;
  tasks: JobTaskRun[];
};

export function useJobTasks(sortedJobs: Job[]) {
  const [expandedJobs, setExpandedJobs] = useState<Record<string, boolean>>({});
  const [jobTasks, setJobTasks] = useState<Record<string, JobTasksState>>({});
  const jobTasksRef = useRef<Record<string, JobTasksState>>({});
  const inflightLoads = useRef<Set<string>>(new Set());

  useEffect(() => {
    jobTasksRef.current = jobTasks;
  }, [jobTasks]);

  const loadTasks = useCallback(async (jobId: string, options?: { silent?: boolean }) => {
    const silent = Boolean(options?.silent);
    if (inflightLoads.current.has(jobId)) {
      return;
    }
    inflightLoads.current.add(jobId);
    const currentBefore = jobTasksRef.current[jobId];
    if (!silent || !currentBefore || currentBefore.tasks.length === 0) {
      setJobTasks((prev) => ({
        ...prev,
        [jobId]: {
          loading: true,
          error: null,
          tasks: prev[jobId]?.tasks ?? [],
        },
      }));
    }
    try {
      const res = await fetchJobTasks(jobId);
      const tasks = Array.isArray(res.tasks) ? res.tasks : [];
      const current = jobTasksRef.current[jobId];
      if (current && current.error === null && areTasksEqual(current.tasks, tasks)) {
        if (current.loading) {
          setJobTasks((prev) => ({
            ...prev,
            [jobId]: {
              ...prev[jobId],
              loading: false,
            },
          }));
        }
        return;
      }
      setJobTasks((prev) => ({
        ...prev,
        [jobId]: {
          loading: false,
          error: null,
          tasks,
        },
      }));
    } catch (err) {
      console.error('Failed to fetch job tasks', err);
      setJobTasks((prev) => ({
        ...prev,
        [jobId]: {
          loading: false,
          error: 'Failed to load tasks',
          tasks: prev[jobId]?.tasks ?? [],
        },
      }));
    } finally {
      inflightLoads.current.delete(jobId);
    }
  }, []);

  useEffect(() => {
    const liveJobIds = new Set(sortedJobs.map((job) => job.id));
    setExpandedJobs((prev) => {
      const next: Record<string, boolean> = {};
      for (const [jobId, isExpanded] of Object.entries(prev)) {
        if (isExpanded && liveJobIds.has(jobId)) {
          next[jobId] = true;
        }
      }
      return next;
    });
    setJobTasks((prev) => {
      const next: Record<string, JobTasksState> = {};
      for (const [jobId, data] of Object.entries(prev)) {
        if (liveJobIds.has(jobId)) {
          next[jobId] = data;
        }
      }
      return next;
    });
  }, [sortedJobs]);

  useEffect(() => {
    const shouldRefresh = sortedJobs.filter(
      (job) =>
        isWorkflowJob(job) &&
        (Boolean(expandedJobs[job.id]) || isImplicitlyExpanded(job) || isJobActive(job)),
    );
    if (shouldRefresh.length === 0) {
      return;
    }

    for (const job of shouldRefresh) {
      const existing = jobTasksRef.current[job.id];
      const hasCached = Boolean(existing && existing.tasks.length > 0);
      void loadTasks(job.id, { silent: hasCached });
    }

    const timer = window.setInterval(() => {
      for (const job of shouldRefresh) {
        void loadTasks(job.id, { silent: true });
      }
    }, 2000);

    return () => window.clearInterval(timer);
  }, [expandedJobs, loadTasks, sortedJobs]);

  return {
    expandedJobs,
    setExpandedJobs,
    jobTasks,
  };
}
