// src/components/settings/sections/OcrProfilesCard.tsx
import { Field, Select } from "../../../ui/primitives";
import { ui } from "../../../ui/tokens";
import type { OcrDraftProfile } from "../types";

type Props = {
    ocrDraft: OcrDraftProfile[];
    ocrModelOptions: string[];
    ocrReasoningOptions: string[];
    onUpdateOcrProfile: (id: string, updates: Partial<OcrDraftProfile>) => void;
};

export function OcrProfilesCard({
    ocrDraft,
    ocrModelOptions,
    ocrReasoningOptions,
    onUpdateOcrProfile,
}: Props) {
    return (
        <div className={ui.trainingCard}>
            <div className={ui.trainingSubTitle}>LLM OCR</div>
            <div className="mt-3 space-y-2">
                {ocrDraft.map((profile) => {
                    const isLocal = profile.kind === "local";
                    const options = new Set(ocrModelOptions);
                    if (profile.model_id) {
                        options.add(profile.model_id);
                    }
                    return (
                        <div
                            key={profile.id}
                            className="flex flex-col gap-2 rounded-md border border-slate-800 bg-slate-950/60 p-2"
                        >
                            <label
                                className={`flex items-center gap-2 text-xs ${
                                    profile.enabled
                                        ? "text-slate-200"
                                        : "text-slate-500"
                                }`}
                            >
                                <input
                                    type="checkbox"
                                    checked={profile.page_translation_enabled}
                                    disabled={!profile.enabled}
                                    onChange={(e) =>
                                        onUpdateOcrProfile(profile.id, {
                                            page_translation_enabled: e.target.checked,
                                        })
                                    }
                                />
                                {profile.label}
                            </label>
                            <div className={ui.trainingHelp}>
                                Enable or disable this profile for page OCR runs.
                            </div>

                            {isLocal ? (
                                <div className={ui.trainingLabelTiny}>
                                    Local OCR (on-device). Runtime parameters are managed
                                    by the tool.
                                </div>
                            ) : (
                                <>
                                    <div className="grid gap-2 md:grid-cols-2">
                                        <Field
                                            label="Model"
                                            layout="stack"
                                            labelClassName={ui.trainingLabelTiny}
                                        >
                                            <Select
                                                variant="training"
                                                value={profile.model_id ?? ""}
                                                onChange={(e) =>
                                                    onUpdateOcrProfile(profile.id, {
                                                        model_id: e.target.value || null,
                                                    })
                                                }
                                            >
                                                {Array.from(options).map((model) => (
                                                    <option key={model} value={model}>
                                                        {model}
                                                    </option>
                                                ))}
                                            </Select>
                                        </Field>

                                        <Field
                                            label="Max output"
                                            layout="stack"
                                            labelClassName={ui.trainingLabelTiny}
                                        >
                                            <input
                                                className={ui.trainingInput}
                                                type="number"
                                                min={1}
                                                value={profile.max_output_tokens ?? ""}
                                                onChange={(e) =>
                                                    onUpdateOcrProfile(profile.id, {
                                                        max_output_tokens:
                                                            e.target.value === ""
                                                                ? null
                                                                : Number(e.target.value),
                                                    })
                                                }
                                            />
                                        </Field>

                                        <Field
                                            label="Reasoning"
                                            layout="stack"
                                            labelClassName={ui.trainingLabelTiny}
                                        >
                                            <Select
                                                variant="training"
                                                value={profile.reasoning_effort ?? ""}
                                                onChange={(e) =>
                                                    onUpdateOcrProfile(profile.id, {
                                                        reasoning_effort:
                                                            e.target.value || null,
                                                    })
                                                }
                                            >
                                                <option value="">default</option>
                                                {ocrReasoningOptions.map((option) => (
                                                    <option key={option} value={option}>
                                                        {option}
                                                    </option>
                                                ))}
                                            </Select>
                                        </Field>

                                        <Field
                                            label="Temperature"
                                            layout="stack"
                                            labelClassName={ui.trainingLabelTiny}
                                        >
                                            <input
                                                className={ui.trainingInput}
                                                type="number"
                                                step="0.1"
                                                min={0}
                                                max={2}
                                                value={profile.temperature ?? ""}
                                                onChange={(e) =>
                                                    onUpdateOcrProfile(profile.id, {
                                                        temperature:
                                                            e.target.value === ""
                                                                ? null
                                                                : Number(e.target.value),
                                                    })
                                                }
                                            />
                                        </Field>
                                    </div>
                                    <div className="space-y-1">
                                        <div className={ui.trainingHelp}>
                                            Model: API model used by this OCR profile.
                                        </div>
                                        <div className={ui.trainingHelp}>
                                            Max output: output token cap per OCR attempt.
                                        </div>
                                        <div className={ui.trainingHelp}>
                                            Reasoning: GPT-5 reasoning level for OCR.
                                        </div>
                                        <div className={ui.trainingHelp}>
                                            Temperature: sampling randomness (if model
                                            supports it).
                                        </div>
                                    </div>
                                </>
                            )}
                        </div>
                    );
                })}
            </div>
            <div className={ui.trainingHelp}>
                Toggle which OCR profiles the page translation workflow may use.
            </div>
        </div>
    );
}
