// src/components/training/TrainingConfigSection.tsx
import { ui } from '../../ui/tokens';

interface TrainingConfigSectionProps {
  selectedDatasetId: string | null;
  modelFamily: string;
  modelFamilies: string[];
  onChangeModelFamily: (value: string) => void;
  modelSize: string;
  onChangeModelSize: (value: string) => void;
  modelId: string;
  ultralyticsVersion: string | null;
  pretrained: boolean;
  onChangePretrained: (value: boolean) => void;
  epochs: string;
  onChangeEpochs: (value: string) => void;
  batchSize: string;
  onChangeBatchSize: (value: string) => void;
  workers: string;
  onChangeWorkers: (value: string) => void;
  imageSize: string;
  onChangeImageSize: (value: string) => void;
  device: string;
  onChangeDevice: (value: string) => void;
  patience: string;
  onChangePatience: (value: string) => void;
  augmentations: boolean;
  onChangeAugmentations: (value: boolean) => void;
  dryRun: boolean;
  onChangeDryRun: (value: boolean) => void;
  trainError: string | null;
  trainJobId: string | null;
  training: boolean;
  onStartTraining: () => void;
}

export function TrainingConfigSection({
  selectedDatasetId,
  modelFamily,
  modelFamilies,
  onChangeModelFamily,
  modelSize,
  onChangeModelSize,
  modelId,
  ultralyticsVersion,
  pretrained,
  onChangePretrained,
  epochs,
  onChangeEpochs,
  batchSize,
  onChangeBatchSize,
  workers,
  onChangeWorkers,
  imageSize,
  onChangeImageSize,
  device,
  onChangeDevice,
  patience,
  onChangePatience,
  augmentations,
  onChangeAugmentations,
  dryRun,
  onChangeDryRun,
  trainError,
  trainJobId,
  training,
  onStartTraining,
}: TrainingConfigSectionProps) {
  return (
    <section className={ui.trainingSectionCompact}>
      <h3 className={ui.trainingSubTitle}>Training config</h3>
      {!selectedDatasetId && (
        <div className={`mt-3 ${ui.trainingHelp}`}>
          Select a prepared dataset to configure training.
        </div>
      )}
      {selectedDatasetId && (
        <div className={`mt-3 ${ui.trainingList}`}>
          <div className="flex items-center justify-between">
            <span>Dataset</span>
            <span className={ui.trainingMetaSmall}>{selectedDatasetId}</span>
          </div>
          <label className="block">
            <span className={ui.trainingLabelSmall}>Model family</span>
            <select
              value={modelFamily}
              onChange={(event) => onChangeModelFamily(event.target.value)}
              className={ui.trainingInput}
            >
              {modelFamilies.map((family) => (
                <option key={family} value={family}>
                  {family.toUpperCase()}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className={ui.trainingLabelSmall}>Model size</span>
            <select
              value={modelSize}
              onChange={(event) => onChangeModelSize(event.target.value)}
              className={ui.trainingInput}
            >
              <option value="n">n (fast)</option>
              <option value="s">s</option>
              <option value="m">m</option>
              <option value="l">l</option>
              <option value="x">x (accurate)</option>
            </select>
          </label>
          <div className={`flex items-center justify-between ${ui.trainingMetaSmall}`}>
            <span>Weights</span>
            <span className={ui.trainingMetaSmall}>{modelId}.pt</span>
          </div>
          {ultralyticsVersion && (
            <div className={ui.trainingLabelSmall}>Ultralytics {ultralyticsVersion}</div>
          )}
          <label className={`flex items-center gap-2 ${ui.trainingMetaSmall}`}>
            <input
              type="checkbox"
              checked={pretrained}
              onChange={(event) => onChangePretrained(event.target.checked)}
            />
            Use pretrained weights
          </label>
          <label className="block">
            <span className={ui.trainingLabelSmall}>Epochs</span>
            <input
              type="number"
              min="1"
              step="1"
              value={epochs}
              onChange={(event) => onChangeEpochs(event.target.value)}
              className={ui.trainingInput}
            />
          </label>
          <label className="block">
            <span className={ui.trainingLabelSmall}>Batch size</span>
            <input
              type="number"
              min="1"
              step="1"
              value={batchSize}
              onChange={(event) => onChangeBatchSize(event.target.value)}
              className={ui.trainingInput}
            />
          </label>
          <label className="block">
            <span className={ui.trainingLabelSmall}>Workers</span>
            <input
              type="number"
              min="0"
              step="1"
              value={workers}
              onChange={(event) => onChangeWorkers(event.target.value)}
              className={ui.trainingInput}
            />
          </label>
          <label className="block">
            <span className={ui.trainingLabelSmall}>Image size</span>
            <div className="mt-1 flex flex-wrap gap-2">
              {[640, 768, 1024, 1280].map((preset) => (
                <button
                  key={preset}
                  type="button"
                  onClick={() => onChangeImageSize(String(preset))}
                  className={ui.trainingPreset}
                >
                  {preset}
                </button>
              ))}
            </div>
            <input
              type="number"
              min="320"
              step="32"
              value={imageSize}
              onChange={(event) => onChangeImageSize(event.target.value)}
              className={ui.trainingInput}
            />
          </label>
          <label className="block">
            <span className={ui.trainingLabelSmall}>Device</span>
            <select
              value={device}
              onChange={(event) => onChangeDevice(event.target.value)}
              className={ui.trainingInput}
            >
              <option value="auto">Auto</option>
              <option value="cpu">CPU</option>
              <option value="cuda">GPU (CUDA)</option>
            </select>
          </label>
          <label className="block">
            <span className={ui.trainingLabelSmall}>Patience</span>
            <input
              type="number"
              min="0"
              step="1"
              value={patience}
              onChange={(event) => onChangePatience(event.target.value)}
              className={ui.trainingInput}
            />
          </label>
          <label className={`flex items-center gap-2 ${ui.trainingMetaSmall}`}>
            <input
              type="checkbox"
              checked={augmentations}
              onChange={(event) => onChangeAugmentations(event.target.checked)}
            />
            Enable augmentations
          </label>
          <label className={`flex items-center gap-2 ${ui.trainingMetaSmall}`}>
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(event) => onChangeDryRun(event.target.checked)}
            />
            Dry run (1 epoch, no files saved)
          </label>
          {trainError && <div className={ui.trainingError}>{trainError}</div>}
          {trainJobId && (
            <div className={ui.trainingMeta}>Training queued. Track progress in Jobs.</div>
          )}
          <button
            type="button"
            onClick={onStartTraining}
            disabled={training || !selectedDatasetId}
            className={ui.trainingPrimaryButtonTight}
          >
            {training ? 'Starting...' : 'Start training'}
          </button>
        </div>
      )}
    </section>
  );
}
