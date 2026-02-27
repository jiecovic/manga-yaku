import { Field, Select } from "../../../ui/primitives";
import { ui } from "../../../ui/tokens";
import type { AgentDraft } from "../types";

type DetectionOption = {
    id: string;
    label: string;
    enabled?: boolean;
};

type Props = {
    agentDraft: AgentDraft | null;
    agentModelOptions: string[];
    agentReasoningOptions: string[];
    onUpdateAgentDraft: (key: keyof AgentDraft, value: string) => void;
    agentDetectionProfileId: string;
    translateSingleBoxUseContext: boolean;
    includePriorContextSummary: boolean;
    includePriorCharacters: boolean;
    includePriorOpenThreads: boolean;
    includePriorGlossary: boolean;
    onUpdateDraft: (key: string, value: unknown) => void;
    agentDetectionLoading: boolean;
    agentDetectionOptions: DetectionOption[];
    hasAgentDetectionOptions: boolean;
};

export function TranslationAgentCard({
    agentDraft,
    agentModelOptions,
    agentReasoningOptions,
    onUpdateAgentDraft,
    agentDetectionProfileId,
    translateSingleBoxUseContext,
    includePriorContextSummary,
    includePriorCharacters,
    includePriorOpenThreads,
    includePriorGlossary,
    onUpdateDraft,
    agentDetectionLoading,
    agentDetectionOptions,
    hasAgentDetectionOptions,
}: Props) {
    return (
        <div className={ui.trainingCard}>
            <div className={ui.trainingSubTitle}>Translation Agent</div>
            <div className="mt-3 space-y-3">
                <Field label="Model" layout="row" labelClassName={ui.label}>
                    <Select
                        value={agentDraft?.model_id ?? ""}
                        onChange={(e) => onUpdateAgentDraft("model_id", e.target.value)}
                    >
                        {agentModelOptions.map((model) => (
                            <option key={model} value={model}>
                                {model}
                            </option>
                        ))}
                    </Select>
                </Field>
                <div className={`${ui.trainingHelp} ml-28`}>
                    Model used by the Agent Translate page workflow. Manual
                    single-box translate uses the sidebar Translation profile.
                </div>

                <Field label="Detection" layout="row" labelClassName={ui.label}>
                    <Select
                        value={agentDetectionProfileId}
                        onChange={(e) =>
                            onUpdateDraft(
                                "agent.translate.detection_profile_id",
                                e.target.value,
                            )
                        }
                        disabled={agentDetectionLoading}
                    >
                        <option value="">Use sidebar selection</option>
                        {agentDetectionOptions.map((profile) => (
                            <option key={profile.id} value={profile.id}>
                                {profile.label}
                            </option>
                        ))}
                    </Select>
                </Field>
                <div className={`${ui.trainingHelp} ml-28`}>
                    Optional override for Agent Translate detection. Leave empty to
                    use the sidebar selection.
                </div>
                {!agentDetectionLoading && !hasAgentDetectionOptions && (
                    <div className={ui.trainingHelp}>
                        No text detection models available. Train a model to enable
                        agent detection.
                    </div>
                )}

                <Field label="Reasoning" layout="row" labelClassName={ui.label}>
                    <Select
                        value={agentDraft?.reasoning_effort ?? "low"}
                        onChange={(e) =>
                            onUpdateAgentDraft("reasoning_effort", e.target.value)
                        }
                    >
                        {agentReasoningOptions.map((option) => (
                            <option key={option} value={option}>
                                {option}
                            </option>
                        ))}
                    </Select>
                </Field>
                <div className={`${ui.trainingHelp} ml-28`}>
                    Reasoning level for Agent Translate runs (GPT-5 models only).
                </div>

                <Field
                    label="Single-box context"
                    layout="row"
                    labelClassName={ui.label}
                >
                    <label className="inline-flex items-center gap-2 text-xs text-slate-300">
                        <input
                            type="checkbox"
                            checked={translateSingleBoxUseContext}
                            onChange={(e) =>
                                onUpdateDraft(
                                    "translation.single_box.use_context",
                                    e.target.checked,
                                )
                            }
                        />
                        include page + volume context
                    </label>
                </Field>
                <div className={`${ui.trainingHelp} ml-28`}>
                    Adds sibling OCR/translations and saved page or volume memory to
                    the prompt.
                </div>

                <Field
                    label="Agent memory"
                    layout="row"
                    labelClassName={ui.label}
                >
                    <div className="flex flex-col gap-1 text-xs text-slate-300">
                        <div className="text-slate-300">page image is always included</div>
                        <label className="inline-flex items-center gap-2">
                            <input
                                type="checkbox"
                                checked={includePriorContextSummary}
                                onChange={(e) =>
                                    onUpdateDraft(
                                        "agent.translate.include_prior_context_summary",
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
                                        "agent.translate.include_prior_characters",
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
                                        "agent.translate.include_prior_open_threads",
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
                                        "agent.translate.include_prior_glossary",
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
                    Agent Translate page prompt.
                </div>

                <Field label="Max output" layout="row" labelClassName={ui.label}>
                    <input
                        className={ui.trainingInput}
                        type="number"
                        min={128}
                        value={agentDraft?.max_output_tokens ?? ""}
                        onChange={(e) =>
                            onUpdateAgentDraft("max_output_tokens", e.target.value)
                        }
                    />
                </Field>
                <div className={`${ui.trainingHelp} ml-28`}>
                    Output token cap for Agent Translate model responses.
                </div>

                <Field label="Temperature" layout="row" labelClassName={ui.label}>
                    <input
                        className={ui.trainingInput}
                        type="number"
                        step="0.1"
                        min={0}
                        max={2}
                        value={agentDraft?.temperature ?? ""}
                        onChange={(e) =>
                            onUpdateAgentDraft("temperature", e.target.value)
                        }
                    />
                </Field>
                <div className={`${ui.trainingHelp} ml-28`}>
                    Sampling randomness for Agent Translate when the model supports
                    temperature.
                </div>
                <div className={`${ui.trainingHelp} ml-28`}>
                    Temperature is ignored by GPT-5 models.
                </div>
            </div>
        </div>
    );
}
