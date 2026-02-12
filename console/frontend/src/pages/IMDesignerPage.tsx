import { useEffect, useState, useCallback } from 'react';
import Header from '@/components/layout/Header';
import { fetchJson, postJson, deleteJson } from '@/lib/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface IMWorkspaceSummary {
  workspace_id: string;
  raw_intent: string;
  stage: string;
  version: number;
  created_at: string;
  updated_at: string;
}

interface FeasibilityDetail {
  rank_coverage: boolean | null;
  coupling_coverage: boolean | null;
  power_coverage: boolean | null;
  governance_margin: number | null;
  axes_violating_power: string[];
  delta_norm: number | null;
  remediation: { type: string; detail: string; minimum_additional_rank?: number | null; minimum_additional_power_axes?: number | null } | null;
}

interface IMWorkspaceDetail {
  workspace_id: string;
  stage: string;
  version: number;
  raw_intent: string;
  created_at: string | null;
  updated_at: string | null;
  goal_tuple: Record<string, unknown>;
  predicate_count: number;
  block_count: number;
  coupling_locked: boolean;
  codimension: number | null;
  regime: string | null;
  verdict: string | null;
  feasibility: FeasibilityDetail | null;
  spawned_agents: string[];
  workflow_id: string | null;
  initial_run_id: string | null;
  audit_trail: AuditEntry[];
}

interface IMPredicate {
  id: string;
  name: string;
  description: string;
  block_id: string;
  epsilon_g: number;
  horizon_t: number;
  severity: string;
  measurement_map: string;
  quality_assessment: string;
  owner_agent?: string;
  intervention_policy?: string;
}

interface IMBlock {
  id: string;
  name: string;
  predicate_ids: string[];
  intra_rank: number;
}

interface CrossCoupling {
  from_block: string;
  to_block: string;
  rho: number;
  mechanism: string;
  direction: string;
}

interface IMWorkspaceFull {
  workspace_id: string;
  stage: string;
  version: number;
  raw_intent: string;
  predicates: IMPredicate[];
  predicate_blocks: IMBlock[];
  cross_block_coupling: CrossCoupling[];
  coupling_matrix: { M?: number[][]; locked?: boolean; human_overrides?: unknown[] };
  codimension: { eigenspectrum?: { index: number; value: number; block_attribution?: string }[]; cod_pi_g?: number; tau?: number };
  assignment: { agents?: { agent_id: string; name: string; assigned_predicates: string[]; model_family: string }[] };
  feasibility: Record<string, unknown>;
  audit_trail: AuditEntry[];
}

interface AuditEntry {
  stage: string;
  tool_name: string;
  input_summary: string;
  output_summary: string;
  created_at: string;
}

interface PipelineResult {
  workspace_id: string;
  verdict?: string;
  stage?: string;
  error?: string;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STAGES = [
  { key: 'created', label: 'Created', step: 0 },
  { key: 'goal_parsed', label: 'Goal Parsed', step: 1 },
  { key: 'predicates_generated', label: 'Predicates', step: 2 },
  { key: 'coupling_built', label: 'Coupling', step: 3 },
  { key: 'codimension_estimated', label: 'Codimension', step: 4 },
  { key: 'rank_budgeted', label: 'Rank Budget', step: 5 },
  { key: 'memory_designed', label: 'Memory', step: 6 },
  { key: 'agents_synthesized', label: 'Agents', step: 7 },
  { key: 'workflow_synthesized', label: 'Workflow', step: 8 },
  { key: 'feasibility_validated', label: 'Feasibility', step: 9 },
  { key: 'agents_spawned', label: 'Spawned', step: 10 },
  { key: 'deployed', label: 'Deployed', step: 11 },
];

const STAGE_INDEX: Record<string, number> = {};
STAGES.forEach((s) => { STAGE_INDEX[s.key] = s.step; });

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'bg-red-900/50 text-red-300 border-red-800/50',
  high: 'bg-orange-900/40 text-orange-300 border-orange-800/50',
  medium: 'bg-yellow-900/40 text-yellow-300 border-yellow-800/50',
  low: 'bg-green-900/40 text-green-300 border-green-800/50',
};

const VERDICT_COLORS: Record<string, string> = {
  feasible: 'bg-green-900/40 text-green-400',
  infeasible: 'bg-red-900/40 text-red-400',
};

