// src/components/translation/RightSidebarChatSection.helpers.ts
import type { AgentMessage, AgentSession } from "../../types";
import type { ChatStreamActivityEntry } from "./ChatStreamActivity";

export type AgentSessionState = AgentSession & {
    isDraft?: boolean;
};

export type AgentStreamPayload = {
    type?: string;
    delta?: string;
    message?: unknown;
    filename?: string;
    [key: string]: unknown;
};

export const buildDraftSession = (
    volumeId: string,
    title: string,
    modelId: string | null,
): AgentSessionState => {
    const now = new Date().toISOString();
    return {
        id: `draft-${Date.now()}`,
        volumeId,
        title,
        modelId,
        createdAt: now,
        updatedAt: now,
        isDraft: true,
    };
};

export function isDraftAgentSessionId(sessionId: string | null | undefined): boolean {
    return String(sessionId || "").trim().startsWith("draft-");
}

export function extractMessageActionEntries(
    message: AgentMessage,
): ChatStreamActivityEntry[] {
    const meta = message.meta;
    if (!meta || typeof meta !== "object") {
        return [];
    }
    const rawActions = (meta as Record<string, unknown>).actions;
    if (!Array.isArray(rawActions)) {
        return [];
    }

    const out: ChatStreamActivityEntry[] = [];
    rawActions.forEach((item, index) => {
        if (!item || typeof item !== "object") return;
        const row = item as Record<string, unknown>;
        const type = String(row.type || "").trim();
        const text = String(row.message || "").trim();
        if (!text) return;
        if (
            type !== "activity" &&
            type !== "tool_called" &&
            type !== "tool_output" &&
            type !== "page_switch"
        ) {
            return;
        }
        const filename = String(row.filename || "").trim();
        out.push({
            id: `msg-${message.id}-action-${index}`,
            kind: type,
            text,
            filename: type === "page_switch" ? filename : undefined,
        });
    });
    return out;
}

export function getPinnedActivityEntries(
    messages: AgentMessage[],
    streamActivity: ChatStreamActivityEntry[],
): ChatStreamActivityEntry[] {
    if (streamActivity.length > 0) {
        return streamActivity;
    }
    for (let index = messages.length - 1; index >= 0; index -= 1) {
        const message = messages[index];
        if (message.role !== "assistant") {
            continue;
        }
        const entries = extractMessageActionEntries(message);
        if (entries.length > 0) {
            return entries;
        }
    }
    return [];
}

export function messageHasMutatingToolAction(message: AgentMessage): boolean {
    const meta = message.meta;
    if (!meta || typeof meta !== "object") {
        return false;
    }
    const rawActions = (meta as Record<string, unknown>).actions;
    if (!Array.isArray(rawActions)) {
        return false;
    }

    for (const item of rawActions) {
        if (!item || typeof item !== "object") continue;
        const row = item as Record<string, unknown>;
        const type = String(row.type || "").trim();
        if (type !== "tool_output") continue;

        const tool = String(row.tool || "").trim();
        if (
            tool === "detect_text_boxes" ||
            tool === "update_text_box_fields" ||
            tool === "set_text_box_note" ||
            tool === "ocr_text_box"
        ) {
            return true;
        }

        const messageText = String(row.message || "").trim();
        if (
            messageText.startsWith("detect_text_boxes ->") ||
            messageText.startsWith("update_text_box_fields ->") ||
            messageText.startsWith("set_text_box_note ->") ||
            messageText.startsWith("ocr_text_box ->")
        ) {
            return true;
        }
    }
    return false;
}

export function messagePageSwitchFilename(message: AgentMessage): string | null {
    const meta = message.meta;
    if (!meta || typeof meta !== "object") {
        return null;
    }
    const rawActions = (meta as Record<string, unknown>).actions;
    if (!Array.isArray(rawActions)) {
        return null;
    }

    for (let index = rawActions.length - 1; index >= 0; index -= 1) {
        const item = rawActions[index];
        if (!item || typeof item !== "object") continue;
        const row = item as Record<string, unknown>;
        if (String(row.type || "").trim() !== "page_switch") {
            continue;
        }
        const filename = String(row.filename || "").trim();
        if (filename) {
            return filename;
        }
    }
    return null;
}
