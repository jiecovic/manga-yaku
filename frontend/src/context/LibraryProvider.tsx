// src/context/LibraryProvider.tsx
import type { ReactNode } from 'react';
import { useLibraryState } from '../hooks/useLibraryState';
import { LibraryContext } from './LibraryContext';

export function LibraryProvider({ children }: { children: ReactNode }) {
  const value = useLibraryState();

  return <LibraryContext.Provider value={value}>{children}</LibraryContext.Provider>;
}
