// src/components/translation/RightSidebarChatSection.tsx
import { useEffect, useMemo, useRef, useState } from "react";
import type { AgentMessage, AgentModel, AgentSession } from "../../types";
import {
    createAgentMessage,
    createAgentSession,
    deleteAgentSession,
    fetchAgentConfig,
    fetchAgentMessages,
    fetchAgentSessions,
    requestAgentReply,
    updateAgentSession,
} from "../../api/agent";
import { API_BASE } from "../../api/client";
import { Button, Field, Select } from "../../ui/primitives";
import { ui } from "../../ui/tokens";

interface RightSidebarChatSectionProps {
    volumeId: string;
}

type AgentSessionState = AgentSession & {
    isDraft?: boolean;
};

const buildDraftSession = (
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

export function RightSidebarChatSection({
    volumeId,
}: RightSidebarChatSectionProps) {
    const [sessions, setSessions] = useState<AgentSessionState[]>([]);
    const [activeSessionId, setActiveSessionId] = useState("");
    const [messages, setMessages] = useState<AgentMessage[]>([]);
    const [models, setModels] = useState<AgentModel[]>([]);
    const [selectedModelId, setSelectedModelId] = useState("");
    const [maxMessageChars, setMaxMessageChars] = useState(2000);
    const [input, setInput] = useState("");
    const [loadingSessions, setLoadingSessions] = useState(false);
    const [loadingMessages, setLoadingMessages] = useState(false);
    const [sending, setSending] = useState(false);
    const [replying, setReplying] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [streamingText, setStreamingText] = useState("");
    const [isStreaming, setIsStreaming] = useState(false);
    const endRef = useRef<HTMLDivElement | null>(null);
    const streamRef = useRef<EventSource | null>(null);
    const streamSessionRef = useRef<string | null>(null);
    const receivedDeltaRef = useRef(false);
    const streamCanceledRef = useRef(false);

    const hasVolume = Boolean(volumeId);

    useEffect(() => {
        let cancelled = false;
        const loadConfig = async () => {
            try {
                const config = await fetchAgentConfig();
                if (cancelled) return;
                setModels(config.models);
                setMaxMessageChars(config.maxMessageChars || 2000);
                setSelectedModelId((prev) =>
                    prev || config.defaultModel || config.models[0]?.id || "",
                );
            } catch (err) {
                console.error("Failed to load agent config", err);
                setModels((prev) => prev);
            }
        };

        void loadConfig();

        return () => {
            cancelled = true;
        };
    }, []);

    useEffect(() => {
        if (!hasVolume) {
            setSessions([]);
            setActiveSessionId("");
            setMessages([]);
            return;
        }

        let cancelled = false;
        const load = async () => {
            setLoadingSessions(true);
            setError(null);
            try {
                const data = await fetchAgentSessions(volumeId);
                if (cancelled) return;
                if (data.length > 0) {
                    setSessions(data);
                    setActiveSessionId((prev) =>
                        data.some((item) => item.id === prev)
                            ? prev
                            : data[0].id,
                    );
                    return;
                }
                const draft = buildDraftSession(
                    volumeId,
                    "Session 1",
                    selectedModelId || null,
                );
                setSessions([draft]);
                setActiveSessionId(draft.id);
            } catch (err) {
                if (cancelled) return;
                console.error("Failed to load agent sessions", err);
                setError("Failed to load chat sessions.");
            } finally {
                if (!cancelled) {
                    setLoadingSessions(false);
                }
            }
        };

        void load();

        return () => {
            cancelled = true;
        };
    }, [hasVolume, volumeId, selectedModelId]);

    useEffect(() => {
        if (!activeSessionId) {
            setMessages([]);
            return;
        }
        const currentSession = sessions.find(
            (session) => session.id === activeSessionId,
        );
        if (currentSession?.isDraft) {
            setMessages([]);
            setLoadingMessages(false);
            return;
        }

        let cancelled = false;
        const loadMessages = async () => {
            setLoadingMessages(true);
            setError(null);
            try {
                const data = await fetchAgentMessages(activeSessionId);
                if (cancelled) return;
                setMessages(data);
            } catch (err) {
                if (cancelled) return;
                console.error("Failed to load agent messages", err);
                setError("Failed to load chat messages.");
            } finally {
                if (!cancelled) {
                    setLoadingMessages(false);
                }
            }
        };

        void loadMessages();

        return () => {
            cancelled = true;
        };
    }, [activeSessionId, sessions]);

    useEffect(() => {
        endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }, [messages, replying, streamingText]);

    const activeSession = useMemo(
        () => sessions.find((session) => session.id === activeSessionId) ?? null,
        [sessions, activeSessionId],
    );

    useEffect(() => {
        if (!activeSession) return;
        if (activeSession.modelId && activeSession.modelId !== selectedModelId) {
            setSelectedModelId(activeSession.modelId);
        }
    }, [activeSession, selectedModelId]);

    useEffect(() => {
        return () => {
            if (streamRef.current) {
                streamRef.current.close();
                streamRef.current = null;
                streamSessionRef.current = null;
            }
        };
    }, []);

    useEffect(() => {
        if (
            streamRef.current &&
            streamSessionRef.current &&
            streamSessionRef.current !== activeSessionId
        ) {
            streamRef.current.close();
            streamRef.current = null;
            streamSessionRef.current = null;
            setStreamingText("");
            setReplying(false);
            setIsStreaming(false);
        }
        if (!activeSessionId && streamRef.current) {
            streamRef.current.close();
            streamRef.current = null;
            streamSessionRef.current = null;
            setStreamingText("");
            setReplying(false);
            setIsStreaming(false);
        }
    }, [activeSessionId]);

    const handleCreateSession = async () => {
        if (!volumeId || sending || replying) return;
        setError(null);
        const existingDraft = sessions.find((session) => session.isDraft);
        const draft =
            existingDraft ??
            buildDraftSession(
                volumeId,
                `Session ${sessions.length + 1}`,
                selectedModelId || null,
            );
        setSessions((prev) => {
            if (prev.some((session) => session.id === draft.id)) {
                return prev;
            }
            return [draft, ...prev];
        });
        setActiveSessionId(draft.id);
    };

    const handleChangeModel = async (nextId: string) => {
        setSelectedModelId(nextId);
        if (!activeSessionId) {
            return;
        }
        if (activeSession?.isDraft) {
            setSessions((prev) =>
                prev.map((item) =>
                    item.id === activeSessionId
                        ? { ...item, modelId: nextId, updatedAt: new Date().toISOString() }
                        : item,
                ),
            );
            return;
        }
        try {
            const updated = await updateAgentSession(activeSessionId, {
                modelId: nextId,
            });
            setSessions((prev) =>
                prev.map((item) => (item.id === updated.id ? updated : item)),
            );
        } catch (err) {
            console.error("Failed to update agent model", err);
            setError("Failed to update model.");
        }
    };

    const handleDeleteSession = async () => {
        if (!volumeId || !activeSessionId || sending || replying) {
            return;
        }
        const target = sessions.find(
            (session) => session.id === activeSessionId,
        );
        if (!target) {
            return;
        }
        const label = target.title || "Session";
        const confirmed = window.confirm(
            `Delete "${label}"? This removes its chat history.`,
        );
        if (!confirmed) {
            return;
        }
        if (!target.isDraft) {
            try {
                await deleteAgentSession(target.id);
            } catch (err) {
                console.error("Failed to delete chat session", err);
                setError("Failed to delete chat session.");
                return;
            }
        }

        setSessions((prev) => {
            const next = prev.filter((item) => item.id !== target.id);
            if (next.length > 0) {
                setActiveSessionId(next[0].id);
                return next;
            }
            const draft = buildDraftSession(
                volumeId,
                "Session 1",
                selectedModelId || null,
            );
            setActiveSessionId(draft.id);
            return [draft];
        });
    };

    const handleSend = async () => {
        const trimmed = input.trim();
        if (!trimmed || !volumeId || !activeSessionId || sending || replying) {
            return;
        }
        if (trimmed.length > maxMessageChars) {
            setError(`Message too long (max ${maxMessageChars} chars).`);
            return;
        }
        setSending(true);
        setError(null);
        let createdSessionId: string | null = null;
        let draftTitle = "Session 1";
        let messageCreated = false;

        try {
            let sessionId = activeSessionId;
            const current = sessions.find(
                (session) => session.id === activeSessionId,
            );
            if (current?.title) {
                draftTitle = current.title;
            }
            if (current?.isDraft) {
                const created = await createAgentSession({
                    volumeId,
                    title: current.title,
                    modelId: current.modelId || selectedModelId || undefined,
                });
                sessionId = created.id;
                createdSessionId = created.id;
                setSessions((prev) =>
                    prev.map((item) => (item.id === current.id ? created : item)),
                );
                setActiveSessionId(created.id);
            }

            const userMessage = await createAgentMessage(sessionId, {
                role: "user",
                content: trimmed,
            });
            messageCreated = true;
            setMessages((prev) => [...prev, userMessage]);
            setInput("");
            setReplying(true);
            setStreamingText("");
            setIsStreaming(false);
            receivedDeltaRef.current = false;
            streamCanceledRef.current = false;

            if (typeof window !== "undefined" && "EventSource" in window) {
                if (streamRef.current) {
                    streamRef.current.close();
                }
                const url = `${API_BASE}/api/agent/sessions/${encodeURIComponent(
                    sessionId,
                )}/reply/stream?maxMessages=20`;
                const source = new EventSource(url);
                streamRef.current = source;
                streamSessionRef.current = sessionId;
                setIsStreaming(true);

                source.onmessage = (event) => {
                    if (streamSessionRef.current !== sessionId) {
                        return;
                    }
                    try {
                        const payload = JSON.parse(event.data);
                        if (payload.type === "delta") {
                            receivedDeltaRef.current = true;
                            setStreamingText((prev) => prev + String(payload.delta || ""));
                            return;
                        }
                        if (payload.type === "done" && payload.message) {
                            setMessages((prev) => [...prev, payload.message as AgentMessage]);
                            setStreamingText("");
                            setReplying(false);
                            setIsStreaming(false);
                            source.close();
                            streamRef.current = null;
                            streamSessionRef.current = null;
                            return;
                        }
                        if (payload.type === "canceled") {
                            setStreamingText("");
                            setReplying(false);
                            setIsStreaming(false);
                            source.close();
                            streamRef.current = null;
                            streamSessionRef.current = null;
                            return;
                        }
                        if (payload.type === "error") {
                            setError(payload.message || "Streaming failed.");
                            setStreamingText("");
                            setReplying(false);
                            setIsStreaming(false);
                            source.close();
                            streamRef.current = null;
                            streamSessionRef.current = null;
                        }
                    } catch (err) {
                        console.error("Failed to parse agent stream", err);
                    }
                };

                source.onerror = async () => {
                    if (streamCanceledRef.current) {
                        streamCanceledRef.current = false;
                        source.close();
                        streamRef.current = null;
                        streamSessionRef.current = null;
                        setStreamingText("");
                        setReplying(false);
                        setIsStreaming(false);
                        return;
                    }
                    source.close();
                    streamRef.current = null;
                    streamSessionRef.current = null;
                    setIsStreaming(false);
                    if (!receivedDeltaRef.current) {
                        try {
                            const assistantMessage = await requestAgentReply(sessionId, {
                                maxMessages: 20,
                            });
                            setMessages((prev) => [...prev, assistantMessage]);
                        } catch (err) {
                            console.error("Failed to fetch agent reply", err);
                            setError("Failed to stream message.");
                        }
                    } else {
                        setError("Agent stream disconnected.");
                    }
                    setStreamingText("");
                    setReplying(false);
                };
            } else {
                const assistantMessage = await requestAgentReply(sessionId, {
                    maxMessages: 20,
                });
                setMessages((prev) => [...prev, assistantMessage]);
                setReplying(false);
            }
        } catch (err) {
            console.error("Failed to send agent message", err);
            setError("Failed to send message.");
            setStreamingText("");
            setReplying(false);
            setIsStreaming(false);
            if (createdSessionId && !messageCreated) {
                try {
                    await deleteAgentSession(createdSessionId);
                } catch (cleanupErr) {
                    console.warn("Failed to remove empty session", cleanupErr);
                }
                const draft = buildDraftSession(
                    volumeId,
                    draftTitle,
                    selectedModelId || null,
                );
                setSessions((prev) => {
                    const filtered = prev.filter(
                        (item) => item.id !== createdSessionId && !item.isDraft,
                    );
                    return [draft, ...filtered];
                });
                setActiveSessionId(draft.id);
            }
        } finally {
            setSending(false);
        }
    };

    const handleStop = () => {
        if (!replying) return;
        streamCanceledRef.current = true;
        if (streamRef.current) {
            streamRef.current.close();
            streamRef.current = null;
        }
        streamSessionRef.current = null;
        receivedDeltaRef.current = false;
        setStreamingText("");
        setReplying(false);
        setIsStreaming(false);
    };

    const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            void handleSend();
        }
    };

    return (
        <div className="h-full flex flex-col gap-3 p-4">
            <div className="flex flex-col gap-2">
                <div className="flex flex-wrap items-center gap-2">
                    <Field
                        label="Session"
                        layout="row"
                        labelClassName="w-16 shrink-0 text-[11px] text-slate-400"
                        className="flex-1 min-w-[180px]"
                    >
                        {loadingSessions ? (
                            <div className={ui.mutedTextXs}>Loading...</div>
                        ) : (
                            <Select
                                value={activeSessionId}
                                onChange={(e) =>
                                    setActiveSessionId(e.target.value)
                                }
                                disabled={!sessions.length}
                            >
                                {sessions.map((session) => (
                                    <option key={session.id} value={session.id}>
                                        {session.isDraft
                                            ? `${session.title} (draft)`
                                            : session.title}
                                    </option>
                                ))}
                            </Select>
                        )}
                    </Field>
                    <div className="flex items-center gap-2">
                        <Button
                            type="button"
                            variant="ghostSmall"
                            onClick={handleCreateSession}
                            disabled={!hasVolume || sending || replying}
                        >
                            New
                        </Button>
                        <button
                            type="button"
                            onClick={handleDeleteSession}
                            disabled={!activeSessionId || sending || replying}
                            className={
                                ui.button.deleteBase +
                                " " +
                                (!activeSessionId || sending || replying
                                    ? ui.button.deleteDisabled
                                    : ui.button.deleteEnabled)
                            }
                        >
                            Delete
                        </button>
                    </div>
                </div>
                <Field
                    label="Model"
                    layout="row"
                    labelClassName="w-16 shrink-0 text-[11px] text-slate-400"
                    className="flex-1 min-w-[180px]"
                >
                    {models.length === 0 ? (
                        <div className={ui.mutedTextXs}>Loading...</div>
                    ) : (
                        <Select
                            value={selectedModelId}
                            onChange={(e) =>
                                void handleChangeModel(e.target.value)
                            }
                        >
                            {models.map((model) => (
                                <option key={model.id} value={model.id}>
                                    {model.label}
                                </option>
                            ))}
                        </Select>
                    )}
                </Field>
            </div>

            {!hasVolume && (
                <div className={ui.mutedTextXs}>
                    Select a volume to start chatting.
                </div>
            )}

            {error && <div className={ui.errorTextXs}>{error}</div>}

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
                            className={`flex ${
                                isUser ? "justify-end" : "justify-start"
                            }`}
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
                                <div className="whitespace-pre-wrap">
                                    {message.content}
                                </div>
                            </div>
                        </div>
                    );
                })}
                {replying && (
                    <div className="flex justify-start">
                        <div className="max-w-[85%] rounded-md border border-slate-800 bg-slate-900/80 px-3 py-2 text-xs text-slate-200">
                            <div className={ui.mutedTextMicro}>Agent</div>
                            <div className="whitespace-pre-wrap">
                                {streamingText || "Thinking..."}
                            </div>
                        </div>
                    </div>
                )}
                <div ref={endRef} />
            </div>

            <div className="space-y-2">
                {activeSession && (
                    <div className={ui.mutedTextMicro}>
                        Active: {activeSession.title}
                    </div>
                )}
                <textarea
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    rows={3}
                    className={ui.textarea}
                    placeholder="Ask the agent..."
                    disabled={!activeSessionId || sending || replying}
                />
                <div className="flex items-center justify-between gap-2">
                    <div className={ui.mutedTextMicro}>
                        {input.length}/{maxMessageChars}
                    </div>
                    <Button
                        type="button"
                        variant="actionSlateSmall"
                        onClick={replying ? handleStop : handleSend}
                        disabled={
                            replying
                                ? !isStreaming
                                : !input.trim() ||
                                  sending ||
                                  replying ||
                                  input.length > maxMessageChars
                        }
                    >
                        {replying
                            ? isStreaming
                                ? "Stop"
                                : "Waiting..."
                            : sending
                              ? "Sending..."
                              : "Send"}
                    </Button>
                </div>
            </div>
        </div>
    );
}
