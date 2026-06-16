import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  ShieldAlert,
  ShieldCheck,
  Database,
  Clock,
  RefreshCw,
  ArrowUpRight,
  ExternalLink,
  AlertTriangle,
  TrendingUp,
  TrendingUp,
  CalendarClock,
} from 'lucide-react';
import api from '../config/api';
import { Skeleton, StatCardSkeleton } from '../components/Skeleton';
import { EmptyState } from '../components/EmptyState/EmptyState';
import ExportButton from '../components/ExportButton/ExportButton';

/* ============================================================================
   API fetch helpers
   ============================================================================ */

async function fetchToolsTotal(): Promise<number> {
  const res = await api.get('/api/v1/tools', { params: { page: 1, page_size: 1 } });
  return res.data?.total ?? 0;
}

async function fetchCriticalCves(): Promise<any[]> {
  const res = await api.get('/api/v1/cves', {
    params: { severity: 'Critical', page_size: 10 },
  });
  return res.data?.data ?? [];
}

async function fetchEolTools(): Promise<any[]> {
  const res = await api.get('/api/v1/governance/eol-status');
  return res.data?.data ?? [];
}

async function fetchCveStats(): Promise<any> {
  const res = await api.get('/api/v1/cves/stats/summary');
  return res.data?.data ?? {};
}

async function fetchAssetRiskOverview(): Promise<any[]> {
  const res = await api.get('/api/v1/assets/risk-overview');
  return res.data?.data ?? [];
}

/* ============================================================================
   Reusable components
   ============================================================================ */

/* ─── Reusable components ─────────────────────────────────────────────────── */

/* ─── Reusable components ─────────────────────────────────────────────────── */

function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="divide-y divide-slate-50">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 px-5 py-3.5">
          <Skeleton className="h-4 w-28" />
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-4 w-16 ml-auto" />
        </div>
      ))}
    </div>
  );
}

/* ─── Error state ──────────────────────────────────────────────────────────── */
function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="w-12 h-12 rounded-full bg-red-50 flex items-center justify-center mb-3">
        <AlertTriangle size={24} className="text-red-500" />
      </div>
      <p className="text-sm text-slate-600 mb-3">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="
            inline-flex items-center gap-1.5 px-4 py-2 rounded-lg
            text-sm font-medium text-indigo-600 bg-indigo-50
            hover:bg-indigo-100 transition-colors
          "
        >
          <RefreshCw size={14} /> Retry
        </button>
      )}
    </div>
  );
}

/* ─── Severity badge ──────────────────────────────────────────────────────── */
function SeverityBadge({ severity }: { severity: string }) {
  return <span className={`badge badge-${severity.toLowerCase()}`}>{severity}</span>;
}

/* ============================================================================
   Stat card
   ============================================================================ */

interface StatCardProps {
  label: string;
  value: string | number;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  color: string;
  bg: string;
  subtitle?: string;
}

function StatCard({ label, value, icon: Icon, color, bg, subtitle }: StatCardProps) {
  return (
    <div className="card p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">
            {label}
          </p>
          <p className="text-2xl font-bold text-slate-900 mt-1">{value}</p>
        </div>
        <div
          className="w-10 h-10 rounded-lg flex items-center justify-center"
          style={{ background: bg }}
        >
          <Icon size={20} style={{ color }} />
        </div>
      </div>
      {subtitle && (
        <p className="flex items-center mt-3 text-xs text-slate-500">
          <TrendingUp size={12} className="mr-1" />
          {subtitle}
        </p>
      )}
    </div>
  );
}

/* ============================================================================
   EOL Timeline item
   ============================================================================ */

interface EolItemProps {
  tool_name: string;
  eol_date: string;
  latest_version?: string;
  lifecycle_status?: string;
}

