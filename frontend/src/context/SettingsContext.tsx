// src/context/SettingsContext.tsx
/* eslint react-refresh/only-export-components: "off" */
import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useState,
} from "react";
import type { ReactNode } from "react";
import { fetchSettings, updateSettings } from "../api/settings";

interface SettingsState {
    scope: string;
    values: Record<string, unknown>;
    defaults: Record<string, unknown>;
    options: Record<string, unknown>;
}

interface SettingsContextValue {
    settings: SettingsState | null;
    loading: boolean;
    error: string | null;
    refresh: () => Promise<void>;
    save: (values: Record<string, unknown>) => Promise<void>;
}

const SettingsContext = createContext<SettingsContextValue | null>(null);

export function SettingsProvider({ children }: { children: ReactNode }) {
    const [settings, setSettings] = useState<SettingsState | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await fetchSettings();
            setSettings(response);
        } catch (err) {
            console.error("Failed to load settings", err);
            setError("Failed to load settings.");
        } finally {
            setLoading(false);
        }
    }, []);

    const save = useCallback(
        async (values: Record<string, unknown>) => {
            if (!settings) {
                return;
            }
            setLoading(true);
            setError(null);
            try {
                const response = await updateSettings({
                    scope: settings.scope,
                    values,
                });
                setSettings(response);
            } catch (err) {
                console.error("Failed to update settings", err);
                setError("Failed to update settings.");
                throw err;
            } finally {
                setLoading(false);
            }
        },
        [settings],
    );

    useEffect(() => {
        void load();
    }, [load]);

    const value = useMemo(
        () => ({
            settings,
            loading,
            error,
            refresh: load,
            save,
        }),
        [settings, loading, error, load, save],
    );

    return (
        <SettingsContext.Provider value={value}>
            {children}
        </SettingsContext.Provider>
    );
}

export function useSettings() {
    const ctx = useContext(SettingsContext);
    if (!ctx) {
        throw new Error("useSettings must be used within SettingsProvider");
    }
    return ctx;
}
