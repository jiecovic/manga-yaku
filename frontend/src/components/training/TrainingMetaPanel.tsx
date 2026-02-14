// src/components/training/TrainingMetaPanel.tsx
import { ui } from "../../ui/tokens";
import { EmptyState } from "../../ui/primitives";

export function TrainingMetaPanel() {
    return (
        <>
            <section className={ui.trainingSection}>
                <h2 className={`${ui.trainingSectionTitle} mb-3`}>
                    Annotations
                </h2>
                <div className={`grid grid-cols-2 gap-3 ${ui.trainingBody}`}>
                    <div className={ui.trainingCard}>
                        <div
                            className={`${ui.trainingLabelSmall} uppercase tracking-wide`}
                        >
                            Labeled pages
                        </div>
                        <div className={`mt-2 ${ui.trainingStatValue}`}>
                            0
                        </div>
                    </div>
                    <div className={ui.trainingCard}>
                        <div
                            className={`${ui.trainingLabelSmall} uppercase tracking-wide`}
                        >
                            Unreviewed edits
                        </div>
                        <div className={`mt-2 ${ui.trainingStatValue}`}>
                            0
                        </div>
                    </div>
                </div>
                <div className={`mt-3 ${ui.trainingHelp}`}>
                    Import Manga109s annotations or promote reviewed volumes
                    into training.
                </div>
            </section>
            <section className={ui.trainingSection}>
                <h2 className={`${ui.trainingSectionTitle} mb-3`}>
                    Validation
                </h2>
                <div className={`flex items-center justify-between ${ui.trainingBody}`}>
                    <span>Last eval run</span>
                    <span className={ui.trainingLabelSmall}>Not run yet</span>
                </div>
                <EmptyState className="mt-3 h-28">
                    Metrics will appear after the first run.
                </EmptyState>
            </section>
        </>
    );
}
