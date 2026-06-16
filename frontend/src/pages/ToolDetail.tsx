import React, { useState, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  ShieldAlert,
  Shield,
  GitBranch,
  AlertTriangle,
  Calendar,
  ExternalLink,
  RefreshCw,
  PackageCheck,
  FileText,
  Search,
  Check,
  X as XIcon,
  Settings,
  Layers,
} from 'lucide-react';
import api from '../config/api';
import { Skeleton, TableRowSkeleton } from '../components/Skeleton';
import { EmptyState } from '../components/EmptyState/EmptyState';
import ExportButton from '../components/ExportButton/ExportButton';
import { sortVersions } from '../utils/semver';

/* ============================================================================
   Types
   ============================================================================ */

interface ToolSummary {
  tool_name: string;
  latest_version: string | null;
  eol_date: string | null;
  eos_date: string | null;
  total_cve_critical: number;
  total_cve_high: number;
  last_updated: string | null;
  lifecycle_status: string;
  risk_level: string;
}

interface VersionRow {
  version: string;
  release_date: string | null;
  breaking_changes: string[] | string | null;
  breaking_changes_enriched?: any[] | string | null;
  deprecated_apis: string[] | string | null;
  has_breaking_changes: boolean;
  cve_count: number;
}

interface CveRow {
  cve_id: string;
  tool_name: string;
  affected_versions: string[] | string | null;
  fixed_in_version: string | null;
  cvss_score: number | null;
  severity: string;
  description: string | null;
  published_at: string | null;
}

type TabId = 'versions' | 'cves' | 'compatibility' | 'license';

const TABS: { id: TabId; label: string; icon: typeof GitBranch }[] = [
  { id: 'versions',      label: 'Versions',        icon: GitBranch     },
  { id: 'cves',           label: 'CVEs',            icon: Shield        },
  { id: 'compatibility',  label: 'Compatibility',   icon: PackageCheck  },
  { id: 'license',        label: 'License History', icon: FileText      },
];

const RISK_COLORS: Record<string, string> = {
  critical: '#ef4444', high: '#f59e0b', medium: '#6366f1', low: '#10b981',
};

const LIFECYCLE_BADGE: Record<string, { color: string; bg: string }> = {
  Active:      { color: '#059669', bg: '#ecfdf5' },
  Maintenance: { color: '#d97706', bg: '#fffbeb' },
  EOL:         { color: '#dc2626', bg: '#fef2f2' },
};

/* ============================================================================
   Utilities
   ============================================================================ */

function parseJsonField(value: any): any[] {
  if (!value) return [];
  if (Array.isArray(value)) return value;
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch { return []; }
  }
  return [];
}

/* ============================================================================
   Sub-components
   ============================================================================ */

function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="w-12 h-12 rounded-full bg-red-50 flex items-center justify-center mb-3">
        <AlertTriangle size={24} className="text-red-500" />
      </div>
      <p className="text-sm text-slate-600 mb-3">{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 transition-colors">
          <RefreshCw size={14} /> Retry
        </button>
      )}
    </div>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  return <span className={`badge badge-${severity.toLowerCase()}`}>{severity}</span>;
}

/* ============================================================================
   Main page
   ============================================================================ */

