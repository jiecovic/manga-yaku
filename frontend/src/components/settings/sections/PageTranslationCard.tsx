// src/components/settings/sections/PageTranslationCard.tsx
import { Field, Select } from "../../../ui/primitives";
import { ui } from "../../../ui/tokens";
import type { ModelCapability, PageTranslationDraft } from "../types";

type DetectionOption = {
    id: string;
    label: string;
    enabled?: boolean;
};

type Props = {
    pageTranslationDraft: PageTranslationDraft | null;
    pageTranslationModelOptions: string[];
    pageTranslationSelectedCapability: ModelCapability;
    pageTranslationReasoningOptions: string[];
    onUpdatePageTranslationDraft: (key: keyof PageTranslationDraft, value: string) => void;
    pageTranslationDetectionProfileId: string;
    includePriorContextSummary: boolean;
    includePriorCharacters: boolean;
    includePriorOpenThreads: boolean;
    includePriorGlossary: boolean;
    onUpdateDraft: (key: string, value: unknown) => void;
    pageTranslationDetectionLoading: boolean;
    pageTranslationDetectionOptions: DetectionOption[];
    hasPageTranslationDetectionOptions: boolean;
};

export function PageTranslationCard({
    pageTranslationDraft,
    pageTranslationModelOptions,
    pageTranslationSelectedCapability,
    pageTranslationReasoningOptions,
    onUpdatePageTranslationDraft,
    pageTranslationDetectionProfileId,
    includePriorContextSummary,
    includePriorCharacters,
    includePriorOpenThreads,
    includePriorGlossary,
    onUpdateDraft,
    pageTranslationDetectionLoading,
    pageTranslationDetectionOptions,
    hasPageTranslationDetectionOptions,
}: Props) {
    return (
        <div className={ui.trainingCard}>
            <div className={ui.trainingSubTitle}>Page Translation Workflow</div>
            <div className="mt-3 space-y-3">
                <div className={ui.trainingHelp}>
                    These settings affect the queued `page_translation`
                    workflow, not the interactive chat agent.
                </div>

                <Field label="Model" layout="row" labelClassName={ui.label}>
                    <Select
                        value={pageTranslationDraft?.model_id ?? ""}
                        onChange={(e) => onUpdatePageTranslationDraft("model_id", e.target.value)}
                    >
                        {pageTranslationModelOptions.map((model) => (
                            <option key={model} value={model}>
                                {model}
                            </option>
                        ))}
                    </Select>
                </Field>
                <div className={`${ui.trainingHelp} ml-28`}>
                    Model used by the page translation workflow. Manual
                    single-box translate uses the sidebar Translation profile.
                </div>

                <Field label="Detection" layout="row" labelClassName={ui.label}>
                    <Select
                        value={pageTranslationDetectionProfileId}
                        onChange={(e) =>
                            onUpdateDraft(
                                "page_translation.detection_profile_id",
                                e.target.value,
                            )
                        }
                        disabled={pageTranslationDetectionLoading}
                    >
                        <option value="">Use sidebar selection</option>
                        {pageTranslationDetectionOptions.map((profile) => (
                            <option key={profile.id} value={profile.id}>
                                {profile.label}
                            </option>
                        ))}
                    </Select>
                </Field>
                <div className={`${ui.trainingHelp} ml-28`}>
                    Optional override for page translation detection. Leave empty to
                    use the sidebar selection.
                </div>
                {!pageTranslationDetectionLoading && !hasPageTranslationDetectionOptions && (
                    <div className={ui.trainingHelp}>
                        No text detection models available. Train a model to enable
                        page translation detection.
                    </div>
                )}

                <Field label="Reasoning" layout="row" labelClassName={ui.label}>
                    <Select
                        value={pageTranslationDraft?.reasoning_effort ?? "low"}
                        disabled={!pageTranslationSelectedCapability.applies_reasoning_effort}
                        onChange={(e) =>
                            onUpdatePageTranslationDraft("reasoning_effort", e.target.value)
                        }
                    >
                        {pageTranslationReasoningOptions.map((option) => (
                            <option key={option} value={option}>
                                {option}
                            </option>
                        ))}
                    </Select>
                </Field>
                <div className={`${ui.trainingHelp} ml-28`}>
                    {pageTranslationSelectedCapability.applies_reasoning_effort
                        ? "Reasoning level for page translation runs with reasoning-capable models."
                        : "Reasoning effort is not used for the selected model."}
                </div>
                {pageTranslationSelectedCapability.notes.map((note) => (
                    <div key={`pt-reason-${note}`} className={`${ui.trainingHelp} ml-28`}>
                        {note}
                    </div>
                ))}

                <Field label="Volume memory" layout="row" labelClassName={ui.label}>
                    <div className="flex flex-col gap-1 text-xs text-slate-300">
                        <div className="text-slate-300">page image is always included</div>
                        <label className="inline-flex items-center gap-2">
                            <input
                                type="checkbox"
                                checked={includePriorContextSummary}
                                onChange={(e) =>
                                    onUpdateDraft(
                                        "page_translation.include_prior_context_summary",
                                        e.target.checked,
                                    )
                                }
                            />
                            include story summary
                        </label>
                        <label className="inline-flex items-center gap-2">
                            <input
                                type="checkbox"
                                checked={includePriorCharacters}
                                onChange={(e) =>
                                    onUpdateDraft(
                                        "page_translation.include_prior_characters",
                                        e.target.checked,
                                    )
                                }
                            />
                            include active characters
                        </label>
                        <label className="inline-flex items-center gap-2">
                            <input
                                type="checkbox"
                                checked={includePriorOpenThreads}
                                onChange={(e) =>
                                    onUpdateDraft(
                                        "page_translation.include_prior_open_threads",
                                        e.target.checked,
                                    )
                                }
                            />
                            include open threads
                        </label>
                        <label className="inline-flex items-center gap-2">
                            <input
                                type="checkbox"
                                checked={includePriorGlossary}
                                onChange={(e) =>
                                    onUpdateDraft(
                                        "page_translation.include_prior_glossary",
                                        e.target.checked,
                                    )
                                }
                            />
                            include glossary
                        </label>
                    </div>
                </Field>
                <div className={`${ui.trainingHelp} ml-28`}>
                    Controls which saved volume memory blocks are injected into the
                    page translation prompt.
                </div>

                <Field label="Max output" layout="row" labelClassName={ui.label}>
                    <input
                        className={ui.trainingInput}
                        type="number"
                        min={128}
                        value={pageTranslationDraft?.max_output_tokens ?? ""}
                        onChange={(e) =>
                            onUpdatePageTranslationDraft("max_output_tokens", e.target.value)
                        }
                    />
                </Field>
                <div className={`${ui.trainingHelp} ml-28`}>
                    Output token cap for page translation model responses.
                </div>

                <Field label="Temperature" layout="row" labelClassName={ui.label}>
                    <input
                        className={ui.trainingInput}
                        type="number"
                        step="0.1"
                        min={0}
                        max={2}
                        disabled={!pageTranslationSelectedCapability.applies_temperature}
                        value={pageTranslationDraft?.temperature ?? ""}
                        onChange={(e) =>
                            onUpdatePageTranslationDraft("temperature", e.target.value)
                        }
                    />
                </Field>
                <div className={`${ui.trainingHelp} ml-28`}>
                    {pageTranslationSelectedCapability.applies_temperature
                        ? "Sampling randomness for page translation when the selected model supports temperature."
                        : "Temperature is inactive for the selected model."}
                </div>
                {pageTranslationSelectedCapability.notes.map((note) => (
                    <div key={`pt-temp-${note}`} className={`${ui.trainingHelp} ml-28`}>
                        {note}
                    </div>
                ))}
            </div>
        </div>
    );
}
