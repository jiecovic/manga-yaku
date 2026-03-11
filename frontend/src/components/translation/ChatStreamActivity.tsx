// src/components/translation/ChatStreamActivity.tsx
export type ChatStreamActivityEntry = {
  id: string;
  kind: 'activity' | 'tool_called' | 'tool_output' | 'page_switch';
  text: string;
  filename?: string;
};

interface ChatStreamActivityProps {
  entries: ChatStreamActivityEntry[];
}

export function ChatStreamActivity({ entries }: ChatStreamActivityProps) {
  if (entries.length === 0) {
    return null;
  }

  return (
    <div className="space-y-1">
      {entries.map((entry) => (
        <div key={entry.id} className="text-[10px] text-slate-400">
          <span className="uppercase tracking-wide text-slate-500">
            {entry.kind === 'tool_called'
              ? 'tool'
              : entry.kind === 'tool_output'
                ? 'result'
                : entry.kind === 'page_switch'
                  ? 'page'
                  : 'info'}
          </span>{' '}
          {entry.text}
        </div>
      ))}
    </div>
  );
}
