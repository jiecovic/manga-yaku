// src/components/translation/ChatMessageList.tsx
import type { RefObject } from "react";
import type { AgentMessage } from "../../types";
import { ui } from "../../ui/tokens";
import { MarkdownText } from "./MarkdownText";

interface ChatMessageListProps {
    loadingMessages: boolean;
    messages: AgentMessage[];
    replying: boolean;
    streamingText: string;
    endRef: RefObject<HTMLDivElement | null>;
}

export function ChatMessageList({
    loadingMessages,
    messages,
    replying,
    streamingText,
    endRef,
}: ChatMessageListProps) {
    return (
        <div className="flex-1 overflow-y-auto space-y-2 pr-1">
            {loadingMessages && (
                <div className={ui.mutedTextXs}>Loading messages...</div>
            )}
            {!loadingMessages && messages.length === 0 && (
                <div className={ui.emptyState}>
                    <div>No messages yet.</div>
                    <div className={ui.emptyStateSub}>
                        Ask the agent about the current volume.
                    </div>
                </div>
            )}
            {messages.map((message) => {
                const isUser = message.role === "user";
                return (
                    <div
                        key={message.id}
                        className={`flex ${isUser ? "justify-end" : "justify-start"}`}
                    >
                        <div
                            className={`max-w-[85%] rounded-md border px-3 py-2 text-xs ${
                                isUser
                                    ? "border-slate-700 bg-slate-800 text-slate-100"
                                    : "border-slate-800 bg-slate-900/80 text-slate-200"
                            }`}
                        >
                            <div className={ui.mutedTextMicro}>
                                {isUser ? "You" : "Agent"}
                            </div>
                            {isUser ? (
                                <div className="whitespace-pre-wrap">{message.content}</div>
                            ) : (
                                <MarkdownText text={message.content} />
                            )}
                        </div>
                    </div>
                );
            })}
            {replying && (
                <div className="flex justify-start">
                    <div className="max-w-[85%] rounded-md border border-slate-800 bg-slate-900/80 px-3 py-2 text-xs text-slate-200">
                        <div className={ui.mutedTextMicro}>Agent</div>
                        {streamingText ? (
                            <MarkdownText text={streamingText} />
                        ) : (
                            <div className="whitespace-pre-wrap">Thinking...</div>
                        )}
                    </div>
                </div>
            )}
            <div ref={endRef} />
        </div>
    );
}
