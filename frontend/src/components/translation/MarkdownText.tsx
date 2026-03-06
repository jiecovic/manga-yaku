// src/components/translation/MarkdownText.tsx
import type { ReactNode } from "react";

interface MarkdownTextProps {
    text: string;
}

const BULLET_RE = /^[-*]\s+(.+)$/;
const ORDERED_RE = /^(\d+)\.\s+(.+)$/;
const INLINE_RE = /(`[^`]+`|\*\*[^*]+\*\*|__[^_]+__|\*[^*]+\*)/g;

function parseInline(text: string): ReactNode[] {
    const nodes: ReactNode[] = [];
    let lastIndex = 0;
    let partIndex = 0;

    for (const match of text.matchAll(INLINE_RE)) {
        const token = match[0];
        const index = match.index ?? 0;
        if (index > lastIndex) {
            nodes.push(text.slice(lastIndex, index));
        }

        if (token.startsWith("**") && token.endsWith("**")) {
            nodes.push(
                <strong key={`s-${partIndex++}`}>{token.slice(2, -2)}</strong>,
            );
        } else if (token.startsWith("__") && token.endsWith("__")) {
            nodes.push(
                <strong key={`s-${partIndex++}`}>{token.slice(2, -2)}</strong>,
            );
        } else if (token.startsWith("`") && token.endsWith("`")) {
            nodes.push(
                <code
                    key={`c-${partIndex++}`}
                    className="rounded bg-slate-800 px-1 py-0.5 text-[11px] text-slate-100"
                >
                    {token.slice(1, -1)}
                </code>,
            );
        } else if (token.startsWith("*") && token.endsWith("*")) {
            nodes.push(<em key={`e-${partIndex++}`}>{token.slice(1, -1)}</em>);
        } else {
            nodes.push(token);
        }

        lastIndex = index + token.length;
    }

    if (lastIndex < text.length) {
        nodes.push(text.slice(lastIndex));
    }
    return nodes;
}

export function MarkdownText({ text }: MarkdownTextProps) {
    const lines = text.split("\n");
    const blocks: ReactNode[] = [];
    let index = 0;

    while (index < lines.length) {
        const line = lines[index].trimEnd();
        if (!line.trim()) {
            index += 1;
            continue;
        }

        if (BULLET_RE.test(line)) {
            const items: ReactNode[] = [];
            while (index < lines.length) {
                const match = lines[index].trimEnd().match(BULLET_RE);
                if (!match) break;
                items.push(<li key={`ul-${index}`}>{parseInline(match[1])}</li>);
                index += 1;
            }
            blocks.push(
                <ul key={`b-${index}`} className="ml-4 list-disc space-y-0.5">
                    {items}
                </ul>,
            );
            continue;
        }

        if (ORDERED_RE.test(line)) {
            const items: ReactNode[] = [];
            while (index < lines.length) {
                const match = lines[index].trimEnd().match(ORDERED_RE);
                if (!match) break;
                items.push(<li key={`ol-${index}`}>{parseInline(match[2])}</li>);
                index += 1;
            }
            blocks.push(
                <ol key={`o-${index}`} className="ml-4 list-decimal space-y-0.5">
                    {items}
                </ol>,
            );
            continue;
        }

        const paragraphLines: string[] = [];
        while (index < lines.length) {
            const current = lines[index].trimEnd();
            if (!current.trim()) break;
            if (BULLET_RE.test(current) || ORDERED_RE.test(current)) break;
            paragraphLines.push(current);
            index += 1;
        }
        const paragraphText = paragraphLines.join("\n");
        blocks.push(
            <p key={`p-${index}`} className="whitespace-pre-wrap">
                {parseInline(paragraphText)}
            </p>,
        );
    }

    return <div className="space-y-1">{blocks}</div>;
}
