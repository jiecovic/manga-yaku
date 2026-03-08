// src/components/training/TrainingLayout.tsx
import { useEffect, useMemo, useState } from "react";

import {
    createPrepareDatasetJob,
    createTrainModelJob,
    fetchTrainingModels,
} from "../../api";
import { useJobs } from "../../context/useJobs";
import { useJobLogs } from "../../hooks/useJobLogs";
import { JobsPanel } from "../JobsPanel";
import { useTrainingDatasets } from "../../hooks/useTrainingDatasets";
import { useTrainingSources } from "../../hooks/useTrainingSources";
import { TrainingConfigSection } from "./TrainingConfigSection";
import { TrainingDataPrepSection } from "./TrainingDataPrepSection";
import { TrainingDatasetsSection } from "./TrainingDatasetsSection";
import { TrainingLogsPanel } from "./TrainingLogsPanel";
import { TrainingMetaPanel } from "./TrainingMetaPanel";
import { ui } from "../../ui/tokens";

const TRAINING_TAB_KEY = "training.activeTab";

export function TrainingLayout() {
    const { sources, loading, error, refresh } = useTrainingSources();
    const {
        datasets,
        loading: datasetsLoading,
        error: datasetsError,
        refresh: refreshDatasets,
    } = useTrainingDatasets();
    const { jobs } = useJobs();
    const [datasetId, setDatasetId] = useState(() => {
        const now = new Date();
        const pad = (value: number) => String(value).padStart(2, "0");
        const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(
            now.getDate(),
        )}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(
            now.getSeconds(),
        )}`;
        return `dataset-${stamp}`;
    });
    const [prepareJobId, setPrepareJobId] = useState<string | null>(null);
    const [prepareError, setPrepareError] = useState<string | null>(null);
    const [preparing, setPreparing] = useState(false);
    const [overwrite, setOverwrite] = useState(false);
    const [valSplit, setValSplit] = useState("0.15");
    const [testSplit, setTestSplit] = useState("0.0");
    const [seed, setSeed] = useState("1337");
    const [useHardlinks, setUseHardlinks] = useState(false);
    const [selectedSources, setSelectedSources] = useState<Set<string>>(
        () => new Set<string>(),
    );
    const [selectedTargets, setSelectedTargets] = useState<Set<string>>(
        () => new Set<string>(["text"]),
    );
    const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(
        null,
    );
    const [modelFamily, setModelFamily] = useState("yolo26");
    const [modelSize, setModelSize] = useState("n");
    const [pretrained, setPretrained] = useState(true);
    const [epochs, setEpochs] = useState("50");
    const [batchSize, setBatchSize] = useState("8");
    const [workers, setWorkers] = useState("0");
    const [imageSize, setImageSize] = useState("1024");
    const [device, setDevice] = useState("auto");
    const [patience, setPatience] = useState("20");
    const [augmentations, setAugmentations] = useState(true);
    const [dryRun, setDryRun] = useState(false);
    const [trainJobId, setTrainJobId] = useState<string | null>(null);
    const [trainError, setTrainError] = useState<string | null>(null);
    const [training, setTraining] = useState(false);
    const [selectedLogJobId, setSelectedLogJobId] = useState<string | null>(
        null,
    );
    const [activeTab, setActiveTab] = useState<"prep" | "train">(() => {
        if (typeof window === "undefined") {
            return "prep";
        }
        const stored = window.localStorage.getItem(TRAINING_TAB_KEY);
        return stored === "prep" || stored === "train" ? stored : "prep";
    });
    const [modelFamilies, setModelFamilies] = useState<string[]>([
        "yolo11",
        "yolo12",
        "yolo26",
    ]);
    const [ultralyticsVersion, setUltralyticsVersion] = useState<string | null>(
        null,
    );

    useEffect(() => {
        setSelectedSources((prev) => {
            const next = new Set<string>();
            const sourceIds = new Set(sources.map((s) => s.id));
            for (const id of prev) {
                if (sourceIds.has(id)) {
                    next.add(id);
                }
            }
            return next;
        });
    }, [sources]);

    useEffect(() => {
        setSelectedDatasetId((prev) => {
            if (datasets.length === 0) {
                return null;
            }
            if (prev && datasets.some((dataset) => dataset.id === prev)) {
                return prev;
            }
            return datasets[0].id;
        });
    }, [datasets]);

    useEffect(() => {
        let cancelled = false;

        const loadModels = async () => {
            try {
                const response = await fetchTrainingModels();
                if (cancelled) return;
                if (response.ultralytics_version) {
                    setUltralyticsVersion(response.ultralytics_version);
                }
                if (Array.isArray(response.families) && response.families.length) {
                    setModelFamilies(response.families);
                    setModelFamily((prev) =>
                        response.families.includes(prev)
                            ? prev
                            : response.families[0],
                    );
                }
            } catch (err) {
                console.warn("Failed to load model families", err);
            }
        };

        void loadModels();
        return () => {
            cancelled = true;
        };
    }, []);

    const availableSources = useMemo(
        () => sources.filter((source) => source.available),
        [sources],
    );
    const trainingJobs = useMemo(
        () =>
            jobs
                .filter((job) => job.type === "train_model")
                .slice()
                .sort((a, b) => b.created_at - a.created_at),
        [jobs],
    );

    const selectedCount = selectedSources.size;
    const selectedSourceList = useMemo(
        () => sources.filter((source) => selectedSources.has(source.id)),
        [sources, selectedSources],
    );
    const supportedTargets = useMemo(() => {
        const allowed = new Set(["text", "panel", "face", "body"]);
        const pool = selectedSourceList.length
            ? selectedSourceList
            : availableSources;

        if (!pool.length) {
            return [];
        }

        if (!selectedSourceList.length) {
            const targetSet = new Set<string>();
            for (const source of pool) {
                const annotations = source.stats?.annotations ?? [];
                for (const annotation of annotations) {
                    const normalized = String(annotation).toLowerCase();
                    if (allowed.has(normalized)) {
                        targetSet.add(normalized);
                    }
                }
            }
            return Array.from(targetSet).sort();
        }

        let intersection: Set<string> | null = null;
        for (const source of pool) {
            const annotations = source.stats?.annotations ?? [];
            const current = new Set<string>();
            for (const annotation of annotations) {
                const normalized = String(annotation).toLowerCase();
                if (allowed.has(normalized)) {
                    current.add(normalized);
                }
            }
            if (intersection === null) {
                intersection = current;
            } else {
                const nextIntersection: string[] = [];
                for (const item of intersection) {
                    if (current.has(item)) {
                        nextIntersection.push(item);
                    }
                }
                intersection = new Set(nextIntersection);
            }
            if (intersection.size === 0) {
                break;
            }
        }

        return intersection ? Array.from(intersection).sort() : [];
    }, [availableSources, selectedSourceList]);
    const selectedTargetsCount = selectedTargets.size;
    const splitError = useMemo(() => {
        const valValue = Number(valSplit);
        const testValue = Number(testSplit);

        if (!Number.isFinite(valValue) || !Number.isFinite(testValue)) {
            return "Enter valid split values.";
        }
        if (valValue <= 0 || valValue >= 1) {
            return "Val split must be between 0 and 1.";
        }
        if (testValue < 0 || testValue >= 1) {
            return "Test split must be between 0 and 1.";
        }
        if (valValue + testValue >= 1) {
            return "Val split + test split must be less than 1.";
        }
        return null;
    }, [valSplit, testSplit]);
    const modelId = `${modelFamily}${modelSize}`;
    const {
        lines: logLines,
        status: logStatus,
        error: logError,
    } = useJobLogs(selectedLogJobId);

    useEffect(() => {
        if (!trainingJobs.length) {
            setSelectedLogJobId(null);
            return;
        }
        if (selectedLogJobId) {
            const exists = trainingJobs.some(
                (job) => job.id === selectedLogJobId,
            );
            if (exists) {
                return;
            }
        }
        const running = trainingJobs.find((job) => job.status === "running");
        setSelectedLogJobId((running ?? trainingJobs[0]).id);
    }, [trainingJobs, selectedLogJobId]);

    const logStatusLabel =
        logStatus === "connected"
            ? "Live"
            : logStatus === "connecting"
            ? "Connecting"
            : logStatus === "error"
            ? "Disconnected"
            : "Idle";

    useEffect(() => {
        if (typeof window === "undefined") {
            return;
        }
        window.localStorage.setItem(TRAINING_TAB_KEY, activeTab);
    }, [activeTab]);

    useEffect(() => {
        setSelectedTargets((prev) => {
            if (!supportedTargets.length) {
                return new Set<string>();
            }
            const next = new Set<string>();
            for (const target of prev) {
                if (supportedTargets.includes(target)) {
                    next.add(target);
                }
            }
            if (next.size === 0 && supportedTargets.includes("text")) {
                next.add("text");
            }
            return next;
        });
    }, [supportedTargets]);

    const toggleSource = (id: string) => {
        setSelectedSources((prev) => {
            const next = new Set(prev);
            if (next.has(id)) {
                next.delete(id);
            } else {
                next.add(id);
            }
            return next;
        });
    };

    const selectAll = () => {
        setSelectedSources(
            new Set(availableSources.map((source) => source.id)),
        );
    };

    const clearAll = () => {
        setSelectedSources(new Set<string>());
    };

    const toggleTarget = (target: string) => {
        setSelectedTargets((prev) => {
            const next = new Set(prev);
            if (next.has(target)) {
                next.delete(target);
            } else {
                next.add(target);
            }
            return next;
        });
    };

    const handlePrepareDataset = async () => {
        if (!selectedCount) {
            setPrepareError("Select at least one source.");
            return;
        }
        if (!selectedTargetsCount) {
            setPrepareError("Select at least one target.");
            return;
        }
        if (splitError) {
            setPrepareError(null);
            return;
        }
        const seedValue = Number.parseInt(seed, 10);
        if (!Number.isFinite(seedValue)) {
            setPrepareError("Seed must be a whole number.");
            return;
        }
        const valValue = Number(valSplit);
        const testValue = Number(testSplit);

        setPreparing(true);
        setPrepareError(null);
        setPrepareJobId(null);
        try {
            const result = await createPrepareDatasetJob({
                dataset_id: datasetId,
                sources: Array.from(selectedSources),
                targets: Array.from(selectedTargets),
                val_split: valValue,
                test_split: testValue,
                link_mode: useHardlinks ? "hardlink" : "copy",
                seed: seedValue,
                overwrite,
            });
            setPrepareJobId(result.jobId);
        } catch (err) {
            console.error("Failed to prepare dataset", err);
            setPrepareError("Failed to queue dataset build.");
        } finally {
            setPreparing(false);
        }
    };

    const handleStartTraining = async () => {
        if (!selectedDatasetId) {
            setTrainError("Select a prepared dataset.");
            return;
        }
        const epochsValue = Number.parseInt(epochs, 10);
        const batchValue = Number.parseInt(batchSize, 10);
        const workersValue = Number.parseInt(workers, 10);
        const imageValue = Number.parseInt(imageSize, 10);
        const patienceValue = Number.parseInt(patience, 10);

        if (!Number.isFinite(epochsValue) || epochsValue <= 0) {
            setTrainError("Epochs must be a positive number.");
            return;
        }
        if (!Number.isFinite(batchValue) || batchValue <= 0) {
            setTrainError("Batch size must be a positive number.");
            return;
        }
        if (!Number.isFinite(workersValue) || workersValue < 0) {
            setTrainError("Workers must be zero or higher.");
            return;
        }
        if (!Number.isFinite(imageValue) || imageValue <= 0) {
            setTrainError("Image size must be a positive number.");
            return;
        }
        if (!Number.isFinite(patienceValue) || patienceValue < 0) {
            setTrainError("Patience must be zero or higher.");
            return;
        }

        setTraining(true);
        setTrainError(null);
        setTrainJobId(null);
        try {
            const result = await createTrainModelJob({
                dataset_id: selectedDatasetId,
                model_family: modelFamily,
                model_size: modelSize,
                pretrained,
                epochs: epochsValue,
                batch_size: batchValue,
                workers: workersValue,
                image_size: imageValue,
                device,
                patience: patienceValue,
                augmentations,
                dry_run: dryRun,
            });
            setTrainJobId(result.jobId);
            setSelectedLogJobId(result.jobId);
        } catch (err) {
            console.error("Failed to start training", err);
            setTrainError("Failed to start training.");
        } finally {
            setTraining(false);
        }
    };

    return (
        <div className="flex-1 flex overflow-hidden">
            <JobsPanel />

            <div className="flex-1 flex overflow-hidden">
                <main className={ui.trainingMain}>
                    <div
                        role="tablist"
                        className={ui.trainingTabs}
                    >
                        <button
                            type="button"
                            role="tab"
                            aria-selected={activeTab === "prep"}
                            onClick={() => setActiveTab("prep")}
                            className={`${ui.trainingTab} ${
                                activeTab === "prep"
                                    ? ui.trainingTabActive
                                    : ui.trainingTabInactive
                            }`}
                        >
                            Data Preparation
                            <span className={`ml-2 ${ui.trainingMeta}`}>
                                {selectedCount} sources
                            </span>
                        </button>
                        <button
                            type="button"
                            role="tab"
                            aria-selected={activeTab === "train"}
                            onClick={() => setActiveTab("train")}
                            className={`${ui.trainingTab} ${
                                activeTab === "train"
                                    ? ui.trainingTabActive
                                    : ui.trainingTabInactive
                            }`}
                        >
                            Training
                            <span className={`ml-2 ${ui.trainingMeta}`}>
                                {datasets.length} datasets
                            </span>
                        </button>
                    </div>

                    {activeTab === "prep" ? (
                        <section className={`${ui.trainingSection} space-y-4`}>
                            <div className="flex items-center justify-between">
                                <h2 className={ui.trainingSectionTitle}>
                                    Data Preparation
                                </h2>
                                <span className={ui.trainingSectionMeta}>
                                    Selected sources: {selectedCount}
                                </span>
                            </div>
                            <TrainingDataPrepSection
                                selectedCount={selectedCount}
                                sources={sources}
                                loading={loading}
                                error={error}
                                refresh={refresh}
                                selectedSources={selectedSources}
                                toggleSource={toggleSource}
                                selectAll={selectAll}
                                clearAll={clearAll}
                                datasetId={datasetId}
                                setDatasetId={setDatasetId}
                                supportedTargets={supportedTargets}
                                selectedTargets={selectedTargets}
                                selectedTargetsCount={selectedTargetsCount}
                                toggleTarget={toggleTarget}
                                valSplit={valSplit}
                                testSplit={testSplit}
                                setValSplit={setValSplit}
                                setTestSplit={setTestSplit}
                                seed={seed}
                                setSeed={setSeed}
                                useHardlinks={useHardlinks}
                                setUseHardlinks={setUseHardlinks}
                                overwrite={overwrite}
                                setOverwrite={setOverwrite}
                                prepareError={prepareError}
                                splitError={splitError}
                                prepareJobId={prepareJobId}
                                preparing={preparing}
                                onPrepareDataset={handlePrepareDataset}
                            />
                        </section>
                    ) : (
                        <section className={`${ui.trainingSection} space-y-4`}>
                            <div className="flex items-center justify-between">
                                <h2 className={ui.trainingSectionTitle}>
                                    Training
                                </h2>
                                <span className={ui.trainingSectionMeta}>
                                    Datasets: {datasets.length}
                                </span>
                            </div>
                            <TrainingDatasetsSection
                                datasets={datasets}
                                datasetsLoading={datasetsLoading}
                                datasetsError={datasetsError}
                                selectedDatasetId={selectedDatasetId}
                                onSelectDataset={setSelectedDatasetId}
                                refreshDatasets={refreshDatasets}
                            />
                            <TrainingConfigSection
                                selectedDatasetId={selectedDatasetId}
                                modelFamily={modelFamily}
                                modelFamilies={modelFamilies}
                                onChangeModelFamily={setModelFamily}
                                modelSize={modelSize}
                                onChangeModelSize={setModelSize}
                                modelId={modelId}
                                ultralyticsVersion={ultralyticsVersion}
                                pretrained={pretrained}
                                onChangePretrained={setPretrained}
                                epochs={epochs}
                                onChangeEpochs={setEpochs}
                                batchSize={batchSize}
                                onChangeBatchSize={setBatchSize}
                                workers={workers}
                                onChangeWorkers={setWorkers}
                                imageSize={imageSize}
                                onChangeImageSize={setImageSize}
                                device={device}
                                onChangeDevice={setDevice}
                                patience={patience}
                                onChangePatience={setPatience}
                                augmentations={augmentations}
                                onChangeAugmentations={setAugmentations}
                                dryRun={dryRun}
                                onChangeDryRun={setDryRun}
                                trainError={trainError}
                                trainJobId={trainJobId}
                                training={training}
                                onStartTraining={handleStartTraining}
                            />
                            <TrainingLogsPanel
                                trainingJobs={trainingJobs}
                                selectedLogJobId={selectedLogJobId}
                                onSelectLogJob={setSelectedLogJobId}
                                logLines={logLines}
                                logStatusLabel={logStatusLabel}
                                logError={logError}
                            />
                            <TrainingMetaPanel />
                        </section>
                    )}
                </main>
            </div>
        </div>
    );
}
