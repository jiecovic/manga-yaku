// src/components/translation/RightSidebarProfilesSection.tsx
import type { OcrProvider, TranslationProvider } from "../../types";
import { CollapsibleSection } from "./CollapsibleSection";
import { ui } from "../../ui/tokens";
import { Field, Select } from "../../ui/primitives";

interface ProfilesSectionProps {
    ocrProviders: OcrProvider[];
    translationProviders: TranslationProvider[];
    ocrEngineId: string;
    translationProfileId: string;
    onChangeOcrEngine: (id: string) => void;
    onChangeTranslationProfile: (id: string) => void;

}

export function RightSidebarProfilesSection({
    ocrProviders,
    translationProviders,
    ocrEngineId,
    translationProfileId,
    onChangeOcrEngine,
    onChangeTranslationProfile,
}: ProfilesSectionProps) {
    const loadingOcrProviders = ocrProviders.length === 0;
    const enabledOcrProviders = ocrProviders.filter((p) => p.enabled);

    const loadingTranslationProviders = translationProviders.length === 0;
    const enabledTranslationProviders = translationProviders.filter(
        (p) => p.enabled,
    );

    return (
        <CollapsibleSection title="Profiles & Options" defaultOpen>
            <div className="space-y-3">
                {/* OCR */}
                <Field label="OCR Profile" layout="row" labelClassName={ui.label}>
                    {loadingOcrProviders && (
                        <div className={ui.mutedTextXs}>Loading...</div>
                    )}

                    {!loadingOcrProviders &&
                        enabledOcrProviders.length === 0 && (
                            <div className={ui.mutedTextXs}>
                                None available.
                            </div>
                        )}

                    {!loadingOcrProviders &&
                        enabledOcrProviders.length > 0 && (
                            <Select
                                value={ocrEngineId}
                                onChange={(e) =>
                                    onChangeOcrEngine(e.target.value)
                                }
                            >
                                {enabledOcrProviders.map((p) => (
                                    <option key={p.id} value={p.id}>
                                        {p.label}
                                    </option>
                                ))}
                            </Select>
                        )}
                </Field>

                {/* Translation */}
                <Field label="Translation" layout="row" labelClassName={ui.label}>
                    {loadingTranslationProviders && (
                        <div className={ui.mutedTextXs}>Loading...</div>
                    )}

                    {!loadingTranslationProviders &&
                        enabledTranslationProviders.length === 0 && (
                            <div className={ui.mutedTextXs}>
                                None available.
                            </div>
                        )}

                    {!loadingTranslationProviders &&
                        enabledTranslationProviders.length > 0 && (
                            <Select
                                value={translationProfileId}
                                onChange={(e) =>
                                    onChangeTranslationProfile(e.target.value)
                                }
                            >
                                {enabledTranslationProviders.map((p) => (
                                    <option key={p.id} value={p.id}>
                                        {p.label}
                                    </option>
                                ))}
                            </Select>
                        )}
                </Field>

            </div>
        </CollapsibleSection>
    );
}
