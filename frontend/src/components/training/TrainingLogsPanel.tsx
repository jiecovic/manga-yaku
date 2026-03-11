// src/components/training/TrainingLogsPanel.tsx
import { useEffect, useMemo, useRef } from 'react';
import type { Job } from '../../api';
import { EmptyState, Field, Select } from '../../ui/primitives';
import { ui } from '../../ui/tokens';
import { formatFloat } from '../../utils/format';
import { getProgressDisplay } from '../../utils/progress';
import { extractLiveMetrics, summarizeLogLines } from '../../utils/trainingLogs';

interface TrainingLogsPanelProps {
  trainingJobs: Job[];
  selectedLogJobId: string | null;
  onSelectLogJob: (jobId: string | null) => void;
  logLines: string[];
  logStatusLabel: string;
  logError: string | null;
}

interface TrainingJobPayload {
  dataset_id?: string;
}

interface MetricPoint {
  x: number;
  y: number;
}

interface MetricHistory {
  box: MetricPoint[];
  cls: MetricPoint[];
  dfl: MetricPoint[];
  map50: MetricPoint[];
  map50_95: MetricPoint[];
}

const MAX_HISTORY_POINTS = 200;

const createEmptyHistory = (): MetricHistory => ({
  box: [],
  cls: [],
  dfl: [],
  map50: [],
  map50_95: [],
});

const clampHistory = (values: MetricPoint[]): MetricPoint[] =>
  values.length > MAX_HISTORY_POINTS ? values.slice(values.length - MAX_HISTORY_POINTS) : values;

const appendPoint = (values: MetricPoint[], point: MetricPoint | null): MetricPoint[] => {
  if (!point) {
    return values;
  }
  return clampHistory([...values, point]);
};

const withOccurrenceKeys = <T,>(
  items: T[],
  keyOf: (item: T) => string,
): Array<{ key: string; item: T }> => {
  const seen = new Map<string, number>();
  return items.map((item) => {
    const base = keyOf(item);
    const nextCount = (seen.get(base) ?? 0) + 1;
    seen.set(base, nextCount);
    return { key: `${base}-${nextCount}`, item };
  });
};

const progressLinePattern =
  /^\s*(\d+)\/(\d+)\s+(\S+)\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+(\d+)\s+(\d+):/;

const toFinite = (value: number | null | undefined): number | null =>
  value !== null && value !== undefined && Number.isFinite(value) ? value : null;

const parseProgressLine = (line: string) => {
  const match = line.match(progressLinePattern);
  if (!match) {
    return null;
  }
  return {
    epoch: Number(match[1]),
    total: Number(match[2]),
    boxLoss: Number(match[4]),
    clsLoss: Number(match[5]),
    dflLoss: Number(match[6]),
  };
};

const parseMapLine = (line: string) => {
  const allMatch = line.match(
    /^\s*all\s+\d+\s+\d+\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)/,
  );
  if (allMatch) {
    return {
      map50: Number(allMatch[3]),
      map50_95: Number(allMatch[4]),
    };
  }
  const map50Match = line.match(/mAP50[^0-9]*([0-9.]+)/i);
  const mapMatch = line.match(/mAP50-95[^0-9]*([0-9.]+)/i);
  if (!map50Match && !mapMatch) {
    return null;
  }
  return {
    map50: map50Match ? Number(map50Match[1]) : null,
    map50_95: mapMatch ? Number(mapMatch[1]) : null,
  };
};

