/** Holly Grace chat types */

export interface HollyMessage {
  role: 'human' | 'holly' | 'system';
  content: string;
  ts: string;
  metadata?: Record<string, unknown>;
}

export interface HollySession {
  session_id: string;
  messages: HollyMessage[];
}

export interface HollyNotification {
  id: number;
  msg_type: string;
  payload: Record<string, unknown>;
  priority: 'low' | 'normal' | 'high' | 'critical';
  status: 'pending' | 'surfaced';
  created_at: string;
}

/** WebSocket message types */
export type HollyWsInbound = {
  type: 'message';
  content: string;
};

export type HollyWsOutbound =
  | { type: 'token'; content: string }
  | { type: 'tool_call'; name: string; input: Record<string, unknown> }
  | { type: 'tool_result'; name: string; result: Record<string, unknown> }
  | { type: 'done'; content: string }
  | { type: 'error'; content: string };

/** Approval card data (extracted from tower tickets) */
export interface ApprovalCardData {
  ticket_id: number;
  run_id: string;
  ticket_type: string;
  risk_level: 'low' | 'medium' | 'high';
  status: string;
  tldr: string;
  why_stopped: string;
  created_at: string;
}

/** Chat entry — either a message or an inline card */
export type ChatEntry =
  | { kind: 'message'; message: HollyMessage }
  | { kind: 'approval'; card: ApprovalCardData }
  | { kind: 'tool_activity'; name: string; status: 'calling' | 'done'; result?: Record<string, unknown> };