function EolTimelineItem({ tool_name, eol_date }: EolItemProps) {
  const now = Date.now();
  const eol = new Date(eol_date).getTime();
  // Tính từ 180 ngày trước EOL tới EOL
  const windowStart = eol - 180 * 24 * 60 * 60 * 1000;
  const totalWindow = eol - windowStart;
  const elapsed = now - windowStart;
  const progressRaw = totalWindow > 0 ? (elapsed / totalWindow) * 100 : 100;
  const progress = Math.min(Math.max(progressRaw, 0), 100);

  const daysLeft = Math.max(0, Math.ceil((eol - now) / (24 * 60 * 60 * 1000)));
  const isOverdue = daysLeft === 0;

  const barColor = isOverdue
    ? '#ef4444'
    : daysLeft <= 30
      ? '#f59e0b'
      : daysLeft <= 90
        ? '#6366f1'
        : '#10b981';

  return (
    <div className="px-5 py-3.5 hover:bg-slate-50/50 transition-colors">
      <div className="flex items-center justify-between mb-1.5">
        <Link
          to={`/catalog/${tool_name}`}
          className="text-sm font-medium text-slate-900 hover:text-indigo-600 transition-colors"
        >
          {tool_name}
        </Link>
        <span className="text-xs text-slate-500 tabular-nums">
          {isOverdue ? (
            <span className="text-red-600 font-semibold">EOL reached</span>
          ) : (
            `${daysLeft}d left`
          )}
        </span>
      </div>
      <div className="flex items-center gap-2 text-xs text-slate-400 mb-2">
        {latest_version && <span className="font-mono">v{latest_version}</span>}
        <span>·</span>
        <span>EOL {new Date(eol_date).toLocaleDateString('en-CA')}</span>
      </div>
      {/* Progress bar */}
      <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${progress}%`, background: barColor }}
        />
      </div>
    </div>
  );
}

/* ============================================================================
   Dashboard page
   ============================================================================ */

const REFETCH_INTERVAL = 5 * 60 * 1000; // 5 phút

export default function Dashboard() {
  // ── Queries ─────────────────────────────────────────────────────────────
  const toolsQuery = useQuery({
    queryKey: ['dashboard', 'toolsTotal'],
    queryFn: fetchToolsTotal,
    refetchInterval: REFETCH_INTERVAL,
  });

  const cvesQuery = useQuery({
    queryKey: ['dashboard', 'criticalCves'],
    queryFn: fetchCriticalCves,
    refetchInterval: REFETCH_INTERVAL,
  });

  const eolQuery = useQuery({
    queryKey: ['dashboard', 'eolTools'],
    queryFn: fetchEolTools,
    refetchInterval: REFETCH_INTERVAL,
  });

  const statsQuery = useQuery({
    queryKey: ['dashboard', 'cveStats'],
    queryFn: fetchCveStats,
    refetchInterval: REFETCH_INTERVAL,
  });

  const assetsQuery = useQuery({
    queryKey: ['dashboard', 'assetRisk'],
    queryFn: fetchAssetRiskOverview,
    refetchInterval: REFETCH_INTERVAL,
  });

  // ── Derived data ────────────────────────────────────────────────────────
  const assetRiskData = assetsQuery.data ?? [];
  const totalTools = toolsQuery.data ?? 0;

  const criticalCves = cvesQuery.data ?? [];
  const criticalCount = criticalCves.length;

  // Tools approaching EOL trong 180 ngày
  const now = Date.now();
  const eolTools = (eolQuery.data ?? [])
    .filter((t: any) => {
      if (!t.eol_date) return false;
      const eolTime = new Date(t.eol_date).getTime();
      const daysUntilEol = (eolTime - now) / (24 * 60 * 60 * 1000);
      return daysUntilEol <= 180; // within 180 days (past or future)
    })
    .sort((a: any, b: any) => {
      return new Date(a.eol_date).getTime() - new Date(b.eol_date).getTime();
    });

  const eolApproachingCount = eolTools.filter((t: any) => {
    const daysUntilEol = (new Date(t.eol_date).getTime() - now) / (24 * 60 * 60 * 1000);
    return daysUntilEol > 0 && daysUntilEol <= 90;
  }).length;

  // CVE severity breakdown
  const severityBreakdown: Record<string, number> = {};
  for (const item of statsQuery.data?.by_severity ?? []) {
    severityBreakdown[item.severity] = item.count;
  }

  return (
    <div className="space-y-6">
      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
          <p className="text-sm text-slate-500 mt-1">
            Real-time overview of your Data Stack risk posture
          </p>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-slate-400">
          <Clock size={12} />
          Auto-refresh every 5 min
        </div>
      </div>

      {/* ── 1. Stats Row ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {toolsQuery.isLoading ? (
          <>
            <StatCardSkeleton />
            <StatCardSkeleton />
            <StatCardSkeleton />
            <StatCardSkeleton />
          </>
        ) : (
          <>
            <StatCard
              label="Total Tools Tracked"
              value={totalTools}
              icon={Database}
              color="#6366f1"
              bg="#eef2ff"
              subtitle="Across all Data Stack"
            />
            <StatCard
              label="Critical CVEs"
              value={criticalCount}
              icon={ShieldAlert}
              color="#ef4444"
              bg="#fef2f2"
              subtitle="Active critical severity"
            />
            <StatCard
              label="Approaching EOL"
              value={eolApproachingCount}
              icon={CalendarClock}
              color="#f59e0b"
              bg="#fffbeb"
              subtitle="Within next 90 days"
            />
            <StatCard
              label="Compliance Score"
              value={
                totalTools > 0
                  ? `${Math.round(((totalTools - (severityBreakdown['Critical'] ?? 0)) / totalTools) * 100)}%`
                  : '—'
              }
              icon={ShieldCheck}
              color="#10b981"
              bg="#ecfdf5"
              subtitle="Tools without critical CVEs"
            />
          </>
        )}
      </div>

      {/* ── 2 & 3. Two-column layout ─────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* ── 2. Critical CVEs Panel (60%) ────────────────────────────────── */}
        <div className="lg:col-span-3 card">
          <div className="px-5 py-4 border-b border-slate-100">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                <ShieldAlert size={16} className="text-red-500" />
                Critical CVEs
              </h2>
              <div className="flex items-center gap-4">
                <ExportButton
                  data={criticalCves}
                  columns={{
                    cve_id: 'CVE ID',
                    tool_name: 'Tool',
                    affected_versions: 'Affected Versions',
                    cvss_score: 'CVSS Score',
                    severity: 'Severity',
                    published_at: 'Published Date',
                  }}
                  filename="critical_cves"
                  format="csv"
                  label="Export CVEs (CSV)"
                />
                <Link
                  to="/catalog"
                  className="text-xs text-indigo-600 hover:text-indigo-700 flex items-center gap-1 transition-colors"
                >
                  View all CVEs <ArrowUpRight size={12} />
                </Link>
              </div>
            </div>
          </div>

          {cvesQuery.isLoading ? (
            <TableSkeleton rows={5} />
          ) : cvesQuery.isError ? (
            <ErrorState
              message="Failed to load CVE data"
              onRetry={() => cvesQuery.refetch()}
            />
          ) : criticalCves.length === 0 ? (
            <EmptyState.NoCVEsFound />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100 bg-slate-50/50">
                    <th className="text-left py-2.5 px-5 font-medium text-slate-500 text-xs">
                      CVE ID
                    </th>
                    <th className="text-left py-2.5 px-5 font-medium text-slate-500 text-xs">
                      Tool
                    </th>
                    <th className="text-center py-2.5 px-5 font-medium text-slate-500 text-xs">
                      CVSS
                    </th>
                    <th className="text-center py-2.5 px-5 font-medium text-slate-500 text-xs">
                      Severity
                    </th>
                    <th className="text-right py-2.5 px-5 font-medium text-slate-500 text-xs">
                      Published
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {criticalCves.map((cve: any) => (
                    <tr
                      key={cve.cve_id}
                      className="hover:bg-slate-50/50 transition-colors"
                    >
                      <td className="py-3 px-5">
                        <a
                          href={`https://nvd.nist.gov/vuln/detail/${cve.cve_id}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-mono text-indigo-600 hover:text-indigo-700 inline-flex items-center gap-1"
                        >
                          {cve.cve_id}
                          <ExternalLink size={10} />
                        </a>
                      </td>
                      <td className="py-3 px-5">
                        <Link
                          to={`/catalog/${cve.tool_name}`}
                          className="text-slate-800 hover:text-indigo-600 font-medium transition-colors"
                        >
                          {cve.tool_name}
                        </Link>
                      </td>
                      <td className="py-3 px-5 text-center">
                        <span
                          className="
                            inline-flex items-center justify-center w-10 h-6 rounded
                            text-xs font-bold tabular-nums
                          "
                          style={{
                            background:
                              (cve.cvss_score ?? 0) >= 9
                                ? '#fef2f2'
                                : (cve.cvss_score ?? 0) >= 7
                                  ? '#fff7ed'
                                  : '#fefce8',
                            color:
                              (cve.cvss_score ?? 0) >= 9
                                ? '#dc2626'
                                : (cve.cvss_score ?? 0) >= 7
                                  ? '#ea580c'
                                  : '#ca8a04',
                          }}
                        >
                          {cve.cvss_score?.toFixed(1) ?? '—'}
                        </span>
                      </td>
                      <td className="py-3 px-5 text-center">
                        <SeverityBadge severity={cve.severity ?? 'Critical'} />
                      </td>
                      <td className="py-3 px-5 text-right text-xs text-slate-400 tabular-nums">
                        {cve.published_at
                          ? new Date(cve.published_at).toLocaleDateString('en-CA')
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ── 3. EOL Timeline (40%) ──────────────────────────────────────── */}
        <div className="lg:col-span-2 card">
          <div className="px-5 py-4 border-b border-slate-100">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                <CalendarClock size={16} className="text-amber-500" />
                EOL Timeline
              </h2>
              <span className="text-xs text-slate-400">Next 180 days</span>
            </div>
          </div>

          {eolQuery.isLoading ? (
            <TableSkeleton rows={5} />
          ) : eolQuery.isError ? (
            <ErrorState
              message="Failed to load EOL data"
              onRetry={() => eolQuery.refetch()}
            />
          ) : eolTools.length === 0 ? (
            <div className="py-12 text-center">
              <ShieldCheck size={36} className="mx-auto text-emerald-300" />
              <p className="text-sm text-slate-500 mt-3">
                No tools approaching EOL
              </p>
            </div>
          ) : (
            <div className="divide-y divide-slate-50">
              {eolTools.map((tool: any) => (
                <EolTimelineItem
                  key={tool.tool_name}
                  tool_name={tool.tool_name}
                  eol_date={tool.eol_date}
                  latest_version={tool.latest_version}
                  lifecycle_status={tool.lifecycle_status}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── 4. Asset Risk Overview ───────────────────────────────────────── */}
      <div className="card mt-6">
        <div className="px-5 py-4 border-b border-slate-100">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
              <Database size={16} className="text-indigo-500" />
              Asset Risk Overview
            </h2>
          </div>
        </div>

        {assetsQuery.isLoading ? (
          <TableSkeleton rows={5} />
        ) : assetsQuery.isError ? (
          <ErrorState message="Failed to load Asset Risk Overview" onRetry={() => assetsQuery.refetch()} />
        ) : assetRiskData.length === 0 ? (
          <div className="py-12 text-center">
            <ShieldCheck size={36} className="mx-auto text-emerald-300" />
            <p className="text-sm text-slate-500 mt-3">No assets configured in inventory.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/50">
                  <th className="text-left py-2.5 px-5 font-medium text-slate-500 text-xs">Department</th>
                  <th className="text-left py-2.5 px-5 font-medium text-slate-500 text-xs">Project</th>
                  <th className="text-left py-2.5 px-5 font-medium text-slate-500 text-xs">Team</th>
                  <th className="text-left py-2.5 px-5 font-medium text-slate-500 text-xs">Tool</th>
                  <th className="text-left py-2.5 px-5 font-medium text-slate-500 text-xs">Version In Use</th>
                  <th className="text-center py-2.5 px-5 font-medium text-slate-500 text-xs">CVE Critical/High</th>
                  <th className="text-center py-2.5 px-5 font-medium text-slate-500 text-xs">EOL Status</th>
                  <th className="text-center py-2.5 px-5 font-medium text-slate-500 text-xs">Risk Level</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {assetRiskData.map((asset: any, idx: number) => {
                  const critical = asset.critical_cves_count || 0;
                  const high = asset.high_cves_count || 0;
                  
                  let daysToEol = Infinity;
                  if (asset.eol_date) {
                    daysToEol = (new Date(asset.eol_date).getTime() - Date.now()) / (24 * 60 * 60 * 1000);
                  }
                  
                  let riskLevel = 'LOW';
                  let rowColor: string;
                  
                  if (critical >= 1 || daysToEol <= 0) {
                    riskLevel = 'HIGH';
                    rowColor = 'bg-red-50 hover:bg-red-100/50';
                  } else if (high >= 2 || daysToEol <= 90) {
                    riskLevel = 'MEDIUM';
                    rowColor = 'bg-amber-50 hover:bg-amber-100/50';
                  } else {
                    rowColor = 'bg-white hover:bg-slate-50/50';
                  }

                  return (
                    <tr key={idx} className={`${rowColor} transition-colors`}>
                      <td className="py-3 px-5 text-slate-600">{asset.department || '—'}</td>
                      <td className="py-3 px-5 font-medium text-slate-800">{asset.project_name}</td>
                      <td className="py-3 px-5 text-slate-600">{asset.team_name || '—'}</td>
                      <td className="py-3 px-5">
                        <Link to={`/catalog/${asset.tool_name}`} className="text-indigo-600 hover:text-indigo-700">
                          {asset.tool_name}
                        </Link>
                      </td>
                      <td className="py-3 px-5 font-mono text-xs">{asset.version_in_use}</td>
                      <td className="py-3 px-5 text-center">
                        {critical > 0 ? (
                          <span className="text-red-600 font-bold">{critical} C</span>
                        ) : (
                          <span className="text-slate-400">0 C</span>
                        )}
                        {' / '}
                        {high > 0 ? (
                          <span className="text-amber-600 font-bold">{high} H</span>
                        ) : (
                          <span className="text-slate-400">0 H</span>
                        )}
                      </td>
                      <td className="py-3 px-5 text-center text-xs">
                        {asset.eol_date ? (
                          daysToEol <= 0 ? (
                            <span className="text-red-600 font-semibold">EOL Reached</span>
                          ) : (
                            <span>{Math.ceil(daysToEol)} days left</span>
                          )
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                      <td className="py-3 px-5 text-center">
                        <span className={`badge ${riskLevel === 'HIGH' ? 'badge-critical' : riskLevel === 'MEDIUM' ? 'badge-high' : 'badge-low'}`}>
                          {riskLevel}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