const buildMetricHistory = (lines: string[], metrics?: Job['metrics'] | null): MetricHistory => {
  const history = createEmptyHistory();
  const progressEntries: Array<{
    epoch: number;
    boxLoss: number;
    clsLoss: number;
    dflLoss: number;
  }> = [];
  const mapEntries: Array<{
    epoch: number;
    map50: number | null;
    map50_95: number | null;
  }> = [];
  let lastEpoch: number | null = null;

  for (const line of lines) {
    const progress = parseProgressLine(line);
    if (progress) {
      progressEntries.push(progress);
      lastEpoch = progress.epoch;
      continue;
    }
    const map = parseMapLine(line);
    if (map && lastEpoch !== null) {
      mapEntries.push({
        epoch: lastEpoch,
        map50: toFinite(map.map50),
        map50_95: toFinite(map.map50_95),
      });
    }
  }

  const perEpochTotals = new Map<number, number>();
  for (const entry of progressEntries) {
    perEpochTotals.set(entry.epoch, (perEpochTotals.get(entry.epoch) ?? 0) + 1);
  }
  const perEpochSeen = new Map<number, number>();

  for (const entry of progressEntries) {
    const total = perEpochTotals.get(entry.epoch) ?? 1;
    const seen = (perEpochSeen.get(entry.epoch) ?? 0) + 1;
    perEpochSeen.set(entry.epoch, seen);
    const xValue = entry.epoch - 1 + seen / total;
    history.box = appendPoint(history.box, {
      x: xValue,
      y: entry.boxLoss,
    });
    history.cls = appendPoint(history.cls, {
      x: xValue,
      y: entry.clsLoss,
    });
    history.dfl = appendPoint(history.dfl, {
      x: xValue,
      y: entry.dflLoss,
    });
  }

  for (const entry of mapEntries) {
    if (entry.map50 !== null) {
      history.map50 = appendPoint(history.map50, {
        x: entry.epoch,
        y: entry.map50,
      });
    }
    if (entry.map50_95 !== null) {
      history.map50_95 = appendPoint(history.map50_95, {
        x: entry.epoch,
        y: entry.map50_95,
      });
    }
  }

  if (metrics) {
    const epoch = toFinite(metrics.epoch ?? null);
    if (epoch !== null) {
      let xValue = epoch;
      const batch = toFinite(metrics.batch ?? null);
      const batches = toFinite(metrics.batches ?? null);
      if (batch !== null && batches !== null && batches > 0) {
        xValue = epoch - 1 + batch / batches;
      }
      if (!history.box.length) {
        const boxLoss = toFinite(metrics.box_loss ?? null);
        if (boxLoss !== null) {
          history.box = appendPoint(history.box, {
            x: xValue,
            y: boxLoss,
          });
        }
      }
      if (!history.cls.length) {
        const clsLoss = toFinite(metrics.cls_loss ?? null);
        if (clsLoss !== null) {
          history.cls = appendPoint(history.cls, {
            x: xValue,
            y: clsLoss,
          });
        }
      }
      if (!history.dfl.length) {
        const dflLoss = toFinite(metrics.dfl_loss ?? null);
        if (dflLoss !== null) {
          history.dfl = appendPoint(history.dfl, {
            x: xValue,
            y: dflLoss,
          });
        }
      }
      if (!history.map50.length) {
        const map50 = toFinite(metrics.map50 ?? null);
        if (map50 !== null) {
          history.map50 = appendPoint(history.map50, {
            x: epoch,
            y: map50,
          });
        }
      }
      if (!history.map50_95.length) {
        const map50_95 = toFinite(metrics.map50_95 ?? null);
        if (map50_95 !== null) {
          history.map50_95 = appendPoint(history.map50_95, {
            x: epoch,
            y: map50_95,
          });
        }
      }
    }
  }

  return {
    box: clampHistory(history.box),
    cls: clampHistory(history.cls),
    dfl: clampHistory(history.dfl),
    map50: clampHistory(history.map50),
    map50_95: clampHistory(history.map50_95),
  };
};

interface ChartSeries {
  label: string;
  color: string;
  values: MetricPoint[];
}

