// src/components/training/TrainingDataPrepSection.tsx
import type { TrainingSource } from "../../types";
import { ui } from "../../ui/tokens";

interface TrainingDataPrepSectionProps {
    selectedCount: number;
    sources: TrainingSource[];
    loading: boolean;
    error: string | null;
    refresh: () => void;
    selectedSources: Set<string>;
    toggleSource: (id: string) => void;
    selectAll: () => void;
    clearAll: () => void;
    datasetId: string;
    setDatasetId: (value: string) => void;
    supportedTargets: string[];
    selectedTargets: Set<string>;
    selectedTargetsCount: number;
    toggleTarget: (target: string) => void;
    valSplit: string;
    testSplit: string;
    setValSplit: (value: string) => void;
    setTestSplit: (value: string) => void;
    seed: string;
    setSeed: (value: string) => void;
    useHardlinks: boolean;
    setUseHardlinks: (value: boolean) => void;
    overwrite: boolean;
    setOverwrite: (value: boolean) => void;
    prepareError: string | null;
    splitError: string | null;
    prepareJobId: string | null;
    preparing: boolean;
    onPrepareDataset: () => void;
}

export function TrainingDataPrepSection({
    selectedCount,
    sources,
    loading,
    error,
    refresh,
    selectedSources,
    toggleSource,
    selectAll,
    clearAll,
    datasetId,
    setDatasetId,
    supportedTargets,
    selectedTargets,
    selectedTargetsCount,
    toggleTarget,
    valSplit,
    testSplit,
    setValSplit,
    setTestSplit,
    seed,
    setSeed,
    useHardlinks,
    setUseHardlinks,
    overwrite,
    setOverwrite,
    prepareError,
    splitError,
    prepareJobId,
    preparing,
    onPrepareDataset,
}: TrainingDataPrepSectionProps) {
    return (
        <>
            <section className={ui.trainingSection}>
                <div className={ui.trainingSectionHeader}>
                    <h2 className={ui.trainingSectionTitle}>
                        Sources
                    </h2>
                    <div className="flex items-center gap-2">
                        <button
                            type="button"
                            className={ui.trainingButton}
                            onClick={refresh}
                        >
                            Refresh
                        </button>
                        <button
                            type="button"
                            className={ui.trainingButton}
                            onClick={selectAll}
                        >
                            Select all
                        </button>
                        <button
                            type="button"
                            className={ui.trainingButton}
                            onClick={clearAll}
                        >
                            Clear
                        </button>
                    </div>
                </div>
                {loading && (
                    <div className={ui.trainingHelp}>
                        Loading sources...
                    </div>
                )}
                {error && <div className={ui.trainingError}>{error}</div>}
                {!loading && !error && sources.length === 0 && (
                    <div className={ui.trainingHelp}>
                        No training sources found yet. Add datasets under
                        training-data/sources.
                    </div>
                )}
                {!loading && sources.length > 0 && (
                    <div className={ui.trainingList}>
                        {sources.map((source) => {
                            const checked = selectedSources.has(source.id);
                            const disabled = !source.available;
                            const stats = source.stats;
                            const volumes =
                                stats?.volumes === null ||
                                stats?.volumes === undefined
                                    ? "n/a"
                                    : stats.volumes;
                            const images =
                                stats?.images === null ||
                                stats?.images === undefined
                                    ? "n/a"
                                    : stats.images;
                            const annotations = stats?.annotations ?? [];
                            return (
                                <label
                                    key={source.id}
                                    className={
                                        "flex items-start gap-3 " +
                                        ui.trainingCard +
                                        " " +
                                        (disabled ? "opacity-60" : "")
                                    }
                                >
                                    <input
                                        type="checkbox"
                                        className="mt-1"
                                        checked={checked}
                                        disabled={disabled}
                                        onChange={() =>
                                            toggleSource(source.id)
                                        }
                                    />
                                    <div className="flex-1">
                                        <div className="flex items-center justify-between">
                                            <div className={ui.trainingItemTitle}>
                                                {source.label}
                                            </div>
                                            <span
                                                className={`${ui.trainingLabelTiny} uppercase tracking-wide`}
                                            >
                                                {source.type}
                                            </span>
                                        </div>
                                        {source.description && (
                                            <div className={`mt-1 ${ui.trainingLabelSmall}`}>
                                                {source.description}
                                            </div>
                                        )}
                                        <div className={`mt-2 flex flex-wrap gap-3 ${ui.trainingMetaSmall}`}>
                                            <span>Volumes: {volumes}</span>
                                            <span>Images: {images}</span>
                                        </div>
                                        {annotations.length > 0 && (
                                            <div className="mt-2 flex flex-wrap gap-2">
                                                {annotations.map((item) => (
                                                    <span
                                                        key={item}
                                                        className={ui.trainingTag}
                                                    >
                                                        {item}
                                                    </span>
                                                ))}
                                            </div>
                                        )}
                                        {source.path && (
                                            <div className={`mt-1 ${ui.trainingLabelSmall}`}>
                                                {source.path}
                                            </div>
                                        )}
                                    </div>
                                </label>
                            );
                        })}
                    </div>
                )}
            </section>
            {selectedCount === 0 ? (
                <section className={ui.trainingSectionCompact}>
                    <h3 className={ui.trainingSubTitle}>
                        Dataset builder
                    </h3>
                    <div className={ui.trainingHelp}>
                        Select at least one source to configure dataset
                        preparation.
                    </div>
                </section>
            ) : (
                <section className={ui.trainingSectionCompact}>
                    <h3 className={ui.trainingSubTitle}>
                        Dataset builder
                    </h3>
                    <div className={`mt-3 ${ui.trainingList}`}>
                        <label className="block">
                            <span className={ui.trainingLabelSmall}>
                                Dataset id
                            </span>
                            <input
                                value={datasetId}
                                onChange={(event) =>
                                    setDatasetId(event.target.value)
                                }
                                className={ui.trainingInput}
                            />
                        </label>
                        <div className={`flex items-center justify-between ${ui.trainingMetaSmall}`}>
                            <span>Targets</span>
                            <span>{selectedTargetsCount}</span>
                        </div>
                        <div
                            className={`${ui.trainingCardCompact} ${ui.trainingListTight}`}
                        >
                            {supportedTargets.length === 0 && (
                                <div className={ui.trainingHintSmall}>
                                    No supported targets found for the selected
                                    sources.
                                </div>
                            )}
                            {supportedTargets.map((target) => (
                                <label
                                    key={target}
                                    className="flex items-center gap-2"
                                >
                                    <input
                                        type="checkbox"
                                        checked={selectedTargets.has(target)}
                                        onChange={() => toggleTarget(target)}
                                    />
                                    <span className="uppercase tracking-wide">
                                        {target}
                                    </span>
                                </label>
                            ))}
                        </div>
                        <label className="block">
                            <span className={ui.trainingLabelSmall}>
                                Val split
                            </span>
                            <input
                                type="number"
                                step="0.01"
                                min="0"
                                max="0.99"
                                value={valSplit}
                                onChange={(event) =>
                                    setValSplit(event.target.value)
                                }
                                className={ui.trainingInput}
                            />
                        </label>
                        <label className="block">
                            <span className={ui.trainingLabelSmall}>
                                Test split
                            </span>
                            <input
                                type="number"
                                step="0.01"
                                min="0"
                                max="0.99"
                                value={testSplit}
                                onChange={(event) =>
                                    setTestSplit(event.target.value)
                                }
                                className={ui.trainingInput}
                            />
                        </label>
                        <label className="block">
                            <span className={ui.trainingLabelSmall}>
                                Seed
                            </span>
                            <input
                                type="number"
                                step="1"
                                min="0"
                                value={seed}
                                onChange={(event) =>
                                    setSeed(event.target.value)
                                }
                                className={ui.trainingInput}
                            />
                        </label>
                        <label className={`flex items-start gap-2 ${ui.trainingMetaSmall}`}>
                            <input
                                type="checkbox"
                                checked={useHardlinks}
                                onChange={(event) =>
                                    setUseHardlinks(event.target.checked)
                                }
                                className="mt-1"
                            />
                            <span>
                                Use hardlinks (saves space, same drive only)
                            </span>
                        </label>
                        <label className={`flex items-center gap-2 ${ui.trainingMetaSmall}`}>
                            <input
                                type="checkbox"
                                checked={overwrite}
                                onChange={(event) =>
                                    setOverwrite(event.target.checked)
                                }
                            />
                            Overwrite existing
                        </label>
                    </div>
                    {prepareError && (
                        <div className={`mt-2 ${ui.trainingError}`}>
                            {prepareError}
                        </div>
                    )}
                    {splitError && (
                        <div className={`mt-2 ${ui.trainingWarning}`}>
                            {splitError}
                        </div>
                    )}
                    {prepareJobId && (
                        <div className={`mt-2 ${ui.trainingMeta}`}>
                            Dataset build queued. Track progress in Jobs.
                        </div>
                    )}
                    <button
                        type="button"
                        onClick={onPrepareDataset}
                        disabled={preparing || !selectedCount || !!splitError}
                        className={ui.trainingPrimaryButton}
                    >
                        {preparing ? "Preparing..." : "Prepare dataset"}
                    </button>
                </section>
            )}
        </>
    );
}