type DetailTab = 'overview' | 'predicates' | 'coupling' | 'audit';

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function PipelineProgress({ stage }: { stage: string }) {
  const currentStep = STAGE_INDEX[stage] ?? 0;
  return (
    <div className="flex items-center gap-1">
      {STAGES.map((s) => (
        <div key={s.key} className="flex items-center">
          <div
            className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-mono transition-colors ${
              s.step < currentStep
                ? 'bg-green-600 text-white'
                : s.step === currentStep
                ? 'bg-[var(--color-accent)] text-white'
                : 'bg-[var(--color-bg-hover)] text-[var(--color-text-muted)]'
            }`}
            title={s.label}
          >
            {s.step}
          </div>
          {s.step < STAGES.length - 1 && (
            <div
              className={`w-3 h-0.5 ${
                s.step < currentStep ? 'bg-green-600' : 'bg-[var(--color-border)]'
              }`}
            />
          )}
        </div>
      ))}
    </div>
  );
}

function WorkspaceCard({
  ws,
  selected,
  onSelect,
  onDelete,
}: {
  ws: IMWorkspaceSummary;
  selected: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      className={`rounded-lg border p-3 cursor-pointer transition-colors ${
        selected
          ? 'border-[var(--color-accent)] bg-[var(--color-accent)]/10'
          : 'border-[var(--color-border)] bg-[var(--color-bg-card)] hover:border-[var(--color-accent)]/50'
      }`}
      onClick={onSelect}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium line-clamp-2">{ws.raw_intent}</p>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="text-[var(--color-text-muted)] hover:text-red-400 text-xs shrink-0"
          title="Delete workspace"
        >
          ×
        </button>
      </div>
      <div className="mt-2">
        <PipelineProgress stage={ws.stage} />
      </div>
      <div className="mt-1 flex items-center gap-2 text-[10px] text-[var(--color-text-muted)] font-mono">
        <span>{ws.workspace_id.slice(0, 8)}</span>
        <span>v{ws.version}</span>
        <span>{ws.updated_at ? new Date(ws.updated_at).toLocaleDateString() : ''}</span>
      </div>
    </div>
  );
}

function StatBox({ label, value, color }: { label: string; value: string | number | null; color?: string }) {
  return (
    <div className="bg-[var(--color-bg-card)] rounded-lg border border-[var(--color-border)] p-3">
      <div className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider">{label}</div>
      <div className={`text-lg font-mono mt-1 ${color ?? 'text-[var(--color-text)]'}`}>
        {value ?? '---'}
      </div>
    </div>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const s = severity.toLowerCase();
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono border ${SEVERITY_COLORS[s] ?? 'bg-[var(--color-bg-hover)] text-[var(--color-text-muted)]'}`}>
      {s.toUpperCase()}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Predicate Table
// ---------------------------------------------------------------------------

function PredicateTable({ predicates, blocks }: { predicates: IMPredicate[]; blocks: IMBlock[] }) {
  const [sortCol, setSortCol] = useState<'id' | 'severity' | 'epsilon_g' | 'block_id'>('id');
  const [sortAsc, setSortAsc] = useState(true);
  const [filterBlock, setFilterBlock] = useState<string>('all');

  const toggleSort = (col: typeof sortCol) => {
    if (sortCol === col) setSortAsc(!sortAsc);
    else { setSortCol(col); setSortAsc(true); }
  };

  const sevOrder: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };

  const filtered = filterBlock === 'all' ? predicates : predicates.filter((p) => p.block_id === filterBlock);
  const sorted = [...filtered].sort((a, b) => {
    let cmp = 0;
    if (sortCol === 'id') cmp = a.id.localeCompare(b.id);
    else if (sortCol === 'severity') cmp = (sevOrder[a.severity] ?? 5) - (sevOrder[b.severity] ?? 5);
    else if (sortCol === 'epsilon_g') cmp = a.epsilon_g - b.epsilon_g;
    else if (sortCol === 'block_id') cmp = a.block_id.localeCompare(b.block_id);
    return sortAsc ? cmp : -cmp;
  });

  const SortHeader = ({ col, label }: { col: typeof sortCol; label: string }) => (
    <th
      className="px-3 py-2 text-left font-medium text-[var(--color-text-muted)] cursor-pointer hover:text-[var(--color-accent)] select-none"
      onClick={() => toggleSort(col)}
    >
      {label} {sortCol === col ? (sortAsc ? '\u25B2' : '\u25BC') : ''}
    </th>
  );

  return (
    <div className="bg-[var(--color-bg-card)] rounded-lg border border-[var(--color-border)] overflow-hidden">
      <div className="p-3 border-b border-[var(--color-border)] flex items-center justify-between">
        <h3 className="text-sm font-semibold">Failure Predicates ({predicates.length})</h3>
        <select
          value={filterBlock}
          onChange={(e) => setFilterBlock(e.target.value)}
          className="text-xs bg-[var(--color-bg)] border border-[var(--color-border)] rounded px-2 py-1 text-[var(--color-text)]"
        >
          <option value="all">All Blocks</option>
          {blocks.map((b) => (
            <option key={b.id} value={b.id}>{b.id} — {b.name} ({b.predicate_ids.length})</option>
          ))}
        </select>
      </div>
      <div className="overflow-auto max-h-[400px]">
        <table className="w-full text-xs">
          <thead className="bg-[var(--color-bg-hover)] sticky top-0">
            <tr>
              <SortHeader col="id" label="ID" />
              <SortHeader col="block_id" label="Block" />
              <th className="px-3 py-2 text-left font-medium text-[var(--color-text-muted)]">Description</th>
              <SortHeader col="severity" label="Severity" />
              <SortHeader col="epsilon_g" label={'\u03B5_g'} />
              <th className="px-3 py-2 text-left font-medium text-[var(--color-text-muted)]">Horizon</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((p) => (
              <tr key={p.id} className="border-t border-[var(--color-border)] hover:bg-[var(--color-bg-hover)]">
                <td className="px-3 py-1.5 font-mono text-[var(--color-accent)] whitespace-nowrap">{p.id}</td>
                <td className="px-3 py-1.5 font-mono text-[var(--color-text-muted)] whitespace-nowrap">{p.block_id}</td>
                <td className="px-3 py-1.5 max-w-[300px]">
                  <div className="truncate" title={p.description || p.name}>{p.description || p.name}</div>
                </td>
                <td className="px-3 py-1.5"><SeverityBadge severity={p.severity} /></td>
                <td className="px-3 py-1.5 font-mono">{p.epsilon_g}</td>
                <td className="px-3 py-1.5 font-mono text-[var(--color-text-muted)]">{p.horizon_t}s</td>
              </tr>
            ))}
            {sorted.length === 0 && (
              <tr><td colSpan={6} className="px-3 py-4 text-center text-[var(--color-text-muted)]">No predicates</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Coupling Heatmap
// ---------------------------------------------------------------------------

function CouplingHeatmap({ matrix, predicates }: { matrix: number[][]; predicates: IMPredicate[] }) {
  if (!matrix.length) return null;
  const n = matrix.length;
  const cellSize = Math.min(24, Math.max(12, Math.floor(500 / n)));

  const colorForValue = (v: number): string => {
    if (v >= 0.9) return '#dc2626';
    if (v >= 0.7) return '#ea580c';
    if (v >= 0.5) return '#d97706';
    if (v >= 0.3) return '#ca8a04';
    if (v >= 0.1) return '#4d7c0f';
    if (v > 0) return '#166534';
    return '#1e293b';
  };

  return (
    <div className="bg-[var(--color-bg-card)] rounded-lg border border-[var(--color-border)] overflow-hidden">
      <div className="p-3 border-b border-[var(--color-border)]">
        <h3 className="text-sm font-semibold">Coupling Matrix ({n}x{n})</h3>
        <p className="text-[10px] text-[var(--color-text-muted)] mt-1">
          M = Cov_v(g) — darker = stronger coupling
        </p>
      </div>
      <div className="p-3 overflow-auto">
        <div className="inline-block">
          {/* Column headers */}
          <div className="flex" style={{ marginLeft: cellSize * 2 }}>
            {predicates.slice(0, n).map((p, i) => (
              <div
                key={i}
                className="text-[8px] text-[var(--color-text-muted)] font-mono overflow-hidden"
                style={{ width: cellSize, textAlign: 'center' }}
                title={p.id}
              >
                {n <= 20 ? p.id.replace('f_', '') : ''}
              </div>
            ))}
          </div>
          {/* Matrix rows */}
          {matrix.map((row, i) => (
            <div key={i} className="flex items-center">
              <div
                className="text-[8px] text-[var(--color-text-muted)] font-mono text-right pr-1"
                style={{ width: cellSize * 2 }}
                title={predicates[i]?.id}
              >
                {predicates[i]?.id.replace('f_', '') ?? i}
              </div>
              {row.map((v, j) => (
                <div
                  key={j}
                  style={{
                    width: cellSize,
                    height: cellSize,
                    backgroundColor: colorForValue(v),
                    border: '1px solid rgba(0,0,0,0.2)',
                  }}
                  title={`${predicates[i]?.id ?? i} x ${predicates[j]?.id ?? j}: ${v.toFixed(3)}`}
                />
              ))}
            </div>
          ))}
          {/* Legend */}
          <div className="flex items-center gap-2 mt-2 text-[10px] text-[var(--color-text-muted)]">
            <span>0</span>
            {[0, 0.1, 0.3, 0.5, 0.7, 0.9].map((v) => (
              <div key={v} className="w-4 h-3 rounded-sm" style={{ backgroundColor: colorForValue(v) }} title={String(v)} />
            ))}
            <span>1</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Eigenspectrum Chart
// ---------------------------------------------------------------------------

function EigenspectrumChart({ eigenspectrum, tau }: { eigenspectrum: { index: number; value: number; block_attribution?: string }[]; tau: number }) {
  if (!eigenspectrum?.length) return null;
  const maxVal = Math.max(...eigenspectrum.map((e) => e.value), 0.1);
  const barWidth = Math.min(40, Math.max(16, Math.floor(400 / eigenspectrum.length)));

  return (
    <div className="bg-[var(--color-bg-card)] rounded-lg border border-[var(--color-border)] overflow-hidden">
      <div className="p-3 border-b border-[var(--color-border)]">
        <h3 className="text-sm font-semibold">Eigenspectrum</h3>
        <p className="text-[10px] text-[var(--color-text-muted)] mt-1">
          {eigenspectrum.filter((e) => e.value > tau).length} eigenvalues above {'\u03C4'}={tau} threshold
        </p>
      </div>
      <div className="p-3 overflow-auto">
        <div className="flex items-end gap-1" style={{ height: 120 }}>
          {eigenspectrum.map((e) => {
            const pct = (e.value / maxVal) * 100;
            const aboveTau = e.value > tau;
            return (
              <div key={e.index} className="flex flex-col items-center" style={{ width: barWidth }}>
                <div
                  className={`w-full rounded-t transition-all ${aboveTau ? 'bg-[var(--color-accent)]' : 'bg-[var(--color-text-muted)]/30'}`}
                  style={{ height: `${pct}%`, minHeight: 2 }}
                  title={`\u03BB${e.index}: ${e.value.toFixed(4)}${e.block_attribution ? ` (${e.block_attribution})` : ''}`}
                />
                <div className="text-[8px] text-[var(--color-text-muted)] mt-1 font-mono">{e.index}</div>
              </div>
            );
          })}
        </div>
        {/* Tau line label */}
        <div className="mt-1 text-[10px] text-[var(--color-text-muted)]">
          {'\u03C4'} threshold = {tau} (dashed) | Colored bars contribute to cod_{'\u03C0'}(G)
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Import Predicates Modal
// ---------------------------------------------------------------------------

function ImportPredicatesModal({
  workspaceId,
  onClose,
  onSuccess,
}: {
  workspaceId: string;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [jsonText, setJsonText] = useState('');
  const [mode, setMode] = useState<'replace' | 'augment'>('replace');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<number | null>(null);

  const handleParse = () => {
    setError(null);
    try {
      const parsed = JSON.parse(jsonText);
      const arr = Array.isArray(parsed) ? parsed : parsed.predicates ?? [parsed];
      setPreview(arr.length);
    } catch {
      setError('Invalid JSON. Paste an array of predicates.');
      setPreview(null);
    }
  };

  const handleSubmit = async () => {
    setLoading(true);
    setError(null);
    try {
      const parsed = JSON.parse(jsonText);
      const arr = Array.isArray(parsed) ? parsed : parsed.predicates ?? [parsed];
      const result = await postJson<PipelineResult>(
        `/api/im/pipeline/${workspaceId}/load-predicates`,
        { predicates: arr, mode, auto_blocks: true },
      );
      if (result.error) {
        setError(result.error);
      } else {
        onSuccess();
        onClose();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load predicates');
    }
    setLoading(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-[var(--color-bg-card)] rounded-xl border border-[var(--color-border)] p-6 w-[640px] max-h-[80vh] overflow-auto shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Import User-Authored Predicates</h2>
          <button onClick={onClose} className="text-[var(--color-text-muted)] hover:text-[var(--color-text)]">×</button>
        </div>

        <p className="text-xs text-[var(--color-text-muted)] mb-3">
          Paste a JSON array of predicates. Supports both user schema (predicate_id, failure_condition_text,
          tolerance_epsilon) and internal format (id, name, epsilon_g).
        </p>

        <textarea
          value={jsonText}
          onChange={(e) => { setJsonText(e.target.value); setPreview(null); }}
          placeholder={'[\n  {\n    "predicate_id": "f_001",\n    "failure_condition_text": "...",\n    "tolerance_epsilon": 0.05,\n    "horizon_t": 3600,\n    "severity": "high",\n    "coupling_block": "BLK_A"\n  }\n]'}
          className="w-full h-48 bg-[var(--color-bg)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-xs font-mono text-[var(--color-text)] placeholder:text-[var(--color-text-muted)]/50 focus:outline-none focus:border-[var(--color-accent)] resize-y"
        />

        <div className="flex items-center gap-3 mt-3">
          <label className="text-xs text-[var(--color-text-muted)]">Mode:</label>
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as 'replace' | 'augment')}
            className="text-xs bg-[var(--color-bg)] border border-[var(--color-border)] rounded px-2 py-1 text-[var(--color-text)]"
          >
            <option value="replace">Replace (overwrite LLM predicates)</option>
            <option value="augment">Augment (merge with existing)</option>
          </select>
          <button
            onClick={handleParse}
            disabled={!jsonText.trim()}
            className="px-3 py-1 text-xs rounded bg-[var(--color-bg-hover)] text-[var(--color-text)] hover:bg-[var(--color-accent)] hover:text-white disabled:opacity-40 transition-colors"
          >
            Validate
          </button>
        </div>

        {preview != null && (
          <div className="mt-2 text-xs text-green-400">
            Parsed {preview} predicate(s) successfully
          </div>
        )}

        {error && (
          <div className="mt-2 text-xs text-red-400">{error}</div>
        )}

        <div className="flex justify-end gap-2 mt-4">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded-lg bg-[var(--color-bg-hover)] text-[var(--color-text)] hover:opacity-80 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading || !jsonText.trim() || preview === null}
            className="px-4 py-2 text-sm rounded-lg bg-[var(--color-accent)] text-white hover:opacity-90 disabled:opacity-40 transition-colors"
          >
            {loading ? 'Loading...' : `Import ${preview ?? 0} Predicates`}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Audit Trail
// ---------------------------------------------------------------------------

function AuditTrail({ trail }: { trail: AuditEntry[] }) {
  if (!trail.length) return null;
  return (
    <div className="bg-[var(--color-bg-card)] rounded-lg border border-[var(--color-border)] overflow-hidden">
      <div className="p-3 border-b border-[var(--color-border)]">
        <h3 className="text-sm font-semibold">Audit Trail ({trail.length} events)</h3>
      </div>
      <div className="overflow-auto max-h-[300px]">
        <table className="w-full text-xs">
          <thead className="bg-[var(--color-bg-hover)] sticky top-0">
            <tr>
              <th className="px-3 py-2 text-left font-medium text-[var(--color-text-muted)]">Stage</th>
              <th className="px-3 py-2 text-left font-medium text-[var(--color-text-muted)]">Tool</th>
              <th className="px-3 py-2 text-left font-medium text-[var(--color-text-muted)]">Input</th>
              <th className="px-3 py-2 text-left font-medium text-[var(--color-text-muted)]">Output</th>
              <th className="px-3 py-2 text-left font-medium text-[var(--color-text-muted)]">Time</th>
            </tr>
          </thead>
          <tbody>
            {trail.map((e, i) => (
              <tr key={i} className="border-t border-[var(--color-border)] hover:bg-[var(--color-bg-hover)]">
                <td className="px-3 py-1.5 font-mono text-[var(--color-accent)]">{e.stage}</td>
                <td className="px-3 py-1.5">{e.tool_name}</td>
                <td className="px-3 py-1.5 text-[var(--color-text-muted)] max-w-[200px] truncate">{e.input_summary}</td>
                <td className="px-3 py-1.5 text-[var(--color-text-muted)] max-w-[200px] truncate">{e.output_summary}</td>
                <td className="px-3 py-1.5 text-[var(--color-text-muted)]">
                  {e.created_at ? new Date(e.created_at).toLocaleTimeString() : ''}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function IMDesignerPage() {
  const [workspaces, setWorkspaces] = useState<IMWorkspaceSummary[]>([]);
  const [selected, setSelected] = useState<IMWorkspaceDetail | null>(null);
  const [fullData, setFullData] = useState<IMWorkspaceFull | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newIntent, setNewIntent] = useState('');
  const [running, setRunning] = useState(false);
  const [pipelineLog, setPipelineLog] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<DetailTab>('overview');
  const [showImport, setShowImport] = useState(false);

  const loadWorkspaces = useCallback(async () => {
    try {
      const data = await fetchJson<{ workspaces: IMWorkspaceSummary[] }>('/api/im/workspaces');
      setWorkspaces(data.workspaces ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load workspaces');
    }
    setLoading(false);
  }, []);

  const loadDetail = useCallback(async (id: string) => {
    try {
      const [summary, full] = await Promise.all([
        fetchJson<IMWorkspaceDetail>(`/api/im/workspaces/${id}`),
        fetchJson<IMWorkspaceFull>(`/api/im/workspaces/${id}/full`),
      ]);
      setSelected(summary);
      setFullData(full);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load workspace');
    }
  }, []);

  useEffect(() => {
    loadWorkspaces();
    const interval = setInterval(loadWorkspaces, 15000);
    return () => clearInterval(interval);
  }, [loadWorkspaces]);

  const handleRunPipeline = async () => {
    if (!newIntent.trim()) return;
    setRunning(true);
    setError(null);
    setPipelineLog(['Starting full pipeline...']);

    try {
      const result = await postJson<PipelineResult>('/api/im/pipeline/full', {
        raw_intent: newIntent.trim(),
      });

      if (result.error) {
        setError(result.error);
        setPipelineLog((prev) => [...prev, `Error: ${result.error}`]);
      } else {
        setPipelineLog((prev) => [
          ...prev,
          `Pipeline complete: ${result.verdict ?? 'unknown'}`,
          `Workspace: ${result.workspace_id}`,
        ]);
        setNewIntent('');
        await loadWorkspaces();
        if (result.workspace_id) {
          await loadDetail(result.workspace_id);
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Pipeline failed');
      setPipelineLog((prev) => [...prev, `Failed: ${e}`]);
    }
    setRunning(false);
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteJson(`/api/im/workspaces/${id}`);
      if (selected?.workspace_id === id) { setSelected(null); setFullData(null); }
      await loadWorkspaces();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Delete failed');
    }
  };

  const handleStepRun = async (step: string) => {
    if (!selected) return;
    setRunning(true);
    setError(null);
    try {
      const url = `/api/im/pipeline/${selected.workspace_id}/${step}`;
      const result = await postJson<PipelineResult>(url, {});
      if (result.error) {
        setError(result.error);
      } else {
        await loadDetail(selected.workspace_id);
        await loadWorkspaces();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Step failed');
    }
    setRunning(false);
  };

  const handleContinuePipeline = async () => {
    if (!selected) return;
    setRunning(true);
    setError(null);
    setPipelineLog((prev) => [...prev, 'Continuing pipeline from predicates (steps 3-9)...']);
    const steps = ['coupling', 'codimension', 'rank-budget', 'memory', 'agents', 'workflow', 'feasibility'];
    try {
      for (const step of steps) {
        setPipelineLog((prev) => [...prev, `Running ${step}...`]);
        const url = `/api/im/pipeline/${selected.workspace_id}/${step}`;
        const result = await postJson<PipelineResult>(url, step === 'coupling' ? { lock: true } : {});
        if (result.error) {
          setError(result.error);
          setPipelineLog((prev) => [...prev, `Error at ${step}: ${result.error}`]);
          break;
        }
      }
      await loadDetail(selected.workspace_id);
      await loadWorkspaces();
      setPipelineLog((prev) => [...prev, 'Pipeline continuation complete!']);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Pipeline failed');
    }
    setRunning(false);
  };

  const handleInstantiate = async () => {
    if (!selected) return;
    setRunning(true);
    setError(null);
    setPipelineLog((prev) => [...prev, 'Instantiating: spawning agents + deploying workflow...']);
    try {
      const url = `/api/im/pipeline/${selected.workspace_id}/instantiate`;
      const result = await postJson<PipelineResult>(url, {});
      if (result.error) {
        setError(result.error);
        setPipelineLog((prev) => [...prev, `Error: ${result.error}`]);
      } else {
        setPipelineLog((prev) => [
          ...prev,
          `Deployed! Workflow: ${(result as Record<string, unknown>).workflow_id ?? '?'}`,
          `Agents spawned: ${(result as Record<string, unknown>).agents_spawned ?? 0}`,
          `Run ID: ${(result as Record<string, unknown>).run_id ?? 'none'}`,
        ]);
        await loadDetail(selected.workspace_id);
        await loadWorkspaces();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Instantiation failed');
      setPipelineLog((prev) => [...prev, `Failed: ${e}`]);
    }
    setRunning(false);
  };

  const handleImportSuccess = async () => {
    if (selected) {
      await loadDetail(selected.workspace_id);
      await loadWorkspaces();
      setActiveTab('predicates');
    }
  };

  const tabs: { key: DetailTab; label: string }[] = [
    { key: 'overview', label: 'Overview' },
    { key: 'predicates', label: `Predicates${fullData?.predicates?.length ? ` (${fullData.predicates.length})` : ''}` },
    { key: 'coupling', label: 'Coupling' },
    { key: 'audit', label: 'Audit' },
  ];

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      <Header
        title="IM Designer"
        subtitle="Architecture Selection Rule — Informational Monism Pipeline"
        right={
          <button
            onClick={loadWorkspaces}
            className="text-xs text-[var(--color-accent)] hover:underline"
          >
            Refresh
          </button>
        }
      />

      <div className="flex-1 overflow-auto p-4">
        {error && (
          <div className="bg-red-900/30 border border-red-700/50 text-red-300 rounded-lg px-4 py-2 text-sm mb-4">
            {error}
            <button
              onClick={() => setError(null)}
              className="ml-2 text-red-400 hover:text-red-300"
            >
              ×
            </button>
          </div>
        )}

        {/* New workspace input */}
        <div className="bg-[var(--color-bg-card)] rounded-lg border border-[var(--color-border)] p-4 mb-4">
          <h3 className="text-sm font-semibold mb-2">New Architecture Design</h3>
          <div className="flex gap-2">
            <input
              type="text"
              value={newIntent}
              onChange={(e) => setNewIntent(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !running && handleRunPipeline()}
              placeholder="Describe your system goal in natural language..."
              className="flex-1 bg-[var(--color-bg)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-accent)]"
              disabled={running}
            />
            <button
              onClick={handleRunPipeline}
              disabled={running || !newIntent.trim()}
              className="px-4 py-2 text-sm rounded-lg bg-[var(--color-accent)] text-white hover:opacity-90 disabled:opacity-40 transition-colors whitespace-nowrap"
            >
              {running ? 'Running...' : 'Run Pipeline'}
            </button>
          </div>
          {pipelineLog.length > 0 && (
            <div className="mt-2 text-xs font-mono text-[var(--color-text-muted)] space-y-0.5 max-h-[100px] overflow-auto">
              {pipelineLog.map((l, i) => (
                <div key={i}>{l}</div>
              ))}
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Left: workspace list */}
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-[var(--color-text-muted)] mb-2">
              Workspaces ({workspaces.length})
            </h3>
            {loading ? (
              <div className="text-sm text-[var(--color-text-muted)]">Loading...</div>
            ) : workspaces.length === 0 ? (
              <div className="text-sm text-[var(--color-text-muted)]">
                No workspaces yet. Enter a goal above to start.
              </div>
            ) : (
              workspaces.map((ws) => (
                <WorkspaceCard
                  key={ws.workspace_id}
                  ws={ws}
                  selected={selected?.workspace_id === ws.workspace_id}
                  onSelect={() => loadDetail(ws.workspace_id)}
                  onDelete={() => handleDelete(ws.workspace_id)}
                />
              ))
            )}
          </div>

          {/* Right: detail view */}
          <div className="lg:col-span-2 space-y-4">
            {!selected ? (
              <div className="bg-[var(--color-bg-card)] rounded-lg border border-[var(--color-border)] p-8 text-center text-sm text-[var(--color-text-muted)]">
                Select a workspace to view details, or run a new pipeline above.
              </div>
            ) : (
              <>
                {/* Header stats */}
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                  <StatBox label="Codimension" value={selected.codimension} color="text-[var(--color-accent)]" />
                  <StatBox
                    label="Regime"
                    value={selected.regime?.toUpperCase() ?? null}
                    color={selected.regime ? 'text-yellow-400' : undefined}
                  />
                  <StatBox
                    label="Verdict"
                    value={selected.verdict?.toUpperCase() ?? null}
                    color={selected.verdict === 'feasible' ? 'text-green-400' : selected.verdict === 'infeasible' ? 'text-red-400' : undefined}
                  />
                  <StatBox label="Predicates" value={selected.predicate_count} />
                  <StatBox label="Blocks" value={selected.block_count} />
                </div>

                {/* Pipeline progress */}
                <div className="bg-[var(--color-bg-card)] rounded-lg border border-[var(--color-border)] p-3">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-sm font-semibold">Pipeline Progress</h3>
                    <span className="text-xs text-[var(--color-text-muted)] font-mono">
                      Stage: {selected.stage}
                    </span>
                  </div>
                  <PipelineProgress stage={selected.stage} />

                  {/* Step-by-step buttons */}
                  <div className="mt-3 flex flex-wrap gap-1">
                    {[
                      { step: 'predicates', label: 'Predicates', requires: 'goal_parsed' },
                      { step: 'coupling', label: 'Coupling', requires: 'predicates_generated' },
                      { step: 'codimension', label: 'Codimension', requires: 'coupling_built' },
                      { step: 'rank-budget', label: 'Rank Budget', requires: 'codimension_estimated' },
                      { step: 'memory', label: 'Memory', requires: 'rank_budgeted' },
                      { step: 'agents', label: 'Agents', requires: 'memory_designed' },
                      { step: 'workflow', label: 'Workflow', requires: 'agents_synthesized' },
                      { step: 'feasibility', label: 'Feasibility', requires: 'workflow_synthesized' },
                    ].map(({ step, label, requires }) => {
                      const current = STAGE_INDEX[selected.stage] ?? 0;
                      const needed = STAGE_INDEX[requires] ?? 0;
                      const enabled = current >= needed;
                      return (
                        <button
                          key={step}
                          onClick={() => handleStepRun(step)}
                          disabled={!enabled || running}
                          className={`px-2 py-1 text-[10px] rounded font-mono transition-colors ${
                            enabled
                              ? 'bg-[var(--color-bg-hover)] text-[var(--color-text)] hover:bg-[var(--color-accent)] hover:text-white'
                              : 'bg-[var(--color-bg)] text-[var(--color-text-muted)] opacity-40 cursor-not-allowed'
                          }`}
                        >
                          {label}
                        </button>
                      );
                    })}
                    {/* Import + Continue buttons */}
                    <button
                      onClick={() => setShowImport(true)}
                      disabled={running || (STAGE_INDEX[selected.stage] ?? 0) < 1}
                      className="px-2 py-1 text-[10px] rounded font-mono bg-purple-900/40 text-purple-300 hover:bg-purple-800/60 disabled:opacity-40 transition-colors"
                      title="Import user-authored predicates (replaces LLM-generated)"
                    >
                      Import Preds
                    </button>
                    {selected.stage === 'predicates_generated' && (
                      <button
                        onClick={handleContinuePipeline}
                        disabled={running}
                        className="px-2 py-1 text-[10px] rounded font-mono bg-[var(--color-accent)] text-white hover:opacity-90 disabled:opacity-40 transition-colors"
                        title="Run steps 3-9 from current predicates"
                      >
                        Continue Pipeline
                      </button>
                    )}
                  </div>
                </div>

                {/* Tab bar */}
                <div className="flex gap-1 bg-[var(--color-bg-card)] rounded-lg border border-[var(--color-border)] p-1">
                  {tabs.map((t) => (
                    <button
                      key={t.key}
                      onClick={() => setActiveTab(t.key)}
                      className={`flex-1 px-3 py-1.5 text-xs rounded font-medium transition-colors ${
                        activeTab === t.key
                          ? 'bg-[var(--color-accent)] text-white'
                          : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-bg-hover)]'
                      }`}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>

                {/* Tab content */}
                {activeTab === 'overview' && (
                  <>
                    {/* Goal tuple */}
                    {selected.goal_tuple && Object.keys(selected.goal_tuple).length > 0 && (
                      <div className="bg-[var(--color-bg-card)] rounded-lg border border-[var(--color-border)] p-3">
                        <h3 className="text-sm font-semibold mb-2">Goal Tuple</h3>
                        <pre className="text-xs font-mono text-[var(--color-text-muted)] overflow-auto max-h-[200px] whitespace-pre-wrap">
                          {JSON.stringify(selected.goal_tuple, null, 2)}
                        </pre>
                      </div>
                    )}

                    {/* Regime + verdict badges */}
                    <div className="flex flex-wrap gap-2">
                      {selected.regime && (
                        <span className={`px-3 py-1 rounded text-xs font-mono ${
                          selected.regime === 'simple' ? 'bg-green-900/40 text-green-400' :
                          selected.regime === 'medium' ? 'bg-yellow-900/40 text-yellow-400' :
                          'bg-red-900/40 text-red-400'
                        }`}>
                          Regime: {selected.regime.toUpperCase()}
                        </span>
                      )}
                      {selected.verdict && (
                        <span className={`px-3 py-1 rounded text-xs font-mono ${VERDICT_COLORS[selected.verdict] ?? ''}`}>
                          Verdict: {selected.verdict.toUpperCase()}
                        </span>
                      )}
                      {selected.coupling_locked && (
                        <span className="px-3 py-1 rounded text-xs font-mono bg-blue-900/40 text-blue-400">
                          Coupling Locked
                        </span>
                      )}
                      <span className="px-3 py-1 rounded text-xs font-mono bg-[var(--color-bg-hover)] text-[var(--color-text-muted)]">
                        {selected.predicate_count} predicates / {selected.block_count} blocks
                      </span>
                    </div>

                    {/* Feasibility conditions detail */}
                    {selected.feasibility && selected.verdict === 'feasible' && (
                      <div className="bg-green-950/30 rounded-lg border border-green-900/50 p-4 space-y-2">
                        <h3 className="text-sm font-semibold text-green-400">All Feasibility Checks Passed</h3>
                        <div className="grid grid-cols-3 gap-2 text-xs">
                          <div className="p-2 rounded bg-green-900/30 text-green-400">{'\u2713'} Rank Coverage</div>
                          <div className="p-2 rounded bg-green-900/30 text-green-400">{'\u2713'} Coupling Coverage</div>
                          <div className="p-2 rounded bg-green-900/30 text-green-400">{'\u2713'} Power Coverage</div>
                        </div>
                        {selected.feasibility.governance_margin != null && (
                          <p className="text-xs text-[var(--color-text-muted)]">
                            Governance margin: {'\u03B3'} = {selected.feasibility.governance_margin}
                          </p>
                        )}
                      </div>
                    )}
                    {selected.feasibility && selected.verdict === 'infeasible' && (
                      <div className="bg-red-950/30 rounded-lg border border-red-900/50 p-4 space-y-2">
                        <h3 className="text-sm font-semibold text-red-400">Feasibility Check Failed</h3>
                        <div className="grid grid-cols-3 gap-2 text-xs">
                          <div className={`p-2 rounded ${selected.feasibility.rank_coverage ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'}`}>
                            {selected.feasibility.rank_coverage ? '\u2713' : '\u2717'} Rank Coverage
                          </div>
                          <div className={`p-2 rounded ${selected.feasibility.coupling_coverage ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'}`}>
                            {selected.feasibility.coupling_coverage ? '\u2713' : '\u2717'} Coupling Coverage
                          </div>
                          <div className={`p-2 rounded ${selected.feasibility.power_coverage ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'}`}>
                            {selected.feasibility.power_coverage ? '\u2713' : '\u2717'} Power Coverage
                          </div>
                        </div>
                        {selected.feasibility.remediation && (
                          <p className="text-xs text-[var(--color-text-muted)] mt-1">
                            <span className="text-yellow-400">Remediation:</span> {selected.feasibility.remediation.detail}
                          </p>
                        )}
                        {selected.feasibility.axes_violating_power?.length > 0 && (
                          <p className="text-xs text-red-300">
                            Violating axes: {selected.feasibility.axes_violating_power.join(', ')}
                          </p>
                        )}
                      </div>
                    )}

                    {/* Eigenspectrum chart */}
                    {fullData?.codimension?.eigenspectrum && (
                      <EigenspectrumChart
                        eigenspectrum={fullData.codimension.eigenspectrum}
                        tau={fullData.codimension.tau ?? 0.05}
                      />
                    )}

                    {/* Deploy section */}
                    <div className="bg-[var(--color-bg-card)] rounded-lg border border-[var(--color-border)] p-4">
                      <div className="flex items-center justify-between mb-3">
                        <h3 className="text-sm font-semibold">Deployment</h3>
                        {selected.stage === 'deployed' && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-green-900/40 text-green-400">
                            LIVE
                          </span>
                        )}
                        {selected.stage === 'agents_spawned' && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-yellow-900/40 text-yellow-400">
                            AGENTS READY
                          </span>
                        )}
                      </div>

                      {selected.verdict !== 'feasible' ? (
                        <p className="text-xs text-[var(--color-text-muted)]">
                          Architecture must be marked <span className="text-green-400">feasible</span> before deployment.
                        </p>
                      ) : selected.stage === 'deployed' ? (
                        <div className="space-y-2">
                          <p className="text-xs text-green-400">
                            Workflow deployed and running.
                          </p>
                          {selected.workflow_id && (
                            <div className="text-xs text-[var(--color-text-muted)] font-mono">
                              Workflow: {selected.workflow_id}
                            </div>
                          )}
                          {selected.spawned_agents?.length > 0 && (
                            <div className="text-xs text-[var(--color-text-muted)]">
                              {selected.spawned_agents.length} agent(s): {selected.spawned_agents.join(', ')}
                            </div>
                          )}
                          {selected.initial_run_id && (
                            <div className="text-xs text-[var(--color-text-muted)] font-mono">
                              Run: {selected.initial_run_id}
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="space-y-3">
                          <p className="text-xs text-[var(--color-text-muted)]">
                            This architecture is feasible. Deploy to spawn {selected.predicate_count > 0 ? 'agents and ' : ''}register the workflow.
                          </p>
                          <div className="flex gap-2">
                            <button
                              onClick={handleInstantiate}
                              disabled={running}
                              className="flex-1 px-4 py-2 text-sm rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-40 transition-colors font-medium"
                            >
                              {running ? 'Deploying...' : 'Deploy to Production'}
                            </button>
                            <button
                              onClick={() => handleStepRun('spawn')}
                              disabled={running || selected.stage === 'agents_spawned'}
                              className="px-3 py-2 text-xs rounded-lg bg-[var(--color-bg-hover)] text-[var(--color-text)] hover:bg-[var(--color-accent)] hover:text-white disabled:opacity-40 transition-colors font-mono"
                              title="Spawn agents only (step 10)"
                            >
                              Spawn
                            </button>
                            <button
                              onClick={() => handleStepRun('deploy')}
                              disabled={running || !['agents_spawned', 'feasibility_validated'].includes(selected.stage)}
                              className="px-3 py-2 text-xs rounded-lg bg-[var(--color-bg-hover)] text-[var(--color-text)] hover:bg-[var(--color-accent)] hover:text-white disabled:opacity-40 transition-colors font-mono"
                              title="Deploy workflow only (step 11)"
                            >
                              Deploy WF
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  </>
                )}

                {activeTab === 'predicates' && fullData && (
                  <>
                    <PredicateTable
                      predicates={fullData.predicates ?? []}
                      blocks={fullData.predicate_blocks ?? []}
                    />
                    {/* Block summary */}
                    {fullData.predicate_blocks?.length > 0 && (
                      <div className="bg-[var(--color-bg-card)] rounded-lg border border-[var(--color-border)] p-3">
                        <h3 className="text-sm font-semibold mb-2">Predicate Blocks ({fullData.predicate_blocks.length})</h3>
                        <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                          {fullData.predicate_blocks.map((b) => (
                            <div key={b.id} className="bg-[var(--color-bg-hover)] rounded p-2 text-xs">
                              <div className="font-mono text-[var(--color-accent)]">{b.id}</div>
                              <div className="text-[var(--color-text-muted)] mt-0.5">{b.name}</div>
                              <div className="text-[var(--color-text-muted)] mt-0.5">{b.predicate_ids.length} predicates, rank={b.intra_rank}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {/* Agent assignment (if available) */}
                    {fullData.assignment?.agents && fullData.assignment.agents.length > 0 && (
                      <div className="bg-[var(--color-bg-card)] rounded-lg border border-[var(--color-border)] p-3">
                        <h3 className="text-sm font-semibold mb-2">Agent Assignment</h3>
                        <div className="space-y-2">
                          {fullData.assignment.agents.map((a) => (
                            <div key={a.agent_id} className="bg-[var(--color-bg-hover)] rounded p-2 text-xs">
                              <div className="flex items-center justify-between">
                                <span className="font-mono text-[var(--color-accent)]">{a.agent_id}</span>
                                <span className="text-[var(--color-text-muted)]">{a.model_family}</span>
                              </div>
                              <div className="text-[var(--color-text-muted)] mt-0.5">{a.name}</div>
                              <div className="flex flex-wrap gap-1 mt-1">
                                {a.assigned_predicates.map((pid) => (
                                  <span key={pid} className="px-1 py-0.5 rounded bg-[var(--color-bg)] text-[10px] font-mono">{pid}</span>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                )}

                {activeTab === 'coupling' && fullData && (
                  <>
                    {fullData.coupling_matrix?.M ? (
                      <CouplingHeatmap
                        matrix={fullData.coupling_matrix.M}
                        predicates={fullData.predicates ?? []}
                      />
                    ) : (
                      <div className="bg-[var(--color-bg-card)] rounded-lg border border-[var(--color-border)] p-8 text-center text-sm text-[var(--color-text-muted)]">
                        No coupling matrix computed yet. Run the coupling step first.
                      </div>
                    )}
                    {/* Cross-block coupling */}
                    {fullData.cross_block_coupling?.length > 0 && (
                      <div className="bg-[var(--color-bg-card)] rounded-lg border border-[var(--color-border)] overflow-hidden">
                        <div className="p-3 border-b border-[var(--color-border)]">
                          <h3 className="text-sm font-semibold">Cross-Block Coupling ({fullData.cross_block_coupling.length} axes)</h3>
                        </div>
                        <div className="overflow-auto max-h-[200px]">
                          <table className="w-full text-xs">
                            <thead className="bg-[var(--color-bg-hover)] sticky top-0">
                              <tr>
                                <th className="px-3 py-2 text-left font-medium text-[var(--color-text-muted)]">From</th>
                                <th className="px-3 py-2 text-left font-medium text-[var(--color-text-muted)]">To</th>
                                <th className="px-3 py-2 text-left font-medium text-[var(--color-text-muted)]">{'\u03C1'}</th>
                                <th className="px-3 py-2 text-left font-medium text-[var(--color-text-muted)]">Mechanism</th>
                              </tr>
                            </thead>
                            <tbody>
                              {fullData.cross_block_coupling.map((c, i) => (
                                <tr key={i} className="border-t border-[var(--color-border)]">
                                  <td className="px-3 py-1.5 font-mono">{c.from_block}</td>
                                  <td className="px-3 py-1.5 font-mono">{c.to_block}</td>
                                  <td className="px-3 py-1.5 font-mono">{c.rho}</td>
                                  <td className="px-3 py-1.5 text-[var(--color-text-muted)]">{c.mechanism}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                  </>
                )}

                {activeTab === 'audit' && (
                  <AuditTrail trail={selected.audit_trail ?? []} />
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {/* Import modal */}
      {showImport && selected && (
        <ImportPredicatesModal
          workspaceId={selected.workspace_id}
          onClose={() => setShowImport(false)}
          onSuccess={handleImportSuccess}
        />
      )}
    </div>
  );
}
