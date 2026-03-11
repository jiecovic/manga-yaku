// src/context/usePage.ts
import { useContext } from 'react';
import { PageContext, type PageContextValue } from './PageContext';

export function usePage(): PageContextValue {
  const ctx = useContext(PageContext);
  if (!ctx) {
    throw new Error('usePage must be used within a PageProvider');
  }
  return ctx;
}
