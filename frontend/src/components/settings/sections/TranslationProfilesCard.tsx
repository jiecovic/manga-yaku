// src/components/settings/sections/TranslationProfilesCard.tsx
import { Field, Select } from '../../../ui/primitives';
import { ui } from '../../../ui/tokens';
import type { ModelCapability, TranslationDraftProfile } from '../types';
import { resolveModelCapability } from '../types';

type Props = {
  translationDraft: TranslationDraftProfile[];
  translationModelOptions: string[];
  translationModelCapabilities: Record<string, ModelCapability>;
  translationReasoningOptions: string[];
  translateSingleBoxUseContext: boolean;
  onUpdateTranslationProfile: (id: string, updates: Partial<TranslationDraftProfile>) => void;
  onUpdateDraft: (key: string, value: unknown) => void;
};

export function TranslationProfilesCard({
  translationDraft,
  translationModelOptions,
  translationModelCapabilities,
  translationReasoningOptions,
  translateSingleBoxUseContext,
  onUpdateTranslationProfile,
  onUpdateDraft,
}: Props) {
  return (
    <div className={ui.trainingCard}>
      <div className={ui.trainingSubTitle}>Single-box Translation LLMs</div>
      <div className="mt-3 space-y-2">
        <Field label="Use context" layout="row" labelClassName={ui.label}>
          <label className="inline-flex items-center gap-2 text-xs text-slate-300">
            <input
              type="checkbox"
              checked={translateSingleBoxUseContext}
              onChange={(e) =>
                onUpdateDraft('translation.single_box.use_context', e.target.checked)
              }
            />
            include page + volume context
          </label>
        </Field>
        <div className={`${ui.trainingHelp} ml-28`}>
          Adds sibling OCR/translations and saved page or volume memory to manual single-box
          translation.
        </div>

        {translationDraft.map((profile) => {
          const options = new Set(translationModelOptions);
          if (profile.model_id) {
            options.add(profile.model_id);
          }
          const capability = resolveModelCapability(translationModelCapabilities, profile.model_id);
          return (
            <div
              key={profile.id}
              className="flex flex-col gap-2 rounded-md border border-slate-800 bg-slate-950/60 p-2"
            >
              <label
                className={`flex items-center gap-2 text-xs ${
                  profile.enabled ? 'text-slate-200' : 'text-slate-500'
                }`}
              >
                <input
                  type="checkbox"
                  checked={profile.single_box_enabled}
                  disabled={!profile.enabled}
                  onChange={(e) =>
                    onUpdateTranslationProfile(profile.id, {
                      single_box_enabled: e.target.checked,
                      effective_enabled: profile.enabled && e.target.checked,
                    })
                  }
                />
                {profile.label}
              </label>
              <div className={ui.trainingHelp}>
                Enable this profile for manual single-box translate.
              </div>

              <div className="grid gap-2 md:grid-cols-2">
                <Field label="Model" layout="stack" labelClassName={ui.trainingLabelTiny}>
                  <Select
                    variant="training"
                    value={profile.model_id ?? ''}
                    onChange={(e) =>
                      onUpdateTranslationProfile(profile.id, {
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

                <Field label="Max output" layout="stack" labelClassName={ui.trainingLabelTiny}>
                  <input
                    className={ui.trainingInput}
                    type="number"
                    min={1}
                    value={profile.max_output_tokens ?? ''}
                    onChange={(e) =>
                      onUpdateTranslationProfile(profile.id, {
                        max_output_tokens: e.target.value === '' ? null : Number(e.target.value),
                      })
                    }
                  />
                </Field>

                <Field label="Reasoning" layout="stack" labelClassName={ui.trainingLabelTiny}>
                  <Select
                    variant="training"
                    value={profile.reasoning_effort ?? ''}
                    disabled={!capability.applies_reasoning_effort}
                    onChange={(e) =>
                      onUpdateTranslationProfile(profile.id, {
                        reasoning_effort: e.target.value || null,
                      })
                    }
                  >
                    <option value="">default</option>
                    {translationReasoningOptions.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </Select>
                </Field>

                <Field label="Temperature" layout="stack" labelClassName={ui.trainingLabelTiny}>
                  <input
                    className={ui.trainingInput}
                    type="number"
                    step="0.1"
                    min={0}
                    max={2}
                    disabled={!capability.applies_temperature}
                    value={profile.temperature ?? ''}
                    onChange={(e) =>
                      onUpdateTranslationProfile(profile.id, {
                        temperature: e.target.value === '' ? null : Number(e.target.value),
                      })
                    }
                  />
                </Field>
              </div>
              <div className="space-y-1">
                <div className={ui.trainingHelp}>
                  Model: API model used by this translation profile.
                </div>
                <div className={ui.trainingHelp}>
                  Max output: output token cap per translation attempt.
                </div>
                <div className={ui.trainingHelp}>
                  {capability.applies_reasoning_effort
                    ? 'Reasoning: active for the selected model.'
                    : 'Reasoning: inactive for the selected model.'}
                </div>
                <div className={ui.trainingHelp}>
                  {capability.applies_temperature
                    ? 'Temperature: active for the selected model.'
                    : 'Temperature: inactive for the selected model.'}
                </div>
                {capability.notes.map((note) => (
                  <div key={`${profile.id}-${note}`} className={ui.trainingHelp}>
                    {note}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
      <div className={ui.trainingHelp}>
        At least one available translation profile must stay enabled.
      </div>
    </div>
  );
}
