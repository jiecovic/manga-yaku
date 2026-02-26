// src/context/JobsContext.ts
import { createContext } from "react";
import type { Job } from "../api";

export interface JobsContextValue {
    jobs: Job[];
    jobsError: string | null;
    jobsLoading: boolean;
    clearFinished: () => Promise<void>;
    cancelJob: (jobId: string) => Promise<void>;
    resumeJob: (jobId: string) => Promise<void>;
    deleteJob: (jobId: string) => Promise<void>;
}

export const JobsContext = createContext<JobsContextValue | undefined>(
    undefined,
);