export default function ToolDetail() {
  const { toolName } = useParams<{ toolName: string }>();
  const [activeTab, setActiveTab] = useState<TabId>('versions');

  // ── Tool detail query ───────────────────────────────────────────────────
  const detailQuery = useQuery({
    queryKey: ['toolDetail', toolName],
    queryFn: async () => {
      const res = await api.get(`/api/v1/tools/${toolName}`);
      return res.data?.data;
    },
    enabled: !!toolName,
    staleTime: 5 * 60_000,
  });

  // ── Versions query ──────────────────────────────────────────────────────
  const versionsQuery = useQuery({
    queryKey: ['toolVersions', toolName],
    queryFn: async () => {
      const res = await api.get(`/api/v1/tools/${toolName}/versions`, {
        params: { page_size: 200 },
      });
      return res.data?.data ?? [];
    },
    enabled: !!toolName && activeTab === 'versions',
    staleTime: 5 * 60_000,
  });

  // ── CVEs for this tool ──────────────────────────────────────────────────
  const cvesQuery = useQuery({
    queryKey: ['toolCves', toolName],
    queryFn: async () => {
      const res = await api.get('/api/v1/cves', {
        params: { tool_name: toolName, page_size: 100 },
      });
      return res.data?.data ?? [];
    },
    enabled: !!toolName && activeTab === 'cves',
    staleTime: 5 * 60_000,
  });

  const summary: ToolSummary | null = detailQuery.data?.summary ?? null;
  const totalVersions: number = detailQuery.data?.total_versions ?? 0;

  const riskColor = RISK_COLORS[summary?.risk_level ?? 'low'];
  const lcBadge = LIFECYCLE_BADGE[summary?.lifecycle_status ?? 'Active'];

  // ── Loading / error ─────────────────────────────────────────────────────
  if (detailQuery.isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-4 w-40" />
        <div className="card p-6 space-y-4">
          <Skeleton className="h-8 w-60" />
          <div className="flex gap-3">
            <Skeleton className="h-5 w-20 rounded-full" />
            <Skeleton className="h-5 w-24 rounded-full" />
          </div>
        </div>
        <div className="grid grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="card p-4 space-y-2">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-7 w-12" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (detailQuery.isError || !summary) {
    return (
      <div>
        <Link to="/catalog" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-indigo-600 transition-colors mb-4">
          <ArrowLeft size={14} /> Back to Catalog
        </Link>
        <div className="card">
          <ErrorState
            message={`Failed to load details for "${toolName}"`}
            onRetry={() => detailQuery.refetch()}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ── Breadcrumb ──────────────────────────────────────────────────── */}
      <nav className="flex items-center gap-1.5 text-sm text-slate-400">
        <Link to="/" className="hover:text-indigo-600 transition-colors">Dashboard</Link>
        <ChevronRight size={14} />
        <Link to="/catalog" className="hover:text-indigo-600 transition-colors">Tech Catalog</Link>
        <ChevronRight size={14} />
        <span className="text-slate-700 font-medium">{summary.tool_name}</span>
      </nav>

      {/* ── Header stats ────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="card p-4">
          <div className="text-slate-500 text-xs font-medium uppercase tracking-wider mb-1">Status</div>
          <div className="font-semibold text-slate-900">
            <span
              className="inline-flex items-center px-2 py-0.5 rounded-full text-xs"
              style={{ background: lcBadge.bg, color: lcBadge.color }}
            >
              {summary.lifecycle_status}
            </span>
          </div>
        </div>

        <div className="card p-4">
          <div className="text-slate-500 text-xs font-medium uppercase tracking-wider mb-1">EOL Date</div>
          <div className="font-semibold text-slate-900 flex items-center gap-2">
            <Calendar size={14} className="text-slate-400" />
            {summary.eol_date ? new Date(summary.eol_date).toLocaleDateString('en-CA') : '—'}
          </div>
        </div>

        <div className="card p-4">
          <div className="text-slate-500 text-xs font-medium uppercase tracking-wider mb-1">Security Risk</div>
          <div className="font-semibold text-slate-900 flex items-center gap-2">
            <ShieldAlert size={14} style={{ color: RISK_COLORS[summary.risk_level.toLowerCase()] ?? '#94a3b8' }} />
            <span className="capitalize">{summary.risk_level}</span>
          </div>
        </div>

        <div className="card p-4">
          <div className="text-slate-500 text-xs font-medium uppercase tracking-wider mb-1">High/Crit CVEs</div>
          <div className="font-semibold text-slate-900 text-lg tabular-nums">
            {summary.total_cve_critical + summary.total_cve_high}
          </div>
        </div>
      </div>

      {/* ── Header card ─────────────────────────────────────────────────── */}
      <div className="card p-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">{summary.tool_name}</h1>
            <div className="flex flex-wrap items-center gap-2.5 mt-2">
              <span className="text-sm font-mono text-slate-600">
                v{summary.latest_version ?? '—'}
              </span>
              <span
                className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold"
                style={{ background: lcBadge.bg, color: lcBadge.color }}
              >
                {summary.lifecycle_status}
              </span>
              <span
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold"
                style={{ background: `${riskColor}15`, color: riskColor }}
              >
                <span className="w-1.5 h-1.5 rounded-full" style={{ background: riskColor }} />
                {summary.risk_level} risk
              </span>
              {summary.eol_date && (
                <span className="inline-flex items-center gap-1 text-xs text-slate-500">
                  <Calendar size={12} />
                  EOL: {new Date(summary.eol_date).toLocaleDateString('en-CA')}
                </span>
              )}
            </div>
          </div>
          <div className="text-xs text-slate-400">
            {totalVersions} version{totalVersions !== 1 ? 's' : ''} ·
            Updated {summary.last_updated ? new Date(summary.last_updated).toLocaleDateString('en-CA') : '—'}
          </div>
        </div>
      </div>

      {/* ── Tab navigation ──────────────────────────────────────────────── */}
      <div className="card p-1.5 inline-flex gap-1">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`
              flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-150
              ${activeTab === tab.id
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'}
            `}
          >
            <tab.icon size={16} />
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Tab content ─────────────────────────────────────────────────── */}
      {activeTab === 'versions' && (
        <VersionsTab
          toolName={toolName!}
          versions={versionsQuery.data ?? []}
          isLoading={versionsQuery.isLoading}
          isError={versionsQuery.isError}
          onRetry={() => versionsQuery.refetch()}
        />
      )}
      {activeTab === 'cves' && (
        <CvesTab
          cves={cvesQuery.data ?? []}
          isLoading={cvesQuery.isLoading}
          isError={cvesQuery.isError}
          onRetry={() => cvesQuery.refetch()}
        />
      )}
      {activeTab === 'compatibility' && (
        <CompatibilityTab toolName={toolName!} versions={versionsQuery.data ?? []} />
      )}
      {activeTab === 'license' && (
        <LicenseTab toolName={toolName!} />
      )}
    </div>
  );
}

