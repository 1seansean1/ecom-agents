/**
 * ApprovalCard — inline approval card for Holly Grace chat.
 * Large touch targets (min 44px), mobile-friendly.
 */

import { useState } from 'react';
import { Check, X, Loader2 } from 'lucide-react';
import type { ApprovalCardData } from '@/types/holly';

const RISK_COLORS: Record<string, string> = {
  low: 'text-green-400 border-green-400/30 bg-green-400/10',
  medium: 'text-yellow-400 border-yellow-400/30 bg-yellow-400/10',
  high: 'text-red-400 border-red-400/30 bg-red-400/10',
};

interface ApprovalCardProps {
  card: ApprovalCardData;
  onApprove: (ticketId: number) => void;
  onReject: (ticketId: number) => void;
}

export default function ApprovalCard({ card, onApprove, onReject }: ApprovalCardProps) {
  const [deciding, setDeciding] = useState<'approve' | 'reject' | null>(null);

  const handleApprove = () => {
    setDeciding('approve');
    onApprove(card.ticket_id);
  };

  const handleReject = () => {
    setDeciding('reject');
    onReject(card.ticket_id);
  };

  const riskClass = RISK_COLORS[card.risk_level] || RISK_COLORS.medium;
  const isDecided = card.status !== 'pending';

  return (
    <div className="flex justify-start mb-3">
      <div className="max-w-[85%] w-full bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-2xl rounded-bl-md overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-2 px-4 pt-3 pb-2">
          <span className={`px-2 py-0.5 text-xs font-medium rounded-full border ${riskClass}`}>
            {card.risk_level}
          </span>
          <span className="text-xs text-[var(--color-text-muted)]">
            #{card.ticket_id} &middot; {card.ticket_type}
          </span>
        </div>

        {/* Content */}
        <div className="px-4 pb-2">
          <div className="text-sm text-[var(--color-text)] font-medium mb-1">
            {card.tldr || 'Approval needed'}
          </div>
          {card.why_stopped && (
            <div className="text-xs text-[var(--color-text-muted)]">
              {card.why_stopped}
            </div>
          )}
        </div>

        {/* Actions */}
        {!isDecided && (
          <div className="flex border-t border-[var(--color-border)]">
            <button
              onClick={handleApprove}
              disabled={!!deciding}
              className="flex-1 flex items-center justify-center gap-2 py-3 text-sm font-medium text-green-400 hover:bg-green-400/10 transition-colors disabled:opacity-50 min-h-[44px]"
            >
              {deciding === 'approve' ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Check size={16} />
              )}
              Approve
            </button>
            <div className="w-px bg-[var(--color-border)]" />
            <button
              onClick={handleReject}
              disabled={!!deciding}
              className="flex-1 flex items-center justify-center gap-2 py-3 text-sm font-medium text-red-400 hover:bg-red-400/10 transition-colors disabled:opacity-50 min-h-[44px]"
            >
              {deciding === 'reject' ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <X size={16} />
              )}
              Reject
            </button>
          </div>
        )}

        {isDecided && (
          <div className="px-4 py-2 border-t border-[var(--color-border)] text-xs text-[var(--color-text-muted)]">
            {card.status === 'approved' ? 'Approved' : 'Rejected'}
          </div>
        )}
      </div>
    </div>
  );
}
