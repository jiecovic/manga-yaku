import { Field } from "../../../ui/primitives";
import { ui } from "../../../ui/tokens";

type Props = {
    confThreshold: string;
    iouThreshold: string;
    containmentThreshold: string;
    onUpdateDraft: (key: string, value: unknown) => void;
};

export function DetectionDefaultsCard({
    confThreshold,
    iouThreshold,
    containmentThreshold,
    onUpdateDraft,
}: Props) {
    return (
        <div className={ui.trainingCard}>
            <div className={ui.trainingSubTitle}>Detection Defaults (YOLO)</div>
            <div className="mt-3 space-y-3">
                <Field label="Conf threshold" layout="row" labelClassName={ui.label}>
                    <input
                        className={ui.trainingInput}
                        type="number"
                        step="0.01"
                        min={0}
                        max={1}
                        value={confThreshold}
                        onChange={(e) =>
                            onUpdateDraft("detection.conf_threshold", e.target.value)
                        }
                    />
                </Field>

                <Field label="IOU threshold" layout="row" labelClassName={ui.label}>
                    <input
                        className={ui.trainingInput}
                        type="number"
                        step="0.01"
                        min={0}
                        max={1}
                        value={iouThreshold}
                        onChange={(e) =>
                            onUpdateDraft("detection.iou_threshold", e.target.value)
                        }
                    />
                </Field>
                <Field label="Containment" layout="row" labelClassName={ui.label}>
                    <input
                        className={ui.trainingInput}
                        type="number"
                        step="0.01"
                        min={0}
                        max={1}
                        value={containmentThreshold}
                        onChange={(e) =>
                            onUpdateDraft(
                                "detection.containment_threshold",
                                e.target.value,
                            )
                        }
                    />
                </Field>
                <div className={ui.trainingHelp}>
                    Leave blank to use Ultralytics defaults (conf 0.25, IoU 0.45,
                    containment 0.9).
                </div>
            </div>
        </div>
    );
}
