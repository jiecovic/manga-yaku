// src/components/HealthBanner.tsx
import { useHealth } from "../context/HealthContext";

export function HealthBanner() {
    const {
        status,
        database,
        lastError,
        clearLastError,
        apiBase,
    } = useHealth();

    let message: string | null = null;
    let tone: "error" | "warning" = "warning";
    let dismissible = false;

    if (status === "down") {
        tone = "error";
        message = `Backend unreachable at ${apiBase}. Start the backend and retry.`;
    } else if (database === "unavailable") {
        tone = "warning";
        message = "Database unavailable. Start Postgres (docker compose up -d).";
    } else if (lastError) {
        tone = "warning";
        message = lastError;
        dismissible = true;
    }

    if (!message) {
        return null;
    }

    const styles =
        tone === "error"
            ? "border-red-900/60 bg-red-900/70 text-red-100"
            : "border-amber-900/60 bg-amber-900/70 text-amber-100";

    return (
        <div className={`border-b ${styles}`}>
            <div className="flex items-center justify-between px-4 py-2 text-xs">
                <div className="flex-1">{message}</div>
                {dismissible ? (
                    <button
                        type="button"
                        onClick={clearLastError}
                        className="ml-4 rounded-md border border-amber-500/70 px-2 py-0.5 text-[10px] text-amber-100 hover:bg-amber-500/20"
                    >
                        Dismiss
                    </button>
                ) : null}
            </div>
        </div>
    );
}
