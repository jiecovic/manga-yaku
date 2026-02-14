// src/context/AgentSettingsContext.tsx
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
import type {
    AgentTranslateSettingsResponse,
    UpdateAgentTranslateSettingsRequest,
} from "../api/agentSettings";
import type {
    OcrProfileSettingsResponse,
    UpdateOcrProfileSettingsRequest,
} from "../api/ocrProfileSettings";
import {
    fetchAgentTranslateSettings,
    updateAgentTranslateSettings,
} from "../api/agentSettings";
import {
    fetchOcrProfileSettings,
    updateOcrProfileSettings,
} from "../api/ocrProfileSettings";

interface AgentSettingsContextValue {
    agent: AgentTranslateSettingsResponse | null;
    ocrProfiles: OcrProfileSettingsResponse | null;
    loading: boolean;
    error: string | null;
    refresh: () => Promise<void>;
    saveAgent: (values: UpdateAgentTranslateSettingsRequest) => Promise<void>;
    saveOcrProfiles: (payload: UpdateOcrProfileSettingsRequest) => Promise<void>;
}

const AgentSettingsContext = createContext<AgentSettingsContextValue | null>(null);

export function AgentSettingsProvider({ children }: { children: ReactNode }) {
    const [agent, setAgent] = useState<AgentTranslateSettingsResponse | null>(null);
    const [ocrProfiles, setOcrProfiles] = useState<OcrProfileSettingsResponse | null>(
        null,
    );
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const [agentRes, ocrRes] = await Promise.all([
                fetchAgentTranslateSettings(),
                fetchOcrProfileSettings(),
            ]);
            setAgent(agentRes);
            setOcrProfiles(ocrRes);
        } catch (err) {
            console.error("Failed to load agent settings", err);
            setError("Failed to load agent settings.");
        } finally {
            setLoading(false);
        }
    }, []);

    const saveAgent = useCallback(
        async (values: UpdateAgentTranslateSettingsRequest) => {
            setLoading(true);
            setError(null);
            try {
                const response = await updateAgentTranslateSettings(values);
                setAgent(response);
            } catch (err) {
                console.error("Failed to update agent settings", err);
                setError("Failed to update agent settings.");
                throw err;
            } finally {
                setLoading(false);
            }
        },
        [],
    );

    const saveOcrProfiles = useCallback(
        async (payload: UpdateOcrProfileSettingsRequest) => {
            setLoading(true);
            setError(null);
            try {
                const response = await updateOcrProfileSettings(payload);
                setOcrProfiles(response);
            } catch (err) {
                console.error("Failed to update OCR profile settings", err);
                setError("Failed to update OCR profile settings.");
                throw err;
            } finally {
                setLoading(false);
            }
        },
        [],
    );

    useEffect(() => {
        void load();
    }, [load]);

    const value = useMemo(
        () => ({
            agent,
            ocrProfiles,
            loading,
            error,
            refresh: load,
            saveAgent,
            saveOcrProfiles,
        }),
        [agent, ocrProfiles, loading, error, load, saveAgent, saveOcrProfiles],
    );

    return (
        <AgentSettingsContext.Provider value={value}>
            {children}
        </AgentSettingsContext.Provider>
    );
}

export function useAgentSettings() {
    const ctx = useContext(AgentSettingsContext);
    if (!ctx) {
        throw new Error("useAgentSettings must be used within AgentSettingsProvider");
    }
    return ctx;
}
