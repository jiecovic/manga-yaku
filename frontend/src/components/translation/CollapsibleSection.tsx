// src/components/translation/CollapsibleSection.tsx
import { useState } from "react";
import type React from "react";
import { ui } from "../../ui/tokens";

interface CollapsibleSectionProps {
    title: string;
    defaultOpen?: boolean;
    children: React.ReactNode;
}

export function CollapsibleSection({
    title,
    defaultOpen = true,
    children,
}: CollapsibleSectionProps) {
    const [open, setOpen] = useState(defaultOpen);

    return (
        <div className={ui.sectionWrap}>
            <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                className={ui.sectionHeader}
            >
                <span>{title}</span>
                <span className={ui.mutedTextMicro}>
                    {open ? "v" : ">"}
                </span>
            </button>
            {open && <div className={ui.sectionBody}>{children}</div>}
        </div>
    );
}
