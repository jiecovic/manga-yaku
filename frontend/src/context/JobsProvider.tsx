// src/context/JobsProvider.tsx
import type { ReactNode } from "react";
import { useJobsPolling } from "../hooks/useJobsPolling";
import { JobsContext } from "./JobsContext";

export function JobsProvider({children}: {children: ReactNode}) {
    // useJobsPolling returns the same shape as JobsContextValue
    const value = useJobsPolling();

    return (
        <JobsContext.Provider value={value}>
            {children}
        </JobsContext.Provider>
    );
}
