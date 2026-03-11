// src/App.tsx
import { useState } from 'react';
import { LogsLayout } from './components/debug/LogsLayout';
import { HealthBanner } from './components/HealthBanner';
import { SettingsLayout } from './components/settings/SettingsLayout';
import { TopNav } from './components/TopNav';
import { TrainingLayout } from './components/training/TrainingLayout';
import { TranslateLayout } from './components/translation/TranslateLayout';
import { HealthProvider } from './context/HealthContext';
import { JobsProvider } from './context/JobsProvider';
import { LibraryProvider } from './context/LibraryProvider';
import { SettingsProvider } from './context/SettingsContext';
import { WorkflowSettingsProvider } from './context/WorkflowSettingsContext';
import { ui } from './ui/tokens';

type AppMode = 'translate' | 'train' | 'logs' | 'settings';

/**
 * App: wires global state + providers, then renders the main layout.
 */
export default function App() {
  const [mode, setMode] = useState<AppMode>('translate');

  return (
    <HealthProvider>
      <SettingsProvider>
        <WorkflowSettingsProvider>
          <LibraryProvider>
            <JobsProvider>
              <div className={ui.appRoot}>
                <HealthBanner />
                <TopNav mode={mode} onChangeMode={setMode} />
                {mode === 'translate' ? (
                  <TranslateLayout />
                ) : mode === 'train' ? (
                  <TrainingLayout />
                ) : mode === 'logs' ? (
                  <LogsLayout />
                ) : (
                  <SettingsLayout />
                )}
              </div>
            </JobsProvider>
          </LibraryProvider>
        </WorkflowSettingsProvider>
      </SettingsProvider>
    </HealthProvider>
  );
}
