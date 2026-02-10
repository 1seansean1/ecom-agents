/**
 * SystemStatus — collapsible status bar for Holly Grace page.
 * Shows run counts, ticket counts, system health.
 */

import { useCallback, useEffect, useState } from 'react';
import { ChevronDown, ChevronUp, Activity, AlertTriangle, CheckCircle } from 'lucide-react';
import { fetchJson } from '@/lib/api';

interface HealthData {
  overall: string;
  active_runs: number;
  queued_runs: number;
  waiting_approval: number;
  pending_tickets: number;
  redis: string;
  postgres: string;
  [key: string]: unknown;
}

export default function SystemStatus() {
  const [expanded, setExpanded] = useState(false);
  const [health, setHealth] = useState<HealthData | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchJson<HealthData>('/api/holly/system-health');
      setHealth(data);
    } catch {
      // Fall back to direct health query
      try {
        const data = await fetchJson<{ checks: HealthData }>('/api/health');
        setHealth(data.checks as HealthData);
      } catch {
        // ignore
      }
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 15000);
    return () => clearInterval(timer);
  }, [refresh]);

  const overallIcon = health?.overall === 'healthy'
    ? <CheckCircle size={14} className="text-green-400" />
    : health?.overall === 'degraded'
    ? <AlertTriangle size={14} className="text-yellow-400" />
    : <Activity size={14} className="text-[var(--color-text-muted)]" />;

  const summaryParts: string[] = [];
  if (health) {
    if (health.active_runs) summaryParts.push(`${health.active_runs} running`);
    if (health.waiting_approval) summaryParts.push(`${health.waiting_approval} waiting`);
    if (health.pending_tickets) summaryParts.push(`${health.pending_tickets} tickets`);
    if (!summaryParts.length) summaryParts.push('All clear');
  }

  return (
    <div className="border-b border-[var(--color-border)] bg-[var(--color-bg-card)]">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-2 text-xs hover:bg-[var(--color-bg-hover)] transition-colors"
      >
        <div className="flex items-center gap-2">
          {overallIcon}
          <span className="text-[var(--color-text-muted)]">
            {summaryParts.join(' · ') || 'Loading...'}
          </span>
        </div>
        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {expanded && health && (
        <div className="px-4 pb-3 grid grid-cols-2 gap-2 text-xs">
          <StatusItem label="Active runs" value={health.active_runs ?? 0} />
          <StatusItem label="Queued" value={health.queued_runs ?? 0} />
          <StatusItem label="Waiting approval" value={health.waiting_approval ?? 0} />
          <StatusItem label="Pending tickets" value={health.pending_tickets ?? 0} />
          <ServiceItem label="Redis" status={health.redis} />
          <ServiceItem label="Postgres" status={health.postgres} />
        </div>
      )}
    </div>
  );
}

function StatusItem({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex justify-between bg-[var(--color-bg)] rounded px-2 py-1.5">
      <span className="text-[var(--color-text-muted)]">{label}</span>
      <span className="text-[var(--color-text)] font-medium">{value}</span>
    </div>
  );
}

function ServiceItem({ label, status }: { label: string; status: string | undefined }) {
  const isHealthy = status === 'healthy';
  return (
    <div className="flex justify-between bg-[var(--color-bg)] rounded px-2 py-1.5">
      <span className="text-[var(--color-text-muted)]">{label}</span>
      <span className={isHealthy ? 'text-green-400' : 'text-red-400'}>
        {status ?? 'unknown'}
      </span>
    </div>
  );
}
