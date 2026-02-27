import { Field } from "../../../ui/primitives";
import { ui } from "../../../ui/tokens";

type Props = {
    ocrParallelismLocal: string;
    ocrParallelismRemote: string;
    ocrParallelismMaxWorkers: string;
    ocrParallelismLeaseSeconds: string;
    ocrParallelismTaskTimeoutSeconds: string;
    onUpdateDraft: (key: string, value: unknown) => void;
};

export function OcrParallelismCard({
    ocrParallelismLocal,
    ocrParallelismRemote,
    ocrParallelismMaxWorkers,
    ocrParallelismLeaseSeconds,
    ocrParallelismTaskTimeoutSeconds,
    onUpdateDraft,
}: Props) {
    return (
        <div className={ui.trainingCard}>
            <div className={ui.trainingSubTitle}>OCR Worker Parallelism</div>
            <div className="mt-3 space-y-3">
                <Field label="Local" layout="row" labelClassName={ui.label}>
                    <input
                        className={ui.trainingInput}
                        type="number"
                        min={1}
                        max={32}
                        value={ocrParallelismLocal}
                        onChange={(e) =>
                            onUpdateDraft("ocr.parallelism.local", e.target.value)
                        }
                    />
                </Field>
                <div className={`${ui.trainingHelp} ml-28`}>
                    Max concurrent local OCR tasks (manga-ocr/on-device).
                </div>
                <Field label="Remote" layout="row" labelClassName={ui.label}>
                    <input
                        className={ui.trainingInput}
                        type="number"
                        min={1}
                        max={32}
                        value={ocrParallelismRemote}
                        onChange={(e) =>
                            onUpdateDraft("ocr.parallelism.remote", e.target.value)
                        }
                    />
                </Field>
                <div className={`${ui.trainingHelp} ml-28`}>
                    Max concurrent remote OCR tasks (LLM/API profiles).
                </div>
                <Field label="Max workers" layout="row" labelClassName={ui.label}>
                    <input
                        className={ui.trainingInput}
                        type="number"
                        min={1}
                        max={64}
                        value={ocrParallelismMaxWorkers}
                        onChange={(e) =>
                            onUpdateDraft("ocr.parallelism.max_workers", e.target.value)
                        }
                    />
                </Field>
                <div className={`${ui.trainingHelp} ml-28`}>
                    Global cap for worker loops claiming OCR tasks.
                </div>
                <Field label="Lease (s)" layout="row" labelClassName={ui.label}>
                    <input
                        className={ui.trainingInput}
                        type="number"
                        min={30}
                        max={3600}
                        value={ocrParallelismLeaseSeconds}
                        onChange={(e) =>
                            onUpdateDraft("ocr.parallelism.lease_seconds", e.target.value)
                        }
                    />
                </Field>
                <div className={`${ui.trainingHelp} ml-28`}>
                    Task claim validity window before stale running tasks can be
                    re-queued.
                </div>
                <Field label="Timeout (s)" layout="row" labelClassName={ui.label}>
                    <input
                        className={ui.trainingInput}
                        type="number"
                        min={15}
                        max={3600}
                        value={ocrParallelismTaskTimeoutSeconds}
                        onChange={(e) =>
                            onUpdateDraft(
                                "ocr.parallelism.task_timeout_seconds",
                                e.target.value,
                            )
                        }
                    />
                </Field>
                <div className={`${ui.trainingHelp} ml-28`}>
                    Hard runtime limit per OCR task attempt.
                </div>
                <div className={ui.trainingHelp}>
                    Local = on-device OCR (manga-ocr). Remote = API OCR (LLM
                    profiles).
                </div>
                <div className={ui.trainingHelp}>
                    Effective workers = min(local + remote, max workers).
                </div>
            </div>
        </div>
    );
}
