// src/config.ts

// Shape of your app-wide config
interface AppConfig {
    apiBase: string;
    env: "development" | "production" | "test";
    isDev: boolean;
    isProd: boolean;
}

type ViteEnv = {
    MODE?: "development" | "production" | "test";
    [key: string]: string | boolean | undefined;
};

const env = import.meta.env as ViteEnv;

// Helper to read Vite env vars safely
function getEnv(name: string): string | undefined {
    const value = env[name];
    return typeof value === "string" ? value : undefined;
}

// --- API BASE --------------------------------------------------------

const rawApiBase = getEnv("VITE_API_BASE");

if (!rawApiBase) {
    throw new Error(
        "VITE_API_BASE is not set. Create frontend/.env with e.g. `VITE_API_BASE=http://localhost:5174` for dev (proxied) or your backend URL in prod."
    );
}

// strip trailing slash (http://localhost:8000/ -> http://localhost:8000)
const apiBase = rawApiBase.replace(/\/$/, "");

// --- ENV FLAGS -------------------------------------------------------

const mode = env.MODE;
const resolvedEnv = mode ?? "development";

export const appConfig: AppConfig = {
    apiBase,
    env: resolvedEnv,
    isDev: resolvedEnv === "development",
    isProd: resolvedEnv === "production",
} as const;
