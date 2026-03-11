export const draftString = (draft: Record<string, unknown>, key: string): string => {
  const value = draft[key];
  return value === null || value === undefined ? '' : String(value);
};

export const draftBoolean = (
  draft: Record<string, unknown>,
  key: string,
  fallback = true,
): boolean => {
  const value = draft[key];
  if (typeof value === 'boolean') {
    return value;
  }
  return fallback;
};
