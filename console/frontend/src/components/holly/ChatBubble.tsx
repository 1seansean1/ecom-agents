/**
 * ChatBubble — renders a single chat message (human or Holly).
 * Mobile-friendly: max-width 80%, readable on narrow screens.
 */

import type { HollyMessage } from '@/types/holly';

function formatTime(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

interface ChatBubbleProps {
  message: HollyMessage;
  isStreaming?: boolean;
}

export default function ChatBubble({ message, isStreaming }: ChatBubbleProps) {
  const isHuman = message.role === 'human';
  const isSystem = message.role === 'system';

  if (isSystem) {
    return (
      <div className="flex justify-center my-2">
        <span className="text-xs text-[var(--color-text-muted)] bg-[var(--color-bg-hover)] px-3 py-1 rounded-full">
          {message.content}
        </span>
      </div>
    );
  }

  return (
    <div className={`flex ${isHuman ? 'justify-end' : 'justify-start'} mb-3`}>
      <div
        className={`relative max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isHuman
            ? 'bg-[var(--color-accent)] text-white rounded-br-md'
            : 'bg-[var(--color-bg-card)] border border-[var(--color-border)] text-[var(--color-text)] rounded-bl-md'
        }`}
      >
        {!isHuman && (
          <div className="text-xs font-semibold text-[var(--color-accent)] mb-1">
            Holly Grace
          </div>
        )}
        <div className="whitespace-pre-wrap break-words">
          {message.content}
          {isStreaming && (
            <span className="inline-block w-2 h-4 ml-0.5 bg-[var(--color-accent)] animate-pulse rounded-sm" />
          )}
        </div>
        <div className={`text-[10px] mt-1 ${isHuman ? 'text-white/60' : 'text-[var(--color-text-muted)]'}`}>
          {formatTime(message.ts)}
        </div>
      </div>
    </div>
  );
}
