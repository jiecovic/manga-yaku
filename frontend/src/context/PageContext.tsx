// src/context/PageContext.tsx
/* eslint react-refresh/only-export-components: "off" */

import {createContext, type ReactNode} from "react";

export interface PageContextValue {
    volumeId: string;
    filename: string;
}

export const PageContext = createContext<PageContextValue | undefined>(
    undefined,
);

interface PageProviderProps {
    volumeId: string;
    filename: string;
    children: ReactNode;
}

export function PageProvider({volumeId, filename, children}: PageProviderProps) {
    const value: PageContextValue = {volumeId, filename};

    return (
        <PageContext.Provider value={value}>
            {children}
        </PageContext.Provider>
    );
}
