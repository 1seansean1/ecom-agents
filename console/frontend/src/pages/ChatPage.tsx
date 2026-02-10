import { useState, useRef, useEffect, useCallback } from 'react';
import Header from '@/components/layout/Header';
import {
  Send, Square, ChevronLeft, ChevronRight, Terminal, Users,
  Trash2, Plus, Copy, Check, Settings2, RotateCcw,
} from 'lucide-react';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface ToolCall {
  id: string;
  name: string;
  input: Record<string, unknown>;
  result?: { output?: string; error?: string };
  status: 'running' | 'done' | 'error';
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  provider?: string;
  model?: string;
  participant?: string;
  toolCalls?: ToolCall[];
  turn?: number;
}

interface ModelInfo { id: string; name: string; ctx: number; unsupported_params?: string[] }
interface ParamSpec { min: number; max: number; step: number; default: number | null }
interface ProviderInfo {
  name: string;
  models: ModelInfo[];
  params: Record<string, ParamSpec>;
}
type ProvidersMap = Record<string, ProviderInfo>;

interface SocraticParticipant {
  name: string;
  provider: string;
  model: string;
  system: string;
}

type ChatMode = 'standard' | 'code' | 'socratic';

const API = '/chat-ui/api';

/* ------------------------------------------------------------------ */
/*  Markdown renderer (minimal, no deps)                               */
/* ------------------------------------------------------------------ */

