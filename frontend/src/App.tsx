// src/App.tsx
import { useState } from "react";

import { TopNav } from "./components/TopNav";
import { HealthBanner } from "./components/HealthBanner";
import { LogsLayout } from "./components/debug/LogsLayout";
import { SettingsLayout } from "./components/settings/SettingsLayout";
import { TranslateLayout } from "./components/translation/TranslateLayout";
import { TrainingLayout } from "./components/training/TrainingLayout";
import { WorkflowSettingsProvider } from "./context/WorkflowSettingsContext";
import { HealthProvider } from "./context/HealthContext";
import { JobsProvider } from "./context/JobsProvider";
import { LibraryProvider } from "./context/LibraryProvider";
import { SettingsProvider } from "./context/SettingsContext";
import { ui } from "./ui/tokens";

type AppMode = "translate" | "train" | "logs" | "settings";

/**
 * App: wires global state + providers, then renders the main layout.
 */
export default function App() {
    const [mode, setMode] = useState<AppMode>("translate");

    return (
        <HealthProvider>
            <SettingsProvider>
                <WorkflowSettingsProvider>
                    <LibraryProvider>
                        <JobsProvider>
                            <div className={ui.appRoot}>
                                <HealthBanner />
                                <TopNav mode={mode} onChangeMode={setMode} />
                                {mode === "translate" ? (
                                    <TranslateLayout />
                                ) : mode === "train" ? (
                                    <TrainingLayout />
                                ) : mode === "logs" ? (
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
