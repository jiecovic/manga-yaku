// src/utils/trainingLogs.ts
export interface LiveMetrics {
  epoch: number;
  total: number;
  gpuMem: string;
  boxLoss: number;
  clsLoss: number;
  dflLoss: number;
  instances: number;
  imageSize: number;
}

export const isProgressLine = (line: string): boolean => {
  if (!line) {
    return false;
  }
  if (!/^\s*\d+\/\d+/.test(line)) {
    if (/mAP50-95\):\s*\d+%/.test(line)) {
      return true;
    }
    if (/^Class\s+Images\s+Instances/.test(line) && /%/.test(line)) {
      return true;
    }
    return false;
  }
  if (line.includes('it/s') || line.includes('s/it')) {
    return true;
  }
  return /%\s/.test(line);
};

export const extractLiveMetrics = (lines: string[]): LiveMetrics | null => {
  const line = [...lines].reverse().find((item) => /^\s*\d+\/\d+/.test(item));
  if (!line) {
    return null;
  }
  const match = line.match(
    /^\s*(\d+)\/(\d+)\s+(\S+)\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+(\d+)\s+(\d+):/,
  );
  if (!match) {
    return null;
  }
  return {
    epoch: Number(match[1]),
    total: Number(match[2]),
    gpuMem: match[3],
    boxLoss: Number(match[4]),
    clsLoss: Number(match[5]),
    dflLoss: Number(match[6]),
    instances: Number(match[7]),
    imageSize: Number(match[8]),
  };
};

export const summarizeLogLines = (lines: string[], limit = 12): string[] => {
  if (!lines.length) {
    return [];
  }

  const isSummaryLine = (line: string): boolean => {
    if (!line) return false;
    if (line.includes('engine\\trainer:')) {
      return false;
    }
    if (isProgressLine(line)) {
      return true;
    }
    return (
      line.startsWith('Ultralytics ') ||
      line.startsWith('Training started:') ||
      line.startsWith('Starting training') ||
      line.startsWith('Image sizes') ||
      line.startsWith('Using ') ||
      line.startsWith('Logging results') ||
      line.startsWith('optimizer:') ||
      line.startsWith('train:') ||
      line.startsWith('val:') ||
      line.startsWith('Transferred ') ||
      line.startsWith('Overriding model.yaml') ||
      line.startsWith('Plotting labels')
    );
  };

  const filtered = lines.filter(isSummaryLine);
  const fallback = filtered.length ? filtered : lines.slice(-8);
  return fallback.slice(-limit);
};
