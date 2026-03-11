// src/components/settings/SettingsTabs.tsx
import { ui } from '../../ui/tokens';

export type SettingsTab = 'llm' | 'translation' | 'detection' | 'ocr';

type Props = {
  activeTab: SettingsTab;
  onChangeTab: (tab: SettingsTab) => void;
};

export function SettingsTabs({ activeTab, onChangeTab }: Props) {
  return (
    <div role="tablist" aria-label="Settings categories" className={ui.trainingTabs}>
      <button
        type="button"
        role="tab"
        aria-selected={activeTab === 'llm'}
        onClick={() => onChangeTab('llm')}
        className={`${ui.trainingTab} ${
          activeTab === 'llm' ? ui.trainingTabActive : ui.trainingTabInactive
        }`}
      >
        LLM
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={activeTab === 'translation'}
        onClick={() => onChangeTab('translation')}
        className={`${ui.trainingTab} ${
          activeTab === 'translation' ? ui.trainingTabActive : ui.trainingTabInactive
        }`}
      >
        Translation
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={activeTab === 'detection'}
        onClick={() => onChangeTab('detection')}
        className={`${ui.trainingTab} ${
          activeTab === 'detection' ? ui.trainingTabActive : ui.trainingTabInactive
        }`}
      >
        Detection
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={activeTab === 'ocr'}
        onClick={() => onChangeTab('ocr')}
        className={`${ui.trainingTab} ${
          activeTab === 'ocr' ? ui.trainingTabActive : ui.trainingTabInactive
        }`}
      >
        OCR
      </button>
    </div>
  );
}
