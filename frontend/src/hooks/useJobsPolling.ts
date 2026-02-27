// src/hooks/useJobsPolling.ts
import { useEffect, useRef, useState } from "react";
import {
    DEFAULT_JOB_CAPABILITIES,
    fetchJobs,
    fetchJobCapabilities,
    clearFinishedJobs,
    cancelJob,
    resumeJob as apiResumeJob,
    deleteJob,
    type Job,
    type JobCapabilities,
} from "../api";
import { appConfig } from "../config";

interface UseJobsPollingResult {
    jobs: Job[];
    jobCapabilities: JobCapabilities;
    jobCapabilitiesError: string | null;
    jobsError: string | null;
    jobsLoading: boolean;
    clearFinished: () => Promise<void>;
    cancelJob: (jobId: string) => Promise<void>;
    resumeJob: (jobId: string) => Promise<void>;
    deleteJob: (jobId: string) => Promise<void>;
}

export function useJobsPolling(intervalMs: number = 2000): UseJobsPollingResult {
    const [jobs, setJobs] = useState<Job[]>([]);
    const [jobCapabilities, setJobCapabilities] = useState<JobCapabilities>(
        DEFAULT_JOB_CAPABILITIES,
    );
    const [jobCapabilitiesError, setJobCapabilitiesError] = useState<string | null>(
        null,
    );
    const [jobsError, setJobsError] = useState<string | null>(null);
    const [jobsLoading, setJobsLoading] = useState(false);
    const hasDataRef = useRef(false);

    useEffect(() => {
        let cancelled = false;
        let timerId: number | null = null;
        let eventSource: EventSource | null = null;
        let reconnectTimer: number | null = null;
        let reconnectDelay = 2000;
        hasDataRef.current = false;

        const pollOnce = async () => {
            try {
                if (!cancelled) {
                    setJobsLoading((prev) => prev || !hasDataRef.current);
                }
                const js = await fetchJobs();
                if (cancelled) return;
                setJobs(js);
                setJobsError(null);
                hasDataRef.current = js.length > 0;
            } catch (err) {
                if (cancelled) return;
                console.error("Failed to fetch jobs", err);
                setJobsError("Failed to fetch jobs");
            } finally {
                if (!cancelled) {
                    setJobsLoading(false);
                }
            }
        };

        const loadCapabilities = async () => {
            try {
                const data = await fetchJobCapabilities();
                if (cancelled) return;
                setJobCapabilities(data);
                setJobCapabilitiesError(null);
            } catch (err) {
                if (cancelled) return;
                console.error("Failed to fetch job capabilities", err);
                setJobCapabilitiesError("Failed to fetch job capabilities");
            }
        };

        const startPolling = () => {
            void pollOnce();
            timerId = window.setInterval(() => {
                void pollOnce();
            }, intervalMs);
        };

        const stopPolling = () => {
            if (timerId !== null) {
                window.clearInterval(timerId);
                timerId = null;
            }
        };

        const stopStream = () => {
            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }
        };

        const scheduleReconnect = () => {
            if (reconnectTimer !== null) {
                window.clearTimeout(reconnectTimer);
            }
            reconnectTimer = window.setTimeout(() => {
                reconnectTimer = null;
                if (!cancelled) {
                    startStream();
                }
            }, reconnectDelay);
            reconnectDelay = Math.min(reconnectDelay * 2, 15000);
        };

        const startStream = () => {
            setJobsLoading((prev) => prev || !hasDataRef.current);
            const url = `${appConfig.apiBase}/api/jobs/stream`;
            eventSource = new EventSource(url);

            eventSource.onmessage = (event) => {
                if (cancelled) return;
                try {
                    const payload = JSON.parse(event.data);
                    if (Array.isArray(payload.jobs)) {
                        setJobs(payload.jobs);
                        setJobsError(null);
                        hasDataRef.current = payload.jobs.length > 0;
                    }
                } catch (err) {
                    console.error("Failed to parse jobs stream", err);
                } finally {
                    if (!cancelled) {
                        setJobsLoading(false);
                    }
                }
            };

            eventSource.onerror = () => {
                if (cancelled) return;
                stopStream();
                setJobsError("Jobs stream disconnected");
                scheduleReconnect();
            };
        };

        if (typeof window !== "undefined" && "EventSource" in window) {
            void loadCapabilities();
            startPolling();
            startStream();
        } else {
            void loadCapabilities();
            startPolling();
        }

        return () => {
            cancelled = true;
            stopStream();
            if (reconnectTimer !== null) {
                window.clearTimeout(reconnectTimer);
                reconnectTimer = null;
            }
            stopPolling();
        };
    }, [intervalMs]);

    const clearFinished = async () => {
        await clearFinishedJobs();

        // optimistic local update so UI feels instant
        setJobs((prev) =>
            prev.filter(
                (j) =>
                    j.status !== "finished" &&
                    j.status !== "failed" &&
                    j.status !== "canceled",
            ),
        );
    };

    const cancelJobById = async (jobId: string) => {
        await cancelJob(jobId);
        setJobs((prev) =>
            prev.map((job) =>
                job.id === jobId
                    ? {
                          ...job,
                          status: "canceled",
                          message: job.message ?? "Canceled",
                      }
                    : job,
            ),
        );
    };

    const resumeJobById = async (jobId: string) => {
        await apiResumeJob(jobId);
    };

    const deleteJobById = async (jobId: string) => {
        await deleteJob(jobId);
        setJobs((prev) => prev.filter((job) => job.id !== jobId));
    };

    return {
        jobs,
        jobCapabilities,
        jobCapabilitiesError,
        jobsError,
        jobsLoading,
        clearFinished,
        cancelJob: cancelJobById,
        resumeJob: resumeJobById,
        deleteJob: deleteJobById,
    };
}
