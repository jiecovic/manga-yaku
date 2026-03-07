// src/components/settings/SettingsLayout.tsx
import { Button } from "../../ui/primitives";
import { ui } from "../../ui/tokens";
import { JobsPanel } from "../JobsPanel";
import { ChatAgentCard } from "./sections/ChatAgentCard";
import { DetectionDefaultsCard } from "./sections/DetectionDefaultsCard";
import { AgentMergeCard } from "./sections/AgentMergeCard";
import { OcrParallelismCard } from "./sections/OcrParallelismCard";
import { OcrProfilesCard } from "./sections/OcrProfilesCard";
import { TranslationAgentCard } from "./sections/TranslationAgentCard";
import { TranslationProfilesCard } from "./sections/TranslationProfilesCard";
import { SettingsTabs } from "./SettingsTabs";
import { useSettingsLayoutState } from "./useSettingsLayoutState";

export function SettingsLayout() {
    const {
        loading,
        error,
        activeTab,
        setActiveTab,
        autoSaveEnabled,
        setAutoSaveEnabled,
        baseAutoSaving,
        agentAutoSaving,
        ocrAutoSaving,
        translationAutoSaving,
        saving,
        restartingBackend,
        saveMessage,
        handleSave,
        handleRestartBackend,
        handleRefresh,
        confThreshold,
        iouThreshold,
        containmentThreshold,
        updateDraft,
        agentDraft,
        agentModelOptions,
        agentReasoningOptions,
        updateAgentDraft,
        agentDetectionProfileId,
        translateSingleBoxUseContext,
        includePriorContextSummary,
        includePriorCharacters,
        includePriorOpenThreads,
        includePriorGlossary,
        agentChatMaxTurns,
        agentChatMaxOutputTokens,
        mergeMaxOutputTokens,
        mergeReasoningEffort,
        agentDetectionLoading,
        agentDetectionOptions,
        hasAgentDetectionOptions,
        translationDraft,
        translationModelOptions,
        translationReasoningOptions,
        updateTranslationProfile,
        ocrDraft,
        ocrModelOptions,
        ocrReasoningOptions,
        updateOcrProfile,
        ocrParallelismLocal,
        ocrParallelismRemote,
        ocrParallelismMaxWorkers,
        ocrParallelismLeaseSeconds,
        ocrParallelismTaskTimeoutSeconds,
    } = useSettingsLayoutState();

    return (
        <div className="flex-1 flex overflow-hidden">
            <JobsPanel />
            <main className={ui.trainingMain}>
                <section className={ui.trainingSection}>
                    <div className={ui.trainingSectionHeader}>
                        <div>
                            <div className={ui.trainingSectionTitle}>Settings</div>
                            <div className={ui.trainingSectionMeta}>
                                Persisted in the database
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            <label className="inline-flex items-center gap-2 rounded-md border border-slate-700 px-2 py-1 text-[11px] text-slate-300">
                                <input
                                    type="checkbox"
                                    checked={autoSaveEnabled}
                                    onChange={(e) => setAutoSaveEnabled(e.target.checked)}
                                />
                                Auto-save
                            </label>
                            <Button
                                type="button"
                                variant="ghostSmall"
                                onClick={handleRefresh}
                                disabled={loading}
                            >
                                Refresh
                            </Button>
                            <Button
                                type="button"
                                variant="ghostSmall"
                                onClick={handleRestartBackend}
                                disabled={loading || restartingBackend}
                            >
                                {restartingBackend ? "Restarting..." : "Restart backend"}
                            </Button>
                            <Button
                                type="button"
                                variant="actionEmerald"
                                onClick={handleSave}
                                disabled={loading || saving}
                            >
                                {saving ? "Saving..." : "Save changes"}
                            </Button>
                        </div>
                    </div>

                    {error && <div className={ui.trainingError}>{error}</div>}
                    {saveMessage && (
                        <div className={ui.trainingMetaSmall}>{saveMessage}</div>
                    )}
                    {!autoSaveEnabled && (
                        <div className={ui.trainingMetaSmall}>
                            Auto-save disabled. Use “Save changes” to persist edits.
                        </div>
                    )}
                    {baseAutoSaving && (
                        <div className={ui.trainingMetaSmall}>
                            Saving base settings…
                        </div>
                    )}
                    {agentAutoSaving && (
                        <div className={ui.trainingMetaSmall}>
                            Saving translation agent settings…
                        </div>
                    )}
                    {ocrAutoSaving && (
                        <div className={ui.trainingMetaSmall}>Saving OCR settings…</div>
                    )}
                    {translationAutoSaving && (
                        <div className={ui.trainingMetaSmall}>
                            Saving translation profile settings…
                        </div>
                    )}

                    <SettingsTabs
                        activeTab={activeTab}
                        onChangeTab={setActiveTab}
                    />

                    <div className="space-y-4">
                        {activeTab === "agent" && (
                            <>
                                <ChatAgentCard
                                    agentChatMaxTurns={agentChatMaxTurns}
                                    agentChatMaxOutputTokens={agentChatMaxOutputTokens}
                                    onUpdateDraft={updateDraft}
                                />
                                <TranslationAgentCard
                                    agentDraft={agentDraft}
                                    agentModelOptions={agentModelOptions}
                                    agentReasoningOptions={agentReasoningOptions}
                                    onUpdateAgentDraft={updateAgentDraft}
                                    agentDetectionProfileId={agentDetectionProfileId}
                                    includePriorContextSummary={includePriorContextSummary}
                                    includePriorCharacters={includePriorCharacters}
                                    includePriorOpenThreads={includePriorOpenThreads}
                                    includePriorGlossary={includePriorGlossary}
                                    onUpdateDraft={updateDraft}
                                    agentDetectionLoading={agentDetectionLoading}
                                    agentDetectionOptions={agentDetectionOptions}
                                    hasAgentDetectionOptions={hasAgentDetectionOptions}
                                />
                                <AgentMergeCard
                                    mergeMaxOutputTokens={mergeMaxOutputTokens}
                                    mergeReasoningEffort={mergeReasoningEffort}
                                    reasoningOptions={agentReasoningOptions}
                                    onUpdateDraft={updateDraft}
                                />
                            </>
                        )}

                        {activeTab === "translation" && (
                            <>
                                <TranslationProfilesCard
                                    translationDraft={translationDraft}
                                    translationModelOptions={translationModelOptions}
                                    translationReasoningOptions={translationReasoningOptions}
                                    translateSingleBoxUseContext={translateSingleBoxUseContext}
                                    onUpdateTranslationProfile={updateTranslationProfile}
                                    onUpdateDraft={updateDraft}
                                />
                            </>
                        )}

                        {activeTab === "detection" && (
                            <DetectionDefaultsCard
                                confThreshold={confThreshold}
                                iouThreshold={iouThreshold}
                                containmentThreshold={containmentThreshold}
                                onUpdateDraft={updateDraft}
                            />
                        )}

                        {activeTab === "ocr" && (
                            <>
                                <OcrProfilesCard
                                    ocrDraft={ocrDraft}
                                    ocrModelOptions={ocrModelOptions}
                                    ocrReasoningOptions={ocrReasoningOptions}
                                    onUpdateOcrProfile={updateOcrProfile}
                                />
                                <OcrParallelismCard
                                    ocrParallelismLocal={ocrParallelismLocal}
                                    ocrParallelismRemote={ocrParallelismRemote}
                                    ocrParallelismMaxWorkers={ocrParallelismMaxWorkers}
                                    ocrParallelismLeaseSeconds={ocrParallelismLeaseSeconds}
                                    ocrParallelismTaskTimeoutSeconds={ocrParallelismTaskTimeoutSeconds}
                                    onUpdateDraft={updateDraft}
                                />
                            </>
                        )}
                    </div>
                </section>
            </main>
        </div>
    );
}
