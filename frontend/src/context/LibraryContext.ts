// src/context/LibraryContext.ts
import { createContext } from 'react';
import type { useLibraryState } from '../hooks/useLibraryState';

export type LibraryContextValue = ReturnType<typeof useLibraryState>;

export const LibraryContext = createContext<LibraryContextValue | undefined>(undefined);