function renderMarkdown(raw: string): string {
  let h = raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // fenced code blocks
  h = h.replace(/```\w*\n([\s\S]*?)```/g, (_, code) =>
    `<pre class="chat-code-block"><code>${(code as string).trimEnd()}</code></pre>`);

  // inline code
  h = h.replace(/`([^`\n]+)`/g, '<code class="chat-inline-code">$1</code>');

  // bold / italic
  h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  h = h.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');

  // headers (only outside code blocks)
  h = h.replace(/^### (.+)$/gm, '<div class="chat-h3">$1</div>');
  h = h.replace(/^## (.+)$/gm, '<div class="chat-h2">$1</div>');
  h = h.replace(/^# (.+)$/gm, '<div class="chat-h1">$1</div>');

  // unordered lists
  h = h.replace(/^[-*] (.+)$/gm, '<div class="chat-li">&bull; $1</div>');

  // ordered lists
  h = h.replace(/^\d+\. (.+)$/gm, '<div class="chat-li">$1</div>');

  // line breaks (but not inside <pre>)
  const parts = h.split(/(<pre[\s\S]*?<\/pre>)/g);
  h = parts.map((p, i) => i % 2 === 0 ? p.replace(/\n/g, '<br/>') : p).join('');

  return h;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

let msgCounter = 0;
const uid = () => `m-${Date.now()}-${++msgCounter}`;

const PROVIDER_COLORS: Record<string, string> = {
  openai: 'text-blue-400',
  anthropic: 'text-purple-400',
  google: 'text-emerald-400',
  grok: 'text-orange-400',
};

const PROVIDER_BG: Record<string, string> = {
  openai: 'bg-blue-950/30 border-blue-500/20',
  anthropic: 'bg-purple-950/30 border-purple-500/20',
  google: 'bg-emerald-950/30 border-emerald-500/20',
  grok: 'bg-orange-950/30 border-orange-500/20',
};

const SOCRATIC_COLORS = [
  { text: 'text-cyan-400', bg: 'bg-cyan-950/30 border-cyan-500/20' },
  { text: 'text-amber-400', bg: 'bg-amber-950/30 border-amber-500/20' },
  { text: 'text-rose-400', bg: 'bg-rose-950/30 border-rose-500/20' },
  { text: 'text-lime-400', bg: 'bg-lime-950/30 border-lime-500/20' },
  { text: 'text-violet-400', bg: 'bg-violet-950/30 border-violet-500/20' },
  { text: 'text-teal-400', bg: 'bg-teal-950/30 border-teal-500/20' },
];

const CODE_TOOLS = [
  'bash_exec', 'read_file', 'write_file', 'edit_file', 'list_files', 'search_files',
];

/* ------------------------------------------------------------------ */
/*  ParamSlider — individual parameter control with disable support    */
/* ------------------------------------------------------------------ */

function ParamSlider({ label, value, onChange, spec, disabled }: {
  label: string;
  value: number | null;
  onChange: (v: number | null) => void;
  spec: { min: number; max: number; step: number; default: number | null };
  disabled: boolean;
}) {
  const isActive = value !== null && !disabled;
  const displayVal = value ?? spec.default ?? spec.min;
  const isFloat = spec.step < 1;

  return (
    <div className={`${disabled ? 'opacity-35 pointer-events-none' : ''}`}>
      <div className="flex items-center justify-between mb-0.5">
        <label className="text-[10px] text-[var(--color-text-muted)]">
          {label}
          {disabled && <span className="ml-1 text-[9px] italic">(n/a)</span>}
        </label>
        <div className="flex items-center gap-1">
          <span className="text-[10px] font-mono text-[var(--color-text)]">
            {isActive ? (isFloat ? displayVal.toFixed(2) : displayVal) : 'default'}
          </span>
          {!disabled && value !== null && (
            <button onClick={() => onChange(null)}
              className="text-[9px] text-[var(--color-text-muted)] hover:text-[var(--color-accent)] ml-1"
              title="Reset to default">x</button>
          )}
        </div>
      </div>
      <input type="range" min={spec.min} max={spec.max} step={spec.step}
        value={displayVal} disabled={disabled}
        onChange={e => onChange(parseFloat(e.target.value))}
        className="w-full h-1 rounded-full appearance-none cursor-pointer accent-[var(--color-accent)] bg-[var(--color-border)]"
        style={{ opacity: isActive ? 1 : 0.4 }} />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function ChatPage() {
  // --- Data ---
  const [providers, setProviders] = useState<ProvidersMap>({});
  const [validKeys, setValidKeys] = useState<Record<string, boolean>>({});

  // --- Chat state ---
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // --- Settings ---
  const [settingsOpen, setSettingsOpen] = useState(true);
  const [mode, setMode] = useState<ChatMode>('standard');
  const [provider, setProvider] = useState('openai');
  const [model, setModel] = useState('gpt-4o');
  const [systemPrompt, setSystemPrompt] = useState('');

  // --- Sampling params (null = use provider default) ---
  const [temperature, setTemperature] = useState<number | null>(null);
  const [topP, setTopP] = useState<number | null>(null);
  const [topK, setTopK] = useState<number | null>(null);
  const [maxTokens, setMaxTokens] = useState<number | null>(null);
  const [frequencyPenalty, setFrequencyPenalty] = useState<number | null>(null);
  const [presencePenalty, setPresencePenalty] = useState<number | null>(null);

  // --- Code mode ---
  const [codeWorkDir, setCodeWorkDir] = useState('c:\\Users\\seanp\\Workspace');
  const [codeModel, setCodeModel] = useState('claude-sonnet-4-5-20250929');
  const [codeMaxTurns, setCodeMaxTurns] = useState(25);
  const [codeTools, setCodeTools] = useState<string[]>([...CODE_TOOLS]);

  // --- Socratic mode ---
  const [socraticParticipants, setSocraticParticipants] = useState<SocraticParticipant[]>([]);
  const [socraticRounds, setSocraticRounds] = useState(1);

  // --- UI ---
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // --- Load models + keys on mount ---
  useEffect(() => {
    fetch(`${API}/models`).then(r => r.json()).then(setProviders).catch(() => {});
    fetch(`${API}/validate-keys`).then(r => r.json()).then(setValidKeys).catch(() => {});
    fetch(`${API}/socratic/defaults`).then(r => r.json()).then(setSocraticParticipants).catch(() => {});
  }, []);

  // --- Auto-scroll ---
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // --- Model list for current provider ---
  const modelList = providers[provider]?.models ?? [];
  const currentModelInfo = modelList.find(m => m.id === model);

  // --- Estimate tokens ---
  const estimateTokens = useCallback((msgs: ChatMessage[]) => {
    return msgs.reduce((sum, m) => sum + Math.max(1, Math.ceil(m.content.length / 4) + 4), 0);
  }, []);

  const contextUsed = estimateTokens(messages);
  const contextLimit = currentModelInfo?.ctx ?? 128000;
  const contextPct = Math.min(100, (contextUsed / contextLimit) * 100);

  // --- Param helpers ---
  const unsupported = currentModelInfo?.unsupported_params ?? [];
  const providerParams = providers[provider]?.params ?? {};
  const isParamDisabled = (name: string) => unsupported.includes(name) || !(name in providerParams);
  // Google uses max_output_tokens instead of max_tokens
  const maxTokensKey = provider === 'google' ? 'max_output_tokens' : 'max_tokens';

  const buildParams = (): Record<string, number> => {
    const p: Record<string, number> = {};
    if (temperature !== null && !isParamDisabled('temperature')) p.temperature = temperature;
    if (topP !== null && !isParamDisabled('top_p')) p.top_p = topP;
    if (topK !== null && !isParamDisabled('top_k')) p.top_k = topK;
    if (maxTokens !== null) {
      if (provider === 'google') p.max_output_tokens = maxTokens;
      else if (!isParamDisabled('max_tokens')) p.max_tokens = maxTokens;
    }
    if (frequencyPenalty !== null && !isParamDisabled('frequency_penalty')) p.frequency_penalty = frequencyPenalty;
    if (presencePenalty !== null && !isParamDisabled('presence_penalty')) p.presence_penalty = presencePenalty;
    return p;
  };

  // --- Copy message ---
  const copyMessage = (id: string, content: string) => {
    navigator.clipboard.writeText(content);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1500);
  };

  // --- Toggle tool expansion ---
  const toggleTool = (toolId: string) => {
    setExpandedTools(prev => {
      const next = new Set(prev);
      next.has(toolId) ? next.delete(toolId) : next.add(toolId);
      return next;
    });
  };

  // --- Stop generation ---
  const stopGeneration = () => {
    abortRef.current?.abort();
    setStreaming(false);
  };

  // --- Clear chat ---
  const clearChat = () => {
    setMessages([]);
  };

  // --- Send message ---
  const sendMessage = async () => {
    const text = input.trim();
    if (!text || streaming) return;

    const userMsg: ChatMessage = { id: uid(), role: 'user', content: text };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput('');
    setStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      if (mode === 'standard') {
        await streamStandard(newMessages, controller.signal);
      } else if (mode === 'code') {
        await streamCode(newMessages, controller.signal);
      } else if (mode === 'socratic') {
        await streamSocratic(text, newMessages, controller.signal);
      }
    } catch (err: unknown) {
      if ((err as Error).name !== 'AbortError') {
        const errMsg: ChatMessage = {
          id: uid(), role: 'assistant',
          content: `Error: ${(err as Error).message}`,
          provider, model,
        };
        setMessages(prev => [...prev, errMsg]);
      }
    } finally {
      setStreaming(false);
    }
  };

  // --- Standard chat stream ---
  const streamStandard = async (msgs: ChatMessage[], signal: AbortSignal) => {
    const apiMessages = msgs.map(m => ({ role: m.role, content: m.content }));

    const assistantId = uid();
    setMessages(prev => [...prev, {
      id: assistantId, role: 'assistant', content: '', provider, model,
    }]);

    const res = await fetch(`${API}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider, model, messages: apiMessages,
        params: buildParams(), system_prompt: systemPrompt,
      }),
      signal,
    });

    await processSSE(res, (data) => {
      if (data.token) {
        setMessages(prev => prev.map(m =>
          m.id === assistantId ? { ...m, content: m.content + data.token } : m
        ));
      }
      if (data.error) {
        setMessages(prev => prev.map(m =>
          m.id === assistantId ? { ...m, content: m.content + `\n\nError: ${data.error}` } : m
        ));
      }
    });
  };

  // --- Code mode stream ---
  const streamCode = async (msgs: ChatMessage[], signal: AbortSignal) => {
    const apiMessages = msgs.map(m => ({ role: m.role, content: m.content }));

    const assistantId = uid();
    const toolCallsMap = new Map<string, ToolCall>();

    setMessages(prev => [...prev, {
      id: assistantId, role: 'assistant', content: '', provider: 'anthropic', model: codeModel, toolCalls: [],
    }]);

    const res = await fetch(`${API}/claude-code/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages: apiMessages,
        system_prompt: systemPrompt,
        working_directory: codeWorkDir,
        max_turns: codeMaxTurns,
        model: codeModel,
        allowed_tools: codeTools,
      }),
      signal,
    });

    await processSSE(res, (data) => {
      if (data.turn) {
        setMessages(prev => prev.map(m =>
          m.id === assistantId ? { ...m, turn: data.turn } : m
        ));
      }
      if (data.token) {
        setMessages(prev => prev.map(m =>
          m.id === assistantId ? { ...m, content: m.content + data.token } : m
        ));
      }
      if (data.tool_call_start) {
        const tc: ToolCall = {
          id: data.tool_call_start.id,
          name: data.tool_call_start.name,
          input: {},
          status: 'running',
        };
        toolCallsMap.set(tc.id, tc);
        setMessages(prev => prev.map(m =>
          m.id === assistantId
            ? { ...m, toolCalls: [...(m.toolCalls ?? []), tc] }
            : m
        ));
      }
      if (data.tool_call_input) {
        const tc = toolCallsMap.get(data.tool_call_input.id);
        if (tc) {
          tc.input = data.tool_call_input.input;
          setMessages(prev => prev.map(m =>
            m.id === assistantId
              ? { ...m, toolCalls: m.toolCalls?.map(t => t.id === tc.id ? { ...tc } : t) }
              : m
          ));
        }
        // Auto-expand new tool calls
        setExpandedTools(prev => new Set(prev).add(data.tool_call_input.id));
      }
      if (data.tool_call_result) {
        const tc = toolCallsMap.get(data.tool_call_result.id);
        if (tc) {
          tc.result = data.tool_call_result.result;
          tc.status = data.tool_call_result.result?.error ? 'error' : 'done';
          setMessages(prev => prev.map(m =>
            m.id === assistantId
              ? { ...m, toolCalls: m.toolCalls?.map(t => t.id === tc.id ? { ...tc } : t) }
              : m
          ));
        }
      }
      if (data.error) {
        setMessages(prev => prev.map(m =>
          m.id === assistantId ? { ...m, content: m.content + `\n\nError: ${data.error}` } : m
        ));
      }
    });
  };

  // --- Socratic mode stream ---
  const streamSocratic = async (userMessage: string, msgs: ChatMessage[], signal: AbortSignal) => {
    const history = msgs.slice(0, -1).map(m => ({ role: m.role, content: m.content }));

    let currentParticipantIdx = -1;
    let currentMsgId = '';

    const res = await fetch(`${API}/socratic/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        participants: socraticParticipants,
        history,
        user_message: userMessage,
        rounds: socraticRounds,
      }),
      signal,
    });

    await processSSE(res, (data) => {
      if (data.participant_start) {
        currentParticipantIdx++;
        currentMsgId = uid();
        const p = data.participant_start;
        setMessages(prev => [...prev, {
          id: currentMsgId, role: 'assistant', content: '',
          provider: p.provider, model: p.model, participant: p.name,
        }]);
      }
      if (data.token && currentMsgId) {
        setMessages(prev => prev.map(m =>
          m.id === currentMsgId ? { ...m, content: m.content + data.token } : m
        ));
      }
      if (data.round) {
        // Round divider
        setMessages(prev => [...prev, {
          id: uid(), role: 'assistant', content: `--- Round ${data.round} ---`,
          participant: '__divider__',
        }]);
      }
      if (data.error) {
        setMessages(prev => [...prev, {
          id: uid(), role: 'assistant', content: `Error: ${data.error}`,
        }]);
      }
    });
  };

  // --- SSE processor ---
  const processSSE = async (
    res: Response,
    onData: (data: any) => void,
  ) => {
    const reader = res.body?.getReader();
    if (!reader) return;
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            if (data.done) return;
            onData(data);
          } catch { /* skip malformed */ }
        }
      }
    }
  };

  // --- Key handler ---
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // --- Socratic participant helpers ---
  const updateParticipant = (idx: number, updates: Partial<SocraticParticipant>) => {
    setSocraticParticipants(prev => prev.map((p, i) => i === idx ? { ...p, ...updates } : p));
  };
  const removeParticipant = (idx: number) => {
    if (socraticParticipants.length <= 2) return;
    setSocraticParticipants(prev => prev.filter((_, i) => i !== idx));
  };
  const addParticipant = () => {
    if (socraticParticipants.length >= 6) return;
    setSocraticParticipants(prev => [...prev, {
      name: `Participant ${prev.length + 1}`,
      provider: 'openai', model: 'gpt-4o-mini',
      system: 'You are a thoughtful participant in a Socratic roundtable.',
    }]);
  };

  /* ================================================================ */
  /*  RENDER                                                           */
  /* ================================================================ */

  return (
    <div className="flex flex-col h-full">
      <Header title="Chat" subtitle={
        mode === 'standard' ? `${providers[provider]?.name ?? provider} / ${currentModelInfo?.name ?? model}`
          : mode === 'code' ? 'Code Mode (Claude + Tools)'
          : `Socratic (${socraticParticipants.length} participants)`
      } />

      <div className="flex-1 flex overflow-hidden">
        {/* ---- Settings Panel ---- */}
        <div className={`shrink-0 border-r border-[var(--color-border)] bg-[var(--color-bg-card)] transition-all duration-200 overflow-y-auto ${settingsOpen ? 'w-64' : 'w-0'}`}>
          {settingsOpen && (
            <div className="p-3 space-y-4">
              {/* Mode */}
              <div>
                <div className="text-[10px] font-semibold text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Mode</div>
                <div className="flex gap-1">
                  {([['standard', 'Chat', null], ['code', 'Code', Terminal], ['socratic', 'Socratic', Users]] as const).map(([m, label, Icon]) => (
                    <button key={m} onClick={() => setMode(m as ChatMode)}
                      className={`flex-1 flex items-center justify-center gap-1 px-2 py-1.5 text-xs rounded-lg border transition-colors ${
                        mode === m
                          ? 'border-[var(--color-accent)] bg-[var(--color-accent)]/10 text-[var(--color-text)]'
                          : 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:border-[var(--color-text-muted)]'
                      }`}>
                      {Icon && <Icon size={12} />}
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Provider / Model (standard mode) */}
              {mode === 'standard' && (
                <>
                  <div>
                    <label className="text-[10px] font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">Provider</label>
                    <select value={provider} onChange={e => {
                      setProvider(e.target.value);
                      const first = providers[e.target.value]?.models[0];
                      if (first) setModel(first.id);
                    }}
                      className="w-full mt-1 px-2 py-1.5 text-xs rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)] text-[var(--color-text)] focus:border-[var(--color-accent)] focus:outline-none">
                      {Object.entries(providers).map(([key, p]) => (
                        <option key={key} value={key} disabled={validKeys[key] === false}>
                          {p.name}{validKeys[key] === false ? ' (no key)' : ''}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-[10px] font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">Model</label>
                    <select value={model} onChange={e => setModel(e.target.value)}
                      className="w-full mt-1 px-2 py-1.5 text-xs rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)] text-[var(--color-text)] focus:border-[var(--color-accent)] focus:outline-none">
                      {modelList.map(m => (
                        <option key={m.id} value={m.id}>{m.name} ({Math.round(m.ctx / 1000)}K)</option>
                      ))}
                    </select>
                  </div>
                </>
              )}

              {/* Sampling Parameters (standard mode only) */}
              {mode === 'standard' && (
                <div className="space-y-2 pt-2 border-t border-[var(--color-border)]">
                  <div className="text-[10px] font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">Parameters</div>
                  {/* Temperature */}
                  {('temperature' in providerParams) && (
                    <ParamSlider label="Temperature" value={temperature}
                      onChange={setTemperature} spec={providerParams.temperature}
                      disabled={isParamDisabled('temperature')} />
                  )}
                  {/* Top P */}
                  {('top_p' in providerParams) && (
                    <ParamSlider label="Top P" value={topP}
                      onChange={setTopP} spec={providerParams.top_p}
                      disabled={isParamDisabled('top_p')} />
                  )}
                  {/* Top K */}
                  {('top_k' in providerParams) && (
                    <ParamSlider label="Top K" value={topK}
                      onChange={setTopK} spec={providerParams.top_k}
                      disabled={isParamDisabled('top_k')} />
                  )}
                  {/* Max Tokens */}
                  {(maxTokensKey in providerParams) && (
                    <ParamSlider label="Max Tokens" value={maxTokens}
                      onChange={setMaxTokens} spec={providerParams[maxTokensKey]}
                      disabled={isParamDisabled(maxTokensKey)} />
                  )}
                  {/* Frequency Penalty */}
                  {('frequency_penalty' in providerParams) && (
                    <ParamSlider label="Freq Penalty" value={frequencyPenalty}
                      onChange={setFrequencyPenalty} spec={providerParams.frequency_penalty}
                      disabled={isParamDisabled('frequency_penalty')} />
                  )}
                  {/* Presence Penalty */}
                  {('presence_penalty' in providerParams) && (
                    <ParamSlider label="Pres Penalty" value={presencePenalty}
                      onChange={setPresencePenalty} spec={providerParams.presence_penalty}
                      disabled={isParamDisabled('presence_penalty')} />
                  )}
                </div>
              )}

              {/* System Prompt */}
              <div>
                <label className="text-[10px] font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">System Prompt</label>
                <textarea value={systemPrompt} onChange={e => setSystemPrompt(e.target.value)}
                  placeholder="You are a helpful assistant..."
                  rows={3}
                  className="w-full mt-1 px-2 py-1.5 text-xs rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)] text-[var(--color-text)] focus:border-[var(--color-accent)] focus:outline-none resize-y" />
              </div>

              {/* Code Mode Settings */}
              {mode === 'code' && (
                <div className="space-y-3 pt-2 border-t border-[var(--color-border)]">
                  <div className="text-[10px] font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">Code Settings</div>
                  <div>
                    <label className="text-[10px] text-[var(--color-text-muted)]">Working Directory</label>
                    <input type="text" value={codeWorkDir} onChange={e => setCodeWorkDir(e.target.value)}
                      className="w-full mt-1 px-2 py-1.5 text-xs font-mono rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)] text-[var(--color-text)] focus:border-[var(--color-accent)] focus:outline-none" />
                  </div>
                  <div>
                    <label className="text-[10px] text-[var(--color-text-muted)]">Model</label>
                    <select value={codeModel} onChange={e => setCodeModel(e.target.value)}
                      className="w-full mt-1 px-2 py-1.5 text-xs rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)] text-[var(--color-text)] focus:border-[var(--color-accent)] focus:outline-none">
                      <option value="claude-opus-4-6">Opus 4.6</option>
                      <option value="claude-sonnet-4-5-20250929">Sonnet 4.5</option>
                      <option value="claude-haiku-4-5-20251001">Haiku 4.5</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-[10px] text-[var(--color-text-muted)]">Max Turns</label>
                    <input type="number" value={codeMaxTurns} onChange={e => setCodeMaxTurns(Number(e.target.value))}
                      min={1} max={50}
                      className="w-full mt-1 px-2 py-1.5 text-xs rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)] text-[var(--color-text)] focus:border-[var(--color-accent)] focus:outline-none" />
                  </div>
                  <div>
                    <label className="text-[10px] text-[var(--color-text-muted)]">Tools</label>
                    <div className="mt-1 space-y-1">
                      {CODE_TOOLS.map(tool => (
                        <label key={tool} className="flex items-center gap-2 text-xs text-[var(--color-text)] cursor-pointer">
                          <input type="checkbox" checked={codeTools.includes(tool)}
                            onChange={e => {
                              setCodeTools(prev => e.target.checked
                                ? [...prev, tool]
                                : prev.filter(t => t !== tool));
                            }}
                            className="rounded border-[var(--color-border)] accent-[var(--color-accent)]" />
                          <span className="font-mono text-[10px]">{tool}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Socratic Settings */}
              {mode === 'socratic' && (
                <div className="space-y-3 pt-2 border-t border-[var(--color-border)]">
                  <div className="flex items-center justify-between">
                    <div className="text-[10px] font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">Participants</div>
                    <div className="flex items-center gap-2">
                      <label className="text-[10px] text-[var(--color-text-muted)]">Rounds:</label>
                      <select value={socraticRounds} onChange={e => setSocraticRounds(Number(e.target.value))}
                        className="px-1.5 py-0.5 text-[10px] rounded bg-[var(--color-bg)] border border-[var(--color-border)] text-[var(--color-text)]">
                        <option value={1}>1</option>
                        <option value={2}>2</option>
                        <option value={3}>3</option>
                      </select>
                    </div>
                  </div>
                  {socraticParticipants.map((p, i) => {
                    const color = SOCRATIC_COLORS[i % SOCRATIC_COLORS.length];
                    return (
                      <div key={i} className={`p-2 rounded-lg border ${color.bg} space-y-1.5`}>
                        <div className="flex items-center justify-between">
                          <input type="text" value={p.name}
                            onChange={e => updateParticipant(i, { name: e.target.value })}
                            className={`bg-transparent text-xs font-semibold ${color.text} focus:outline-none w-full`} />
                          <button onClick={() => removeParticipant(i)}
                            className="text-[var(--color-text-muted)] hover:text-red-400 ml-2"
                            disabled={socraticParticipants.length <= 2}>
                            <Trash2 size={10} />
                          </button>
                        </div>
                        <div className="flex gap-1">
                          <select value={p.provider} onChange={e => {
                            const prov = e.target.value;
                            const firstModel = providers[prov]?.models[0]?.id ?? '';
                            updateParticipant(i, { provider: prov, model: firstModel });
                          }}
                            className="flex-1 px-1 py-0.5 text-[10px] rounded bg-[var(--color-bg)] border border-[var(--color-border)] text-[var(--color-text)]">
                            {Object.entries(providers).map(([k, pv]) => (
                              <option key={k} value={k}>{pv.name}</option>
                            ))}
                          </select>
                          <select value={p.model} onChange={e => updateParticipant(i, { model: e.target.value })}
                            className="flex-1 px-1 py-0.5 text-[10px] rounded bg-[var(--color-bg)] border border-[var(--color-border)] text-[var(--color-text)]">
                            {(providers[p.provider]?.models ?? []).map(m => (
                              <option key={m.id} value={m.id}>{m.name}</option>
                            ))}
                          </select>
                        </div>
                        <textarea value={p.system} onChange={e => updateParticipant(i, { system: e.target.value })}
                          rows={2} placeholder="Persona prompt..."
                          className="w-full px-1.5 py-1 text-[10px] rounded bg-[var(--color-bg)] border border-[var(--color-border)] text-[var(--color-text)] focus:outline-none resize-y" />
                      </div>
                    );
                  })}
                  <button onClick={addParticipant} disabled={socraticParticipants.length >= 6}
                    className="w-full py-1.5 text-[10px] rounded-lg border border-dashed border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:border-[var(--color-text-muted)] transition-colors disabled:opacity-40">
                    <Plus size={10} className="inline mr-1" />Add Participant
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ---- Settings toggle ---- */}
        <button onClick={() => setSettingsOpen(!settingsOpen)}
          className="shrink-0 w-5 flex items-center justify-center border-r border-[var(--color-border)] bg-[var(--color-bg-card)] text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors">
          {settingsOpen ? <ChevronLeft size={12} /> : <Settings2 size={12} />}
        </button>

        {/* ---- Main chat area ---- */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Context bar */}
          <div className="flex items-center gap-3 px-4 py-1.5 border-b border-[var(--color-border)] bg-[var(--color-bg-card)]">
            <div className="flex-1 flex items-center gap-2">
              <div className="flex-1 h-1.5 rounded-full bg-[var(--color-bg)] overflow-hidden">
                <div className={`h-full rounded-full transition-all duration-300 ${
                  contextPct > 90 ? 'bg-red-500' : contextPct > 75 ? 'bg-yellow-500' : 'bg-[var(--color-accent)]'
                }`} style={{ width: `${contextPct}%` }} />
              </div>
              <span className="text-[10px] text-[var(--color-text-muted)] whitespace-nowrap">
                {contextUsed.toLocaleString()} / {(contextLimit / 1000).toFixed(0)}K tokens
              </span>
            </div>
            <div className="flex items-center gap-1">
              <button onClick={clearChat}
                className="p-1 rounded text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
                title="Clear chat">
                <Trash2 size={12} />
              </button>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full text-[var(--color-text-muted)]">
                <div className="text-3xl mb-3">
                  {mode === 'standard' ? '💬' : mode === 'code' ? '⌨️' : '🏛️'}
                </div>
                <div className="text-sm font-semibold mb-1">
                  {mode === 'standard' ? 'Start a conversation'
                    : mode === 'code' ? 'Code Mode — Claude with tools'
                    : 'Socratic Roundtable'}
                </div>
                <div className="text-xs max-w-sm text-center">
                  {mode === 'standard' ? 'Send a message to chat with AI. Switch providers and models anytime.'
                    : mode === 'code' ? `Working in ${codeWorkDir}. Claude will read, write, and edit files autonomously.`
                    : `${socraticParticipants.length} AI personas will discuss your prompt in ${socraticRounds} round${socraticRounds > 1 ? 's' : ''}.`}
                </div>
              </div>
            )}

            {messages.map(msg => {
              // Round divider
              if (msg.participant === '__divider__') {
                return (
                  <div key={msg.id} className="flex items-center gap-3 py-2">
                    <div className="flex-1 h-px bg-[var(--color-border)]" />
                    <span className="text-[10px] text-[var(--color-text-muted)] font-semibold">{msg.content}</span>
                    <div className="flex-1 h-px bg-[var(--color-border)]" />
                  </div>
                );
              }

              const isUser = msg.role === 'user';
              const provColor = PROVIDER_COLORS[msg.provider ?? ''] ?? 'text-[var(--color-text)]';
              const provBg = PROVIDER_BG[msg.provider ?? ''] ?? 'bg-[var(--color-bg-card)] border-[var(--color-border)]';

              // Socratic participant color
              const pIdx = msg.participant
                ? socraticParticipants.findIndex(p => p.name === msg.participant)
                : -1;
              const socColor = pIdx >= 0 ? SOCRATIC_COLORS[pIdx % SOCRATIC_COLORS.length] : null;

              return (
                <div key={msg.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[85%] rounded-xl px-3 py-2 border text-sm ${
                    isUser
                      ? 'bg-[var(--color-accent)]/10 border-[var(--color-accent)]/30 text-[var(--color-text)]'
                      : socColor
                        ? `${socColor.bg} text-[var(--color-text)]`
                        : `${provBg} text-[var(--color-text)]`
                  }`}>
                    {/* Header badge */}
                    {!isUser && (
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <div className="flex items-center gap-1.5">
                          {msg.participant && (
                            <span className={`text-[10px] font-bold ${socColor?.text ?? provColor}`}>
                              {msg.participant}
                            </span>
                          )}
                          {msg.provider && (
                            <span className={`text-[10px] ${provColor}`}>
                              {providers[msg.provider]?.name ?? msg.provider}
                            </span>
                          )}
                          {msg.model && (
                            <span className="text-[10px] text-[var(--color-text-muted)]">
                              {providers[msg.provider ?? '']?.models.find(m => m.id === msg.model)?.name ?? msg.model}
                            </span>
                          )}
                          {msg.turn && (
                            <span className="text-[10px] text-[var(--color-text-muted)]">
                              Turn {msg.turn}
                            </span>
                          )}
                        </div>
                        <button onClick={() => copyMessage(msg.id, msg.content)}
                          className="text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors">
                          {copiedId === msg.id ? <Check size={10} /> : <Copy size={10} />}
                        </button>
                      </div>
                    )}

                    {/* Content */}
                    {msg.content && (
                      <div className="chat-markdown text-xs leading-relaxed"
                        dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }} />
                    )}

                    {/* Tool calls (Code mode) */}
                    {msg.toolCalls && msg.toolCalls.length > 0 && (
                      <div className="mt-2 space-y-1.5">
                        {msg.toolCalls.map(tc => {
                          const isExpanded = expandedTools.has(tc.id);
                          return (
                            <div key={tc.id} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] overflow-hidden">
                              <button onClick={() => toggleTool(tc.id)}
                                className="w-full flex items-center gap-2 px-2 py-1.5 text-[10px] hover:bg-[var(--color-bg-hover)] transition-colors">
                                <Terminal size={10} className="text-emerald-400 shrink-0" />
                                <span className="font-mono font-semibold text-emerald-400">{tc.name}</span>
                                <span className={`ml-auto text-[9px] font-bold px-1.5 py-0.5 rounded ${
                                  tc.status === 'running' ? 'bg-yellow-900/40 text-yellow-400'
                                    : tc.status === 'error' ? 'bg-red-900/40 text-red-400'
                                    : 'bg-emerald-900/40 text-emerald-400'
                                }`}>
                                  {tc.status === 'running' ? 'RUNNING' : tc.status === 'error' ? 'ERROR' : 'DONE'}
                                </span>
                                <ChevronRight size={10} className={`text-[var(--color-text-muted)] transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                              </button>
                              {isExpanded && (
                                <div className="border-t border-[var(--color-border)]">
                                  {/* Input */}
                                  <div className="px-2 py-1.5">
                                    <div className="text-[9px] text-[var(--color-text-muted)] font-semibold mb-0.5">INPUT</div>
                                    <pre className="text-[10px] font-mono text-[var(--color-text)] whitespace-pre-wrap break-all">
                                      {JSON.stringify(tc.input, null, 2)}
                                    </pre>
                                  </div>
                                  {/* Output */}
                                  {tc.result && (
                                    <div className="px-2 py-1.5 border-t border-[var(--color-border)]">
                                      <div className="text-[9px] text-[var(--color-text-muted)] font-semibold mb-0.5">OUTPUT</div>
                                      <pre className={`text-[10px] font-mono whitespace-pre-wrap break-all max-h-48 overflow-y-auto ${
                                        tc.name === 'bash_exec'
                                          ? 'bg-black/40 text-emerald-400 p-1.5 rounded'
                                          : tc.result.error
                                            ? 'text-red-400'
                                            : 'text-[var(--color-text)]'
                                      }`}>
                                        {tc.result.output ?? tc.result.error ?? '(no output)'}
                                      </pre>
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {/* Streaming indicator */}
            {streaming && (
              <div className="flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
                <div className="flex gap-1">
                  <div className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)] animate-pulse" />
                  <div className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)] animate-pulse [animation-delay:150ms]" />
                  <div className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)] animate-pulse [animation-delay:300ms]" />
                </div>
                {mode === 'code' ? 'Claude is thinking...' : 'Generating...'}
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input area */}
          <div className="border-t border-[var(--color-border)] bg-[var(--color-bg-card)] p-3">
            <div className="flex items-end gap-2">
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder={
                  mode === 'standard' ? 'Type a message...'
                    : mode === 'code' ? 'Ask Claude to read, write, or edit files...'
                    : 'Pose a question for the roundtable...'
                }
                rows={1}
                className="flex-1 px-3 py-2 text-sm rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)] text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] focus:border-[var(--color-accent)] focus:outline-none resize-none"
                style={{ minHeight: '38px', maxHeight: '120px' }}
                onInput={e => {
                  const el = e.target as HTMLTextAreaElement;
                  el.style.height = 'auto';
                  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
                }}
              />
              {streaming ? (
                <button onClick={stopGeneration}
                  className="p-2 rounded-lg bg-red-500/20 border border-red-500/30 text-red-400 hover:bg-red-500/30 transition-colors"
                  title="Stop generation">
                  <Square size={16} />
                </button>
              ) : (
                <button onClick={sendMessage} disabled={!input.trim()}
                  className="p-2 rounded-lg bg-[var(--color-accent)] text-white hover:opacity-90 transition-opacity disabled:opacity-40"
                  title="Send (Enter)">
                  <Send size={16} />
                </button>
              )}
            </div>
            <div className="flex items-center justify-between mt-1.5 px-1">
              <span className="text-[10px] text-[var(--color-text-muted)]">
                {mode === 'standard'
                  ? 'Enter to send, Shift+Enter for new line'
                  : mode === 'code'
                    ? `Code: ${codeWorkDir}`
                    : `${socraticParticipants.length} participants, ${socraticRounds} round${socraticRounds > 1 ? 's' : ''}`}
              </span>
              {mode === 'socratic' && (
                <button onClick={() => {
                  fetch(`${API}/socratic/defaults`).then(r => r.json()).then(setSocraticParticipants);
                }}
                  className="text-[10px] text-[var(--color-text-muted)] hover:text-[var(--color-text)] flex items-center gap-1">
                  <RotateCcw size={9} /> Reset participants
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