/* ============================================================================
   Tab: Versions
   ============================================================================ */

function VersionsTab({
  toolName,
  versions,
  isLoading,
  isError,
  onRetry,
}: {
  toolName: string;
  versions: VersionRow[];
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);

  const sortedVersions = useMemo(() => {
    if (!versions) return [];
    // Sort descending by default
    const sorted = sortVersions(versions.map(v => v.version));
    // Reconstruct array preserving order
    return sorted.map(sv => versions.find(v => v.version === sv)!);
  }, [versions]);

  if (isError) return <div className="card"><ErrorState message="Failed to load versions" onRetry={onRetry} /></div>;

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <ExportButton
          data={sortedVersions.map(v => ({
            version: v.version,
            release_date: v.release_date ? new Date(v.release_date).toLocaleDateString('en-CA') : '',
            breaking_changes_count: parseJsonField(v.breaking_changes).length,
            cve_count: v.cve_count,
            features_count: 0
          }))}
          columns={{
            version: 'Version',
            release_date: 'Release Date',
            breaking_changes_count: 'Breaking Changes Count',
            cve_count: 'CVE Count',
            features_count: 'Features Count'
          }}
          filename="versions"
          format="csv"
          label="Export Versions (CSV)"
        />
      </div>
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50/60">
              <th className="w-8 px-2" />
              <th className="text-left py-3 px-4 font-medium text-slate-500 text-xs uppercase tracking-wider">Version</th>
              <th className="text-left py-3 px-4 font-medium text-slate-500 text-xs uppercase tracking-wider">Release Date</th>
              <th className="text-center py-3 px-4 font-medium text-slate-500 text-xs uppercase tracking-wider">Breaking</th>
              <th className="text-center py-3 px-4 font-medium text-slate-500 text-xs uppercase tracking-wider">CVEs</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {isLoading
              ? Array.from({ length: 5 }).map((_, i) => <TableRowSkeleton key={i} columns={5} />)
              : sortedVersions.map((v, idx) => {
                  const isOpen = expanded === v.version;
                  let breakingEnriched = parseJsonField(v.breaking_changes_enriched);
                  const breakingCount = breakingEnriched.length > 0 ? breakingEnriched.length : parseJsonField(v.breaking_changes).length;
                  if (breakingEnriched.length === 0) {
                    const flatBc = parseJsonField(v.breaking_changes);
                    breakingEnriched = flatBc.map(b => ({ text: b, category: 'UNCATEGORIZED', impact: 'Low', action_required: false }));
                  }
                  const breakingGroups = breakingEnriched.reduce((acc: any, bc: any) => {
                    acc[bc.category] = acc[bc.category] || [];
                    acc[bc.category].push(bc);
                    return acc;
                  }, {});
                  const deprecated = parseJsonField(v.deprecated_apis);
                  const prevVersion = sortedVersions[idx + 1]?.version || '0.0.0';
                  return (
                    <React.Fragment key={v.version}>
                      <tr
                        key={v.version}
                        onClick={() => setExpanded(isOpen ? null : v.version)}
                        className="hover:bg-indigo-50/40 cursor-pointer transition-colors group"
                      >
                        <td className="py-3 px-2 text-center">
                          <ChevronDown
                            size={14}
                            className={`
                              text-slate-400 transition-transform duration-200 mx-auto
                              ${isOpen ? 'rotate-180' : ''}
                            `}
                          />
                        </td>
                        <td className="py-3 px-4">
                          <span className="font-mono font-medium text-slate-900 group-hover:text-indigo-600 transition-colors">
                            v{v.version}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-xs text-slate-500 tabular-nums">
                          {v.release_date
                            ? new Date(v.release_date).toLocaleDateString('en-CA')
                            : '—'}
                        </td>
                        <td className="py-3 px-4 text-center">
                          {breakingCount > 0 ? (
                            <span className="badge badge-high">
                              <AlertTriangle size={10} className="mr-1" />
                              {breakingCount}
                            </span>
                          ) : (
                            <Check size={14} className="mx-auto text-emerald-400" />
                          )}
                        </td>
                        <td className="py-3 px-4 text-center">
                          {v.cve_count > 0 ? (
                            <span className="text-xs font-semibold text-red-600 inline-flex items-center gap-1">
                              <ShieldAlert size={12} /> {v.cve_count}
                            </span>
                          ) : (
                            <span className="text-xs text-emerald-600">0</span>
                          )}
                        </td>
                      </tr>
                      {/* Expanded detail */}
                      {isOpen && (
                        <tr key={`${v.version}-detail`}>
                          <td colSpan={5} className="bg-slate-50/60 px-8 py-4">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-xs">
                              {/* Breaking changes */}
                              <div>
                                <h4 className="font-semibold text-slate-700 mb-2 flex items-center gap-1.5">
                                  <AlertTriangle size={12} className="text-amber-500" />
                                  Breaking Changes
                                </h4>
                                {breakingCount > 0 ? (
                                  <div className="space-y-3">
                                    {Object.entries(breakingGroups).map(([cat, items]: [string, any]) => (
                                      <div key={cat}>
                                        <div className="text-xs font-semibold text-slate-600 mb-1">{cat}</div>
                                        <ul className="space-y-1">
                                          {items.map((bc: any, i: number) => (
                                            <li key={i} className="text-slate-600 pl-3 border-l-2 flex flex-col gap-0.5" style={{ borderColor: bc.impact === 'High' ? '#fca5a5' : bc.impact === 'Medium' ? '#fcd34d' : '#e2e8f0' }}>
                                              <span>{bc.text}</span>
                                              {bc.impact !== 'Low' && (
                                                <span className={`text-[9px] px-1 py-0.5 rounded-sm self-start ${bc.impact === 'High' ? 'bg-rose-100 text-rose-700' : 'bg-amber-100 text-amber-700'}`}>{bc.impact} Impact</span>
                                              )}
                                            </li>
                                          ))}
                                        </ul>
                                      </div>
                                    ))}
                                  </div>
                                ) : (
                                  <p className="text-slate-400 italic">None</p>
                                )}
                              </div>
                              {/* Deprecated APIs */}
                              <div>
                                <h4 className="font-semibold text-slate-700 mb-2 flex items-center gap-1.5">
                                  <XIcon size={12} className="text-red-400" />
                                  Deprecated APIs
                                </h4>
                                {deprecated.length > 0 ? (
                                  <ul className="space-y-1">
                                    {deprecated.map((d, i) => (
                                      <li key={i} className="text-slate-600 pl-3 border-l-2 border-red-200 font-mono">
                                        {d}
                                      </li>
                                    ))}
                                  </ul>
                                ) : (
                                  <p className="text-slate-400 italic">None</p>
                                )}
                              </div>
                              <ConfigChangesTable toolName={toolName!} fromVersion={prevVersion} toVersion={v.version} />
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
          </tbody>
        </table>
      </div>
      {!isLoading && versions.length === 0 && (
        <div className="py-16 text-center">
          <Layers size={36} className="mx-auto text-slate-300" />
          <p className="text-sm text-slate-500 mt-3">No versions found</p>
        </div>
      )}
      </div>
    </div>
  );
}

function ConfigChangesTable({ toolName, fromVersion, toVersion }: { toolName: string; fromVersion: string; toVersion: string }) {
  const query = useQuery({
    queryKey: ['configDiff', toolName, fromVersion, toVersion],
    queryFn: async () => {
      const res = await api.get('/api/v1/analysis/config-diff', {
        params: { tool: toolName, from_version: fromVersion, to_version: toVersion }
      });
      return res.data?.data;
    },
    staleTime: 5 * 60_000,
  });

  if (query.isLoading) return <Skeleton className="h-10 w-full mt-4" />;
  if (query.isError) return null;

  const grouped = query.data;
  if (!grouped) return null;
  const allChanges = [...(grouped.new_param || []), ...(grouped.changed_default || []), ...(grouped.deprecated || [])];

  if (allChanges.length === 0) return null;

  return (
    <div className="col-span-1 md:col-span-2 mt-4 pt-4 border-t border-slate-200">
      <h4 className="font-semibold text-slate-700 mb-2 flex items-center gap-1.5">
        <Settings size={12} className="text-slate-500" />
        Config Changes
      </h4>
      <div className="overflow-x-auto rounded border border-slate-200">
        <table className="w-full text-xs text-left">
          <thead className="bg-slate-100/50">
            <tr>
              <th className="px-3 py-2 font-medium text-slate-600">Parameter</th>
              <th className="px-3 py-2 font-medium text-slate-600">Old Default</th>
              <th className="px-3 py-2 font-medium text-slate-600">New Default</th>
              <th className="px-3 py-2 font-medium text-slate-600 text-center">Impact</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {allChanges.map((c: any, i: number) => (
              <tr key={i} className={c.impact_level === 'High' ? 'bg-red-50/50' : ''}>
                <td className="px-3 py-2 font-mono text-slate-700">{c.param_name}</td>
                <td className="px-3 py-2 text-slate-500">{c.old_default || '—'}</td>
                <td className="px-3 py-2 text-slate-700">{c.new_default || '—'}</td>
                <td className="px-3 py-2 text-center">
                  <span className={`inline-flex px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                    c.impact_level === 'High' ? 'bg-red-100 text-red-700' : 
                    c.impact_level === 'Medium' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600'
                  }`}>
                    {c.impact_level}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ============================================================================
   Tab: CVEs
   ============================================================================ */

function CvesTab({
  cves,
  isLoading,
  isError,
  onRetry,
}: {
  cves: CveRow[];
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
}) {
  const [severityFilter, setSeverityFilter] = useState<string>('All');
  const [searchCve, setSearchCve] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);

  const filtered = useMemo(() => {
    return cves.filter((c) => {
      const matchSev = severityFilter === 'All' || c.severity === severityFilter;
      const matchSearch = !searchCve || c.cve_id.toLowerCase().includes(searchCve.toLowerCase());
      return matchSev && matchSearch;
    });
  }, [cves, severityFilter, searchCve]);

  // Group by severity
  const grouped = useMemo(() => {
    const groups: Record<string, CveRow[]> = { Critical: [], High: [], Medium: [], Low: [] };
    for (const c of filtered) {
      const key = c.severity in groups ? c.severity : 'Low';
      groups[key].push(c);
    }
    return groups;
  }, [filtered]);

  if (isError) return <div className="card"><ErrorState message="Failed to load CVEs" onRetry={onRetry} /></div>;

  const SEVERITIES = ['All', 'Critical', 'High', 'Medium', 'Low'] as const;

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="card p-4 flex flex-col sm:flex-row items-start sm:items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search by CVE ID..."
            value={searchCve}
            onChange={(e) => setSearchCve(e.target.value)}
            className="w-full h-8 pl-8 pr-3 rounded-lg bg-slate-50 border border-slate-200 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 transition-all"
          />
        </div>
        <div className="flex items-center gap-1">
          {SEVERITIES.map((s) => (
            <button
              key={s}
              onClick={() => setSeverityFilter(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                severityFilter === s
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        <span className="text-xs text-slate-400 ml-auto tabular-nums">
          {filtered.length} CVE{filtered.length !== 1 ? 's' : ''}
        </span>
      </div>

      {isLoading ? (
        <div className="card p-4 space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState.NoCVEsFound days={30} />
      ) : (
        // Grouped display
        Object.entries(grouped)
          .filter(([, items]) => items.length > 0)
          .map(([severity, items]) => (
            <div key={severity} className="card overflow-hidden">
              <div className="px-5 py-3 border-b border-slate-100 bg-slate-50/40 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                  <SeverityBadge severity={severity} />
                  <span className="text-slate-400 font-normal">({items.length})</span>
                </h3>
              </div>
              <div className="divide-y divide-slate-50">
                {items.map((cve) => {
                  const isOpen = expanded === cve.cve_id;
                  return (
                    <div key={cve.cve_id}>
                      <div
                        onClick={() => setExpanded(isOpen ? null : cve.cve_id)}
                        className="flex items-center justify-between px-5 py-3 hover:bg-slate-50/50 cursor-pointer transition-colors"
                      >
                        <div className="flex items-center gap-3">
                          <ChevronDown size={14} className={`text-slate-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                          <div>
                            <a
                              href={`https://nvd.nist.gov/vuln/detail/${cve.cve_id}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="font-mono text-sm text-indigo-600 hover:text-indigo-700 inline-flex items-center gap-1"
                            >
                              {cve.cve_id} <ExternalLink size={10} />
                            </a>
                            {cve.fixed_in_version && (
                              <span className="ml-2 text-xs text-emerald-600">
                                Fixed in v{cve.fixed_in_version}
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-4">
                          <span
                            className="inline-flex items-center justify-center w-10 h-6 rounded text-xs font-bold tabular-nums"
                            style={{
                              background: (cve.cvss_score ?? 0) >= 9 ? '#fef2f2' : (cve.cvss_score ?? 0) >= 7 ? '#fff7ed' : '#fefce8',
                              color: (cve.cvss_score ?? 0) >= 9 ? '#dc2626' : (cve.cvss_score ?? 0) >= 7 ? '#ea580c' : '#ca8a04',
                            }}
                          >
                            {cve.cvss_score?.toFixed(1) ?? '—'}
                          </span>
                          <span className="text-xs text-slate-400 tabular-nums hidden sm:inline">
                            {cve.published_at ? new Date(cve.published_at).toLocaleDateString('en-CA') : ''}
                          </span>
                        </div>
                      </div>
                      {/* Expanded description */}
                      {isOpen && (
                        <div className="px-12 pb-4 text-xs text-slate-600 leading-relaxed bg-slate-50/30">
                          <p>{cve.description ?? 'No description available.'}</p>
                          {cve.affected_versions && (
                            <p className="mt-2 text-slate-500">
                              <span className="font-medium text-slate-700">Affected:</span>{' '}
                              {parseJsonField(cve.affected_versions).join(', ') || '—'}
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))
      )}
    </div>
  );
}

/* ============================================================================
   Tab: Compatibility
   ============================================================================ */

function CompatibilityTab({ toolName, versions }: { toolName: string; versions: VersionRow[] }) {
  // Fetch compatibility data for each version (batch via version detail)
  const compatQuery = useQuery({
    queryKey: ['toolCompat', toolName],
    queryFn: async () => {
      // Use the versions list and try to fetch compatibility for each
      const results: any[] = [];
      // Fetch top 20 versions' compatibility
      const topVersions = (versions || []).slice(0, 20);
      for (const v of topVersions) {
        try {
          const res = await api.get(`/api/v1/tools/${toolName}/versions/${v.version}`);
          const compat = res.data?.data?.compatibility;
          if (compat) {
            results.push({ version: v.version, ...compat });
          } else {
            results.push({ version: v.version, dependencies: null });
          }
        } catch {
          results.push({ version: v.version, dependencies: null });
        }
      }
      return results;
    },
    enabled: versions.length > 0,
    staleTime: 10 * 60_000,
  });

  const data = useMemo(() => compatQuery.data ?? [], [compatQuery.data]);

  // Extract all dependency keys
  const allDepKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const row of data) {
      const deps = typeof row.dependencies === 'string' ? (() => { try { return JSON.parse(row.dependencies); } catch { return {}; } })() : row.dependencies;
      if (deps && typeof deps === 'object') {
        Object.keys(deps).forEach((k) => keys.add(k));
      }
    }
    return Array.from(keys).sort();
  }, [data]);

  if (compatQuery.isLoading) {
    return (
      <div className="card p-6 space-y-3">
        {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
      </div>
    );
  }

  if (data.length === 0 || allDepKeys.length === 0) {
    return (
      <div className="card py-16 text-center">
        <PackageCheck size={36} className="mx-auto text-slate-300" />
        <p className="text-sm text-slate-500 mt-3">No compatibility data available yet</p>
      </div>
    );
  }

  return (
    <div className="card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50/60">
              <th className="text-left py-3 px-5 font-medium text-slate-500 text-xs uppercase tracking-wider sticky left-0 bg-slate-50/60">
                Version
              </th>
              {allDepKeys.map((key) => (
                <th key={key} className="text-center py-3 px-4 font-medium text-slate-500 text-xs uppercase tracking-wider whitespace-nowrap">
                  {key}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {data.map((row: any) => {
              const deps = typeof row.dependencies === 'string' ? (() => { try { return JSON.parse(row.dependencies); } catch { return {}; } })() : (row.dependencies ?? {});
              return (
                <tr key={row.version} className="hover:bg-slate-50/50 transition-colors">
                  <td className="py-3 px-5 font-mono font-medium text-slate-900 sticky left-0 bg-white">
                    v{row.version}
                  </td>
                  {allDepKeys.map((key) => {
                    const val = deps[key];
                    // Highlight missing/incompatible
                    const isMissing = !val;
                    return (
                      <td
                        key={key}
                        className={`py-3 px-4 text-center text-xs tabular-nums ${isMissing ? 'text-slate-300' : 'text-slate-700'}`}
                      >
                        {val ?? '—'}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ============================================================================
   Tab: License History
   ============================================================================ */

function LicenseTab({ toolName }: { toolName: string }) {
  const licenseQuery = useQuery({
    queryKey: ['toolLicense', toolName],
    queryFn: async () => {
      try {
        const res = await api.get('/api/v1/governance/license-changes', {
          params: { tool_name: toolName },
        });
        return res.data?.data ?? [];
      } catch {
        return [];
      }
    },
    staleTime: 10 * 60_000,
  });

  const changes = licenseQuery.data ?? [];

  if (licenseQuery.isLoading) {
    return (
      <div className="card p-6 space-y-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="flex gap-4">
            <Skeleton className="w-3 h-3 rounded-full flex-shrink-0 mt-1" />
            <div className="space-y-2 flex-1">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-3 w-60" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (changes.length === 0) {
    return (
      <div className="card py-16 text-center">
        <FileText size={36} className="mx-auto text-slate-300" />
        <p className="text-sm text-slate-500 mt-3">No license changes recorded</p>
        <p className="text-xs text-slate-400 mt-1">
          Most tools in the Data Stack use Apache 2.0 license
        </p>
      </div>
    );
  }

  return (
    <div className="card p-6">
      <div className="relative pl-6">
        {/* Timeline line */}
        <div className="absolute left-[5px] top-2 bottom-2 w-0.5 bg-slate-200" />

        <div className="space-y-6">
          {changes.map((change: any, i: number) => {
            const isFirst = i === 0;
            return (
              <div key={i} className="relative flex gap-4">
                {/* Dot */}
                <div
                  className={`
                    absolute -left-6 top-1 w-3 h-3 rounded-full border-2
                    ${isFirst ? 'bg-indigo-600 border-indigo-600' : 'bg-white border-slate-300'}
                  `}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-slate-900">
                      {change.new_license ?? 'Apache 2.0'}
                    </span>
                    {change.old_license && (
                      <>
                        <span className="text-xs text-slate-400">←</span>
                        <span className="text-xs text-slate-500 line-through">
                          {change.old_license}
                        </span>
                      </>
                    )}
                  </div>
                  <div className="flex items-center gap-2 mt-1 text-xs text-slate-400">
                    {change.version && (
                      <span className="font-mono">v{change.version}</span>
                    )}
                    {change.changed_at && (
                      <>
                        <span>·</span>
                        <span className="tabular-nums">
                          {new Date(change.changed_at).toLocaleDateString('en-CA')}
                        </span>
                      </>
                    )}
                  </div>
                  {change.reason && (
                    <p className="text-xs text-slate-500 mt-1.5">{change.reason}</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
