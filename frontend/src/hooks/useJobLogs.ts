// src/hooks/useJobLogs.ts
import { useEffect, useState } from "react";
import { appConfig } from "../config";
import { isProgressLine } from "../utils/trainingLogs";

type LogStatus = "idle" | "connecting" | "connected" | "error";

interface JobLogsState {
    lines: string[];
    status: LogStatus;
    error: string | null;
}

interface JobLogsStateInternal extends JobLogsState {
    jobId: string | null;
}

export function useJobLogs(
    jobId: string | null,
    maxLines: number = 400,
): JobLogsState {
    const [state, setState] = useState<JobLogsStateInternal>(() => ({
        jobId,
        lines: [],
        status: jobId ? "connecting" : "idle",
        error: null,
    }));

    const fallbackState: JobLogsStateInternal =
        state.jobId === jobId
            ? state
            : {
                  jobId,
                  lines: [],
                  status: jobId ? "connecting" : "idle",
                  error: null,
              };

    useEffect(() => {
        if (!jobId) {
            return undefined;
        }

        let cancelled = false;
        const source = new EventSource(
            `${appConfig.apiBase}/api/jobs/${jobId}/logs/stream`,
        );

        source.onopen = () => {
            if (cancelled) return;
            setState((prev) => ({
                jobId,
                lines: prev.jobId === jobId ? prev.lines : [],
                status: "connected",
                error: null,
            }));
        };

        source.onmessage = (event) => {
            if (cancelled) return;
            if (!event.data) return;
            setState((prev) => {
                const baseLines = prev.jobId === jobId ? prev.lines : [];
                const next = baseLines.slice();
                const isProgress = isProgressLine(event.data);
                if (
                    isProgress &&
                    next.length > 0 &&
                    isProgressLine(next[next.length - 1])
                ) {
                    next[next.length - 1] = event.data;
                } else {
                    next.push(event.data);
                }
                const clipped =
                    next.length > maxLines
                        ? next.slice(next.length - maxLines)
                        : next;
                return {
                    jobId,
                    lines: clipped,
                    status: "connected",
                    error: null,
                };
            });
        };

        source.onerror = () => {
            if (cancelled) return;
            setState((prev) => ({
                jobId,
                lines: prev.jobId === jobId ? prev.lines : [],
                status: "error",
                error: "Log stream disconnected.",
            }));
        };

        return () => {
            cancelled = true;
            source.close();
        };
    }, [jobId, maxLines]);

    return {
        lines: fallbackState.lines,
        status: fallbackState.status,
        error: fallbackState.error,
    };
}
