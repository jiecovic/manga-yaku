// src/components/TopNav.tsx
import type { ReactNode } from "react";
import { ui } from "../ui/tokens";

interface TopNavProps {
    mode: "translate" | "train" | "logs" | "settings";
    onChangeMode: (mode: "translate" | "train" | "logs" | "settings") => void;
    rightSlot?: ReactNode;
}

const modes = [
    { id: "translate", label: "Translate" },
    { id: "train", label: "Train" },
    { id: "logs", label: "Logs" },
    { id: "settings", label: "Settings" },
] as const;

export function TopNav({ mode, onChangeMode, rightSlot }: TopNavProps) {
    return (
        <header className={ui.topNav}>
            <div className={ui.topNavInner}>
                <div className={ui.topNavTitle}>
                    MangaYaku
                </div>
                <div className="flex items-center gap-2">
                    <div className={ui.topNavSegment}>
                        {modes.map((item) => {
                            const active = item.id === mode;
                            return (
                                <button
                                    key={item.id}
                                    type="button"
                                    className={
                                        ui.topNavSegmentButton +
                                        " " +
                                        (active
                                            ? ui.topNavSegmentActive
                                            : ui.topNavSegmentInactive)
                                    }
                                    onClick={() => onChangeMode(item.id)}
                                >
                                    {item.label}
                                </button>
                            );
                        })}
                    </div>
                    {rightSlot}
                </div>
            </div>
        </header>
    );
}