const buildPath = (
  values: MetricPoint[],
  minX: number,
  maxX: number,
  minY: number,
  maxY: number,
): string => {
  if (values.length < 2) {
    return '';
  }
  const rangeX = maxX - minX || 1;
  const rangeY = maxY - minY || 1;
  return values
    .map((point, index) => {
      const x = ((point.x - minX) / rangeX) * 100;
      const y = 100 - ((point.y - minY) / rangeY) * 100;
      return `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(' ');
};

const MetricChart = ({ title, series }: { title: string; series: ChartSeries[] }) => {
  const points = series.flatMap((item) => item.values);
  if (points.length < 2) {
    return (
      <div className="rounded-md border border-slate-800 bg-slate-950/60 p-2">
        <div className={ui.trainingMetaSmall}>{title}</div>
        <div className={`mt-2 ${ui.mutedTextTiny}`}>Waiting for metrics...</div>
      </div>
    );
  }
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);

  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/60 p-2">
      <div className={ui.trainingMetaSmall}>{title}</div>
      <svg viewBox="0 0 100 100" className="mt-2 h-20 w-full" preserveAspectRatio="none">
        <title>{title}</title>
        {series.map((item) => {
          const path = buildPath(item.values, minX, maxX, minY, maxY);
          if (!path) {
            return null;
          }
          return (
            <path key={item.label} d={path} fill="none" stroke={item.color} strokeWidth="1.5" />
          );
        })}
      </svg>
      <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-slate-400">
        {series.map((item) => (
          <span key={item.label} className="flex items-center gap-1">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: item.color }}
            />
            {item.label}
          </span>
        ))}
      </div>
    </div>
  );
};

export function TrainingLogsPanel({
  trainingJobs,
  selectedLogJobId,
  onSelectLogJob,
  logLines,
  logStatusLabel,
  logError,
}: TrainingLogsPanelProps) {
  const logRef = useRef<HTMLDivElement | null>(null);
  const selectedLogJob = trainingJobs.find((job) => job.id === selectedLogJobId) ?? null;
  const progressDisplay = getProgressDisplay(selectedLogJob?.progress);
  const liveMetrics = useMemo(() => {
    return extractLiveMetrics(logLines);
  }, [logLines]);
  const displayMetrics = useMemo(() => {
    if (!selectedLogJob) {
      return null;
    }
    const parsed = liveMetrics
      ? {
          epoch: liveMetrics.epoch,
          total_epochs: liveMetrics.total,
          gpu_mem: liveMetrics.gpuMem,
          box_loss: liveMetrics.boxLoss,
          cls_loss: liveMetrics.clsLoss,
          dfl_loss: liveMetrics.dflLoss,
          batches: null,
          batch: null,
          lr: null,
        }
      : null;
    const jobMetrics = selectedLogJob.metrics ?? null;
    if (!parsed && !jobMetrics) {
      return null;
    }
    return {
      ...parsed,
      ...jobMetrics,
    };
  }, [liveMetrics, selectedLogJob]);

  const summaryLines = useMemo(() => summarizeLogLines(logLines, 12), [logLines]);
  const summaryLineEntries = useMemo(
    () => withOccurrenceKeys(summaryLines, (line) => line),
    [summaryLines],
  );

  useEffect(() => {
    if (summaryLines.length === 0) {
      return;
    }
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [summaryLines]);

  const metricHistory = useMemo(
    () => buildMetricHistory(logLines, selectedLogJob?.metrics ?? null),
    [logLines, selectedLogJob?.metrics],
  );

  const lossSeries = useMemo<ChartSeries[]>(
    () => [
      { label: 'Box', color: '#38bdf8', values: metricHistory.box },
      { label: 'Cls', color: '#fbbf24', values: metricHistory.cls },
      { label: 'DFL', color: '#a78bfa', values: metricHistory.dfl },
    ],
    [metricHistory],
  );

  const mapSeries = useMemo<ChartSeries[]>(
    () => [
      { label: 'mAP50', color: '#34d399', values: metricHistory.map50 },
      { label: 'mAP50-95', color: '#f87171', values: metricHistory.map50_95 },
    ],
    [metricHistory],
  );

  return (
    <section className={ui.trainingSectionCompact}>
      <div className="flex items-center justify-between">
        <h3 className={ui.trainingSubTitle}>Training logs</h3>
        <span className={ui.trainingLogBadge}>{logStatusLabel}</span>
      </div>
      {trainingJobs.length === 0 ? (
        <EmptyState className="mt-3 h-24">Start a training run to see logs.</EmptyState>
      ) : (
        <div className="mt-3 space-y-2">
          <Field label="Log source" labelClassName={ui.trainingLabelSmall}>
            <Select
              variant="training"
              value={selectedLogJobId ?? ''}
              onChange={(event) => onSelectLogJob(event.target.value || null)}
            >
              <option value="">Select a training job</option>
              {trainingJobs.map((job) => {
                const payload = job.payload as TrainingJobPayload;
                const datasetLabel = payload?.dataset_id
                  ? `dataset ${payload.dataset_id}`
                  : 'training job';
                return (
                  <option key={job.id} value={job.id}>
                    {job.status} | {datasetLabel}
                  </option>
                );
              })}
            </Select>
          </Field>
          {selectedLogJob && (
            <div className={ui.trainingCardCompact}>
              <div className={ui.trainingMetaSmall}>Current status</div>
              <div className={`mt-1 ${ui.trainingLogStatus}`}>
                {selectedLogJob.message ?? 'Running...'}
              </div>
              {progressDisplay.progress !== null && (
                <div className="mt-2">
                  <div className={ui.progressTrack}>
                    <div
                      className={ui.progressFill}
                      style={{
                        width: `${progressDisplay.width}%`,
                      }}
                    />
                  </div>
                  <div className={`mt-1 ${ui.trainingLabelTiny}`}>{progressDisplay.label}</div>
                </div>
              )}
              {displayMetrics && (
                <div className={`mt-3 grid grid-cols-2 gap-2 ${ui.trainingLogMetrics}`}>
                  <div>
                    Epoch: {displayMetrics.epoch ?? '?'}/{displayMetrics.total_epochs ?? '?'}
                  </div>
                  {displayMetrics.batch !== null &&
                    displayMetrics.batch !== undefined &&
                    displayMetrics.batches !== null &&
                    displayMetrics.batches !== undefined && (
                      <div>
                        Batch: {displayMetrics.batch}/{displayMetrics.batches}
                      </div>
                    )}
                  {displayMetrics.device && <div>Device: {displayMetrics.device}</div>}
                  {displayMetrics.gpu_mem && <div>GPU mem: {displayMetrics.gpu_mem}</div>}
                  {displayMetrics.box_loss !== null && displayMetrics.box_loss !== undefined && (
                    <div>Box loss: {formatFloat(displayMetrics.box_loss)}</div>
                  )}
                  {displayMetrics.cls_loss !== null && displayMetrics.cls_loss !== undefined && (
                    <div>Cls loss: {formatFloat(displayMetrics.cls_loss)}</div>
                  )}
                  {displayMetrics.dfl_loss !== null && displayMetrics.dfl_loss !== undefined && (
                    <div>DFL loss: {formatFloat(displayMetrics.dfl_loss)}</div>
                  )}
                  {displayMetrics.map50 !== null && displayMetrics.map50 !== undefined && (
                    <div>mAP50: {formatFloat(displayMetrics.map50)}</div>
                  )}
                  {displayMetrics.map50_95 !== null && displayMetrics.map50_95 !== undefined && (
                    <div>mAP50-95: {formatFloat(displayMetrics.map50_95)}</div>
                  )}
                  {displayMetrics.lr !== null && displayMetrics.lr !== undefined && (
                    <div>LR: {formatFloat(displayMetrics.lr, 6)}</div>
                  )}
                </div>
              )}
              {selectedLogJob && (
                <div className="mt-3 grid gap-2 md:grid-cols-2">
                  <MetricChart title="Loss trends" series={lossSeries} />
                  <MetricChart title="mAP trends" series={mapSeries} />
                </div>
              )}
            </div>
          )}
          <div ref={logRef} className={ui.trainingLogBox}>
            {summaryLines.length > 0 ? (
              <div className={`p-2 ${ui.trainingLogLine}`}>
                {summaryLineEntries.map(({ key, item: line }) => (
                  <div key={key}>{line}</div>
                ))}
              </div>
            ) : (
              <div className={`p-3 ${ui.mutedTextTiny}`}>Waiting for updates...</div>
            )}
          </div>
          {selectedLogJob && (
            <div className={ui.trainingMetaSmall}>Status: {selectedLogJob.status}</div>
          )}
          {logError && <div className={ui.trainingWarningSmall}>{logError}</div>}
        </div>
      )}
    </section>
  );
}
