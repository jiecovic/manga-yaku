// src/components/translation/ChatMessageList.tsx
import type { JSX, RefObject } from 'react';
import type { AgentMessage } from '../../types';
import { ui } from '../../ui/tokens';
import type { ChatStreamActivityEntry } from './ChatStreamActivity';
import { MarkdownText } from './MarkdownText';

interface ChatMessageListProps {
  loadingMessages: boolean;
  messages: AgentMessage[];
  replying: boolean;
  streamingText: string;
  streamActivity: ChatStreamActivityEntry[];
  endRef: RefObject<HTMLDivElement | null>;
}

type ChatRenderItem =
  | { kind: 'message'; message: AgentMessage }
  | { kind: 'timeline'; id: string; messages: AgentMessage[] };

function buildRenderItems(messages: AgentMessage[]): ChatRenderItem[] {
  const items: ChatRenderItem[] = [];
  let timelineBuffer: AgentMessage[] = [];

  const flushTimeline = () => {
    if (timelineBuffer.length === 0) return;
    items.push({
      kind: 'timeline',
      id: `timeline-${timelineBuffer[0].id}-${timelineBuffer[timelineBuffer.length - 1].id}`,
      messages: timelineBuffer,
    });
    timelineBuffer = [];
  };

  for (const message of messages) {
    if (message.role === 'tool') {
      timelineBuffer.push(message);
      continue;
    }
    flushTimeline();
    items.push({ kind: 'message', message });
  }
  flushTimeline();
  return items;
}

function renderTimelineGroup(
  id: string,
  entries: { id: string | number; content: string }[],
): JSX.Element | null {
  if (entries.length === 0) {
    return null;
  }
  const latest = entries[entries.length - 1];
  return (
    <div key={id} className="flex justify-start">
      <details className="max-w-[92%] rounded-md border border-amber-900/50 bg-amber-950/20 px-3 py-2 text-xs text-amber-100/90">
        <summary className="cursor-pointer list-none">
          <div className={ui.mutedTextMicro}>Activity</div>
          <div className="whitespace-pre-wrap">
            {latest.content}
            {entries.length > 1 ? ` (${entries.length})` : ''}
          </div>
        </summary>
        {entries.length > 1 && (
          <div className="mt-2 space-y-1 border-t border-amber-900/30 pt-2">
            {entries.map((entry, index) => (
              <div key={entry.id} className="flex gap-2 text-[11px] text-amber-100/85">
                <div className="min-w-[18px] text-right text-amber-300/80">{index + 1}.</div>
                <div className="whitespace-pre-wrap">{entry.content}</div>
              </div>
            ))}
          </div>
        )}
      </details>
    </div>
  );
}

export function ChatMessageList({
  loadingMessages,
  messages,
  replying,
  streamingText,
  streamActivity,
  endRef,
}: ChatMessageListProps) {
  const renderItems = buildRenderItems(messages);
  const liveStreamEntries = streamActivity.map((entry) => ({
    id: entry.id,
    content: entry.text,
  }));

  return (
    <div className="flex-1 overflow-y-auto space-y-2 pr-1">
      {loadingMessages && <div className={ui.mutedTextXs}>Loading messages...</div>}
      {!loadingMessages && messages.length === 0 && (
        <div className={ui.emptyState}>
          <div>No messages yet.</div>
          <div className={ui.emptyStateSub}>Ask the agent about the current volume.</div>
        </div>
      )}
      {renderItems.map((item) => {
        if (item.kind === 'timeline') {
          return renderTimelineGroup(
            item.id,
            item.messages.map((message) => ({
              id: message.id,
              content: message.content,
            })),
          );
        }
        const message = item.message;
        const isUser = message.role === 'user';
        return (
          <div key={message.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[85%] rounded-md border px-3 py-2 text-xs ${
                isUser
                  ? 'border-slate-700 bg-slate-800 text-slate-100'
                  : 'border-slate-800 bg-slate-900/80 text-slate-200'
              }`}
            >
              <div className={ui.mutedTextMicro}>{isUser ? 'You' : 'Agent'}</div>
              {isUser ? (
                <div className="whitespace-pre-wrap">{message.content}</div>
              ) : (
                <MarkdownText text={message.content} />
              )}
            </div>
          </div>
        );
      })}
      {replying && renderTimelineGroup('live-stream-activity', liveStreamEntries)}
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
