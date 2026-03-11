// src/components/training/TrainingDatasetsSection.tsx
import type { TrainingDataset } from '../../types';
import { ui } from '../../ui/tokens';

interface TrainingDatasetsSectionProps {
  datasets: TrainingDataset[];
  datasetsLoading: boolean;
  datasetsError: string | null;
  selectedDatasetId: string | null;
  onSelectDataset: (datasetId: string) => void;
  refreshDatasets: () => void;
}

export function TrainingDatasetsSection({
  datasets,
  datasetsLoading,
  datasetsError,
  selectedDatasetId,
  onSelectDataset,
  refreshDatasets,
}: TrainingDatasetsSectionProps) {
  return (
    <section className={ui.trainingSection}>
      <div className={ui.trainingSectionHeader}>
        <h2 className={ui.trainingSectionTitle}>Prepared datasets</h2>
        <button type="button" className={ui.trainingButton} onClick={refreshDatasets}>
          Refresh
        </button>
      </div>
      {datasetsLoading && <div className={ui.trainingHelp}>Loading prepared datasets...</div>}
      {datasetsError && <div className={ui.trainingError}>{datasetsError}</div>}
      {!datasetsLoading && !datasetsError && datasets.length === 0 && (
        <div className={ui.trainingHelp}>No prepared datasets yet.</div>
      )}
      {!datasetsLoading && datasets.length > 0 && (
        <div className={ui.trainingList}>
          {datasets.map((dataset) => {
            const checked = selectedDatasetId === dataset.id;
            const stats = dataset.stats;
            const trainImages =
              stats?.train_images === null || stats?.train_images === undefined
                ? 'n/a'
                : stats.train_images;
            const valImages =
              stats?.val_images === null || stats?.val_images === undefined
                ? 'n/a'
                : stats.val_images;
            const testImages =
              stats?.test_images === null || stats?.test_images === undefined
                ? 0
                : stats.test_images;
            const targets = dataset.targets ?? [];
            const splits: string[] = [];
            if (dataset.val_split !== null && dataset.val_split !== undefined) {
              splits.push(`val ${dataset.val_split}`);
            }
            if (
              dataset.test_split !== null &&
              dataset.test_split !== undefined &&
              dataset.test_split > 0
            ) {
              splits.push(`test ${dataset.test_split}`);
            }
            if (dataset.image_mode) {
              splits.push(`mode ${dataset.image_mode}`);
            }

            return (
              <label
                key={dataset.id}
                className={
                  'flex items-start gap-3 ' +
                  ui.trainingCard +
                  ' ' +
                  (checked ? 'ring-1 ring-sky-500' : '')
                }
              >
                <input
                  type="radio"
                  name="prepared-dataset"
                  className="mt-1"
                  checked={checked}
                  onChange={() => onSelectDataset(dataset.id)}
                />
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <div className={ui.trainingItemTitle}>{dataset.id}</div>
                    {dataset.created_at && (
                      <span className={ui.trainingLabelTiny}>{dataset.created_at}</span>
                    )}
                  </div>
                  <div className={`mt-2 flex flex-wrap gap-3 ${ui.trainingMetaSmall}`}>
                    <span>Train: {trainImages}</span>
                    <span>Val: {valImages}</span>
                    {testImages ? <span>Test: {testImages}</span> : null}
                    {splits.length > 0 ? <span>Splits: {splits.join(', ')}</span> : null}
                  </div>
                  {targets.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {targets.map((item) => (
                        <span key={item} className={ui.trainingTag}>
                          {item}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className={`mt-1 ${ui.trainingLabelSmall}`}>{dataset.path}</div>
                </div>
              </label>
            );
          })}
        </div>
      )}
    </section>
  );
}
