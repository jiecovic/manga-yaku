// src/components/settings/sections/ChatAgentCard.tsx
import { Field } from "../../../ui/primitives";
import { ui } from "../../../ui/tokens";

type Props = {
    agentChatMaxTurns: string;
    agentChatMaxOutputTokens: string;
    onUpdateDraft: (key: string, value: unknown) => void;
};

export function ChatAgentCard({
    agentChatMaxTurns,
    agentChatMaxOutputTokens,
    onUpdateDraft,
}: Props) {
    return (
        <div className={ui.trainingCard}>
            <div className={ui.trainingSubTitle}>Chat Agent</div>
            <div className="mt-3 space-y-3">
                <div className={ui.trainingHelp}>
                    These settings affect the MCP-backed chat agent in the right
                    sidebar. The chat model itself is selected per session in the
                    chat UI.
                </div>

                <Field label="Max turns" layout="row" labelClassName={ui.label}>
                    <input
                        className={ui.trainingInput}
                        type="number"
                        min={1}
                        max={200}
                        value={agentChatMaxTurns}
                        onChange={(e) =>
                            onUpdateDraft("agent.chat.max_turns", e.target.value)
                        }
                    />
                </Field>
                <div className={`${ui.trainingHelp} ml-28`}>
                    Turn budget for one chat-agent run before the SDK stops with
                    `MaxTurnsExceeded`.
                </div>

                <Field label="Max output" layout="row" labelClassName={ui.label}>
                    <input
                        className={ui.trainingInput}
                        type="number"
                        min={128}
                        max={64000}
                        value={agentChatMaxOutputTokens}
                        onChange={(e) =>
                            onUpdateDraft(
                                "agent.chat.max_output_tokens",
                                e.target.value,
                            )
                        }
                    />
                </Field>
                <div className={`${ui.trainingHelp} ml-28`}>
                    Output token budget for one chat-agent reply, including the
                    text-only repair fallback.
                </div>
            </div>
        </div>
    );
}
