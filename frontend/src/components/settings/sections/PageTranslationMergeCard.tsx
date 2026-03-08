// src/components/settings/sections/PageTranslationMergeCard.tsx
import { Field, Select } from "../../../ui/primitives";
import { ui } from "../../../ui/tokens";

type Props = {
    mergeMaxOutputTokens: string;
    mergeReasoningEffort: string;
    reasoningOptions: string[];
    onUpdateDraft: (key: string, value: unknown) => void;
};

export function PageTranslationMergeCard({
    mergeMaxOutputTokens,
    mergeReasoningEffort,
    reasoningOptions,
    onUpdateDraft,
}: Props) {
    return (
        <div className={ui.trainingCard}>
            <div className={ui.trainingSubTitle}>Page Translation Merge Stage</div>
            <div className="mt-3 space-y-3">
                <Field label="Reasoning" layout="row" labelClassName={ui.label}>
                    <Select
                        value={mergeReasoningEffort}
                        onChange={(e) =>
                            onUpdateDraft(
                                "page_translation.merge.reasoning_effort",
                                e.target.value,
                            )
                        }
                    >
                        {reasoningOptions.map((option) => (
                            <option key={`merge-${option}`} value={option}>
                                {option}
                            </option>
                        ))}
                    </Select>
                </Field>
                <div className={`${ui.trainingHelp} ml-28`}>
                    Reasoning level for stage-2 continuity merge.
                </div>

                <Field label="Max output" layout="row" labelClassName={ui.label}>
                    <input
                        className={ui.trainingInput}
                        type="number"
                        min={128}
                        max={4096}
                        value={mergeMaxOutputTokens}
                        onChange={(e) =>
                            onUpdateDraft(
                                "page_translation.merge.max_output_tokens",
                                e.target.value,
                            )
                        }
                    />
                </Field>
                <div className={`${ui.trainingHelp} ml-28`}>
                    Output token cap for merge JSON (characters, threads, glossary,
                    story summary).
                </div>
            </div>
        </div>
    );
}
