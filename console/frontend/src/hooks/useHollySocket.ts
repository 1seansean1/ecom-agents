/**
 * useHollySocket — WebSocket hook for real-time Holly Grace chat streaming.
 *
 * Connects to /ws/holly on the agents service and handles:
 * - Token-by-token streaming of Holly's responses
 * - Tool call / result notifications
 * - Reconnection with backoff
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { HollyWsOutbound } from '@/types/holly';

const WS_BASE = import.meta.env.VITE_WS_URL || 'ws://localhost:8050';

interface UseHollySocketOptions {
  sessionId?: string;
  token?: string;
  onToken?: (text: string) => void;
  onToolCall?: (name: string, input: Record<string, unknown>) => void;
  onToolResult?: (name: string, result: Record<string, unknown>) => void;
  onDone?: (fullText: string) => void;
  onError?: (error: string) => void;
}

export function useHollySocket(options: UseHollySocketOptions) {
  const {
    sessionId = 'default',
    token,
    onToken,
    onToolCall,
    onToolResult,
    onDone,
    onError,
  } = options;

  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const reconnectDelay = useRef(1000);

  const connect = useCallback(() => {
    if (!token) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setConnecting(true);
    const url = `${WS_BASE}/ws/holly?token=${encodeURIComponent(token)}&session_id=${encodeURIComponent(sessionId)}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      setConnecting(false);
      reconnectDelay.current = 1000;
    };

    ws.onmessage = (event) => {
      try {
        const msg: HollyWsOutbound = JSON.parse(event.data);
        switch (msg.type) {
          case 'token':
            onToken?.(msg.content);
            break;
          case 'tool_call':
            onToolCall?.(msg.name, msg.input);
            break;
          case 'tool_result':
            onToolResult?.(msg.name, msg.result);
            break;
          case 'done':
            onDone?.(msg.content);
            break;
          case 'error':
            onError?.(msg.content);
            break;
        }
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      setConnected(false);
      setConnecting(false);
      wsRef.current = null;
      // Reconnect with backoff
      reconnectTimer.current = setTimeout(() => {
        reconnectDelay.current = Math.min(reconnectDelay.current * 2, 30000);
        connect();
      }, reconnectDelay.current);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [token, sessionId, onToken, onToolCall, onToolResult, onDone, onError]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const sendMessage = useCallback((content: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'message', content }));
      return true;
    }
    return false;
  }, []);

  return { connected, connecting, sendMessage };
}
