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
                <div className={ui.trainingHelp}>
                    Temperature is ignored by GPT-5 models.
                </div>
            </div>
        </div>
    );
}
