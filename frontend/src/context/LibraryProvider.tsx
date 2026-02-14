// src/context/LibraryProvider.tsx
import type { ReactNode } from "react";
import { LibraryContext } from "./LibraryContext";
import { useLibraryState } from "../hooks/useLibraryState";

export function LibraryProvider({ children }: { children: ReactNode }) {
    const value = useLibraryState();

    return (
        <LibraryContext.Provider value={value}>
            {children}
        </LibraryContext.Provider>
    );
}
