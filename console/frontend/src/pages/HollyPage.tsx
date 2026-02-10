/**
 * HollyPage — Chat-first mobile UI for Holly Grace super-orchestrator.
 *
 * Single-column layout:
 * - Collapsible system status bar (top)
 * - Scrollable chat messages with inline approval cards
 * - Sticky bottom input bar (thumb-reachable)
 *
 * Responsive: on desktop (>768px), same layout but wider content area.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Send, Loader2, Sparkles, Wrench, RefreshCw } from 'lucide-react';
import Header from '@/components/layout/Header';
import SystemStatus from '@/components/holly/SystemStatus';
import ChatBubble from '@/components/holly/ChatBubble';
import ApprovalCard from '@/components/holly/ApprovalCard';
import { fetchJson, postJson } from '@/lib/api';
import type { ApprovalCardData, ChatEntry, HollyMessage } from '@/types/holly';

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function HollyPage() {
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [streamText, setStreamText] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom
  const scrollToBottom = useCallback(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [entries, streamText, scrollToBottom]);

  // Load session on mount
  useEffect(() => {
    loadSession();
    loadGreeting();
  }, []);

  const loadSession = async () => {
    try {
      const data = await fetchJson<{ messages: HollyMessage[] }>('/api/holly/session');
      if (data.messages?.length) {
        setEntries(data.messages.map((m) => ({ kind: 'message' as const, message: m })));
      }
    } catch {
      // fresh session
    }
  };

  const loadGreeting = async () => {
    try {
      const data = await fetchJson<{ greeting: string }>('/api/holly/greeting');
      if (data.greeting && entries.length === 0) {
        setEntries([{
          kind: 'message',
          message: {
            role: 'holly',
            content: data.greeting,
            ts: new Date().toISOString(),
          },
        }]);
      }
    } catch {
      // use default
    }
  };

  // Load pending tickets as approval cards
  useEffect(() => {
    const loadTickets = async () => {
      try {
        const data = await fetchJson<{ tickets: ApprovalCardData[] }>('/api/tower/inbox?status=pending&limit=10');
        if (data.tickets?.length) {
          const existingTicketIds = new Set(
            entries
              .filter((e): e is { kind: 'approval'; card: ApprovalCardData } => e.kind === 'approval')
              .map((e) => e.card.ticket_id)
          );
          const newCards: ChatEntry[] = data.tickets
            .filter((t) => !existingTicketIds.has(t.ticket_id ?? (t as any).id))
            .map((t) => ({
              kind: 'approval' as const,
              card: {
                ticket_id: t.ticket_id ?? (t as any).id,
                run_id: t.run_id,
                ticket_type: t.ticket_type,
                risk_level: t.risk_level,
                status: t.status,
                tldr: t.tldr || (t as any).context_pack?.tldr || '',
                why_stopped: t.why_stopped || (t as any).context_pack?.why_stopped || '',
                created_at: t.created_at,
              },
            }));
          if (newCards.length) {
            setEntries((prev) => [...prev, ...newCards]);
          }
        }
      } catch {
        // ignore
      }
    };
    loadTickets();
    const timer = setInterval(loadTickets, 10000);
    return () => clearInterval(timer);
  }, []);

  // Send message via REST (non-streaming for simplicity)
  const handleSend = async () => {
    const text = input.trim();
    if (!text || sending) return;

    // Add human message
    const humanMsg: HollyMessage = {
      role: 'human',
      content: text,
      ts: new Date().toISOString(),
    };
    setEntries((prev) => [...prev, { kind: 'message', message: humanMsg }]);
    setInput('');
    setSending(true);
    setIsStreaming(true);
    setStreamText('');

    try {
      const data = await postJson<{ response: string }>('/api/holly/message', {
        message: text,
        session_id: 'default',
      });

      setIsStreaming(false);
      setStreamText('');

      if (data.response) {
        const hollyMsg: HollyMessage = {
          role: 'holly',
          content: data.response,
          ts: new Date().toISOString(),
        };
        setEntries((prev) => [...prev, { kind: 'message', message: hollyMsg }]);
      }
    } catch (err) {
      setIsStreaming(false);
      setStreamText('');
      const errorMsg: HollyMessage = {
        role: 'holly',
        content: 'Sorry, I encountered an error processing your message. Please try again.',
        ts: new Date().toISOString(),
      };
      setEntries((prev) => [...prev, { kind: 'message', message: errorMsg }]);
    } finally {
      setSending(false);
    }
  };

  // Handle approval/rejection
  const handleApprove = async (ticketId: number) => {
    try {
      await postJson(`/api/holly/message`, {
        message: `Approve ticket #${ticketId}`,
        session_id: 'default',
      });
      setEntries((prev) =>
        prev.map((e) =>
          e.kind === 'approval' && e.card.ticket_id === ticketId
            ? { ...e, card: { ...e.card, status: 'approved' } }
            : e
        )
      );
    } catch {
      // ignore
    }
  };

  const handleReject = async (ticketId: number) => {
    try {
      await postJson(`/api/holly/message`, {
        message: `Reject ticket #${ticketId}`,
        session_id: 'default',
      });
      setEntries((prev) =>
        prev.map((e) =>
          e.kind === 'approval' && e.card.ticket_id === ticketId
            ? { ...e, card: { ...e.card, status: 'rejected' } }
            : e
        )
      );
    } catch {
      // ignore
    }
  };

  // Clear session
  const handleClear = async () => {
    try {
      await postJson('/api/holly/clear', { session_id: 'default' });
      setEntries([]);
      loadGreeting();
    } catch {
      // ignore
    }
  };

  // Keyboard: Enter to send, Shift+Enter for newline
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Auto-resize textarea
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  };

  return (
    <div className="flex flex-col h-full">
      <Header
        title="Holly Grace"
        subtitle="Super-Orchestrator"
        right={
          <button
            onClick={handleClear}
            className="p-2 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-bg-hover)] transition-colors"
            title="Clear conversation"
          >
            <RefreshCw size={16} />
          </button>
        }
      />

      <SystemStatus />

      {/* Chat area */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {entries.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-[var(--color-text-muted)]">
            <Sparkles size={48} className="mb-4 opacity-30" />
            <p className="text-sm">Start a conversation with Holly Grace</p>
          </div>
        )}

        {entries.map((entry, i) => {
          if (entry.kind === 'message') {
            return <ChatBubble key={i} message={entry.message} />;
          }
          if (entry.kind === 'approval') {
            return (
              <ApprovalCard
                key={`ticket-${entry.card.ticket_id}`}
                card={entry.card}
                onApprove={handleApprove}
                onReject={handleReject}
              />
            );
          }
          if (entry.kind === 'tool_activity') {
            return (
              <div key={i} className="flex justify-start mb-2">
                <div className="flex items-center gap-2 text-xs text-[var(--color-text-muted)] bg-[var(--color-bg-hover)] px-3 py-1.5 rounded-full">
                  <Wrench size={12} />
                  <span>{entry.name}</span>
                  {entry.status === 'calling' && <Loader2 size={12} className="animate-spin" />}
                </div>
              </div>
            );
          }
          return null;
        })}

        {/* Streaming indicator */}
        {isStreaming && (
          <div className="flex justify-start mb-3">
            <div className="bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-2xl rounded-bl-md px-4 py-3">
              <div className="text-xs font-semibold text-[var(--color-accent)] mb-1">Holly Grace</div>
              <div className="flex items-center gap-1">
                <span className="w-2 h-2 bg-[var(--color-accent)] rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-[var(--color-accent)] rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-[var(--color-accent)] rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* Input bar — sticky bottom */}
      <div className="shrink-0 border-t border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-3">
        <div className="flex items-end gap-2 max-w-3xl mx-auto">
          <textarea
            ref={inputRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Message Holly Grace..."
            rows={1}
            className="flex-1 resize-none bg-[var(--color-bg)] border border-[var(--color-border)] rounded-xl px-4 py-2.5 text-sm text-[var(--color-text)] placeholder-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-accent)] transition-colors"
            style={{ maxHeight: '120px' }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || sending}
            className="shrink-0 w-11 h-11 flex items-center justify-center rounded-xl bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-40 transition-colors"
          >
            {sending ? (
              <Loader2 size={18} className="animate-spin" />
            ) : (
              <Send size={18} />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
