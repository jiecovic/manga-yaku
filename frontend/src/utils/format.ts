// src/utils/format.ts
export const formatFloat = (value: number | null | undefined, digits = 4): string => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—';
  }
  const abs = Math.abs(value);
  if (abs > 0 && (abs < 0.001 || abs >= 1000)) {
    return value.toExponential(2);
  }
  const fixed = value.toFixed(digits);
  return fixed.replace(/\.?0+$/, '');
};
