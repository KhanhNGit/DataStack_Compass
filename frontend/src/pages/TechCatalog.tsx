import { useState, useMemo, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Database,
  Search,
  Filter,
  ChevronUp,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  AlertTriangle,
  Shield,
  Calendar,
} from 'lucide-react';
import api from '../config/api';

/* ============================================================================
   Types
   ============================================================================ */

interface ToolRow {
  tool_name: string;
  latest_version: string | null;
  lifecycle_status: string;
  eol_date: string | null;
  total_cve_critical: number;
  total_cve_high: number;
  last_updated: string | null;
  risk_level: string;
}

type SortKey = 'tool_name' | 'latest_version' | 'lifecycle_status' | 'eol_date' | 'total_cve_critical' | 'last_updated';
type SortDir = 'asc' | 'desc';

const LIFECYCLE_OPTIONS = ['All', 'Active', 'Maintenance', 'EOL'] as const;

const LIFECYCLE_BADGE: Record<string, { color: string; bg: string }> = {
  Active:      { color: '#059669', bg: '#ecfdf5' },
  Maintenance: { color: '#d97706', bg: '#fffbeb' },
  EOL:         { color: '#dc2626', bg: '#fef2f2' },
};

/* ============================================================================
   Sub-components
   ============================================================================ */

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`skeleton ${className}`} />;
}

function TableRowSkeleton() {
  return (
    <tr>
      {Array.from({ length: 6 }).map((_, i) => (
        <td key={i} className="py-3.5 px-5">
          <Skeleton className="h-4 w-full max-w-24" />
        </td>
      ))}
    </tr>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="w-12 h-12 rounded-full bg-red-50 flex items-center justify-center mb-3">
        <AlertTriangle size={24} className="text-red-500" />
      </div>
      <p className="text-sm text-slate-600 mb-3">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 transition-colors"
        >
          <RefreshCw size={14} /> Retry
        </button>
      )}
    </div>
  );
}

function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <ChevronDown size={14} className="text-slate-300" />;
  return dir === 'asc'
    ? <ChevronUp size={14} className="text-indigo-600" />
    : <ChevronDown size={14} className="text-indigo-600" />;
}

/* ============================================================================
   Main page
   ============================================================================ */

export default function TechCatalog() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // ── State from URL / local ──────────────────────────────────────────────
  const initialSearch = searchParams.get('search') ?? '';
  const [search, setSearch] = useState(initialSearch);
  const [statusFilter, setStatusFilter] = useState<string>('All');
  const [page, setPage] = useState(1);
  const [sortKey, setSortKey] = useState<SortKey>('tool_name');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const pageSize = 20;

  // ── API query ───────────────────────────────────────────────────────────
  const {
    data: apiResponse,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['techCatalog', search, statusFilter, page, pageSize],
    queryFn: async () => {
      const params: Record<string, string | number> = {
        page,
        page_size: pageSize,
      };
      if (search.trim()) params.search = search.trim();
      if (statusFilter !== 'All') params.lifecycle_status = statusFilter;
      const res = await api.get('/api/v1/tools', { params });
      return res.data;
    },
    staleTime: 5 * 60 * 1000,
  });

  const tools: ToolRow[] = apiResponse?.data ?? [];
  const total: number = apiResponse?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  // ── Client-side sort ────────────────────────────────────────────────────
  const sorted = useMemo(() => {
    const copy = [...tools];
    copy.sort((a, b) => {
      let aVal: any = a[sortKey];
      let bVal: any = b[sortKey];

      // null handling
      if (aVal == null && bVal == null) return 0;
      if (aVal == null) return 1;
      if (bVal == null) return -1;

      // numeric columns
      if (sortKey === 'total_cve_critical') {
        aVal = Number(aVal);
        bVal = Number(bVal);
      }

      if (typeof aVal === 'string') {
        const cmp = aVal.localeCompare(bVal as string, undefined, { sensitivity: 'base' });
        return sortDir === 'asc' ? cmp : -cmp;
      }
      const diff = (aVal as number) - (bVal as number);
      return sortDir === 'asc' ? diff : -diff;
    });
    return copy;
  }, [tools, sortKey, sortDir]);

  // ── Handlers ────────────────────────────────────────────────────────────
  const handleSort = useCallback((key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  }, [sortKey]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    if (search.trim()) {
      setSearchParams({ search: search.trim() });
    } else {
      setSearchParams({});
    }
  };

  const handleStatusChange = (status: string) => {
    setStatusFilter(status);
    setPage(1);
  };

  // ── Column definitions ──────────────────────────────────────────────────
  const COLUMNS: { key: SortKey; label: string; align: string }[] = [
    { key: 'tool_name',          label: 'Tool Name',      align: 'text-left'   },
    { key: 'latest_version',     label: 'Latest Version', align: 'text-left'   },
    { key: 'lifecycle_status',   label: 'Status',         align: 'text-center' },
    { key: 'eol_date',           label: 'EOL Date',       align: 'text-center' },
    { key: 'total_cve_critical', label: 'Critical CVEs',  align: 'text-center' },
    { key: 'last_updated',       label: 'Last Updated',   align: 'text-right'  },
  ];

  return (
    <div className="space-y-6">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
          <Database size={24} className="text-indigo-500" />
          Tech Catalog
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Track versions, CVEs, and lifecycle status of your Data Stack tools
        </p>
      </div>

      {/* ── Filter bar ──────────────────────────────────────────────────── */}
      <div className="card p-4">
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
          {/* Search */}
          <form onSubmit={handleSearchSubmit} className="relative flex-1 max-w-sm">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="Search tools..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="
                w-full h-9 pl-9 pr-4 rounded-lg
                bg-slate-50 border border-slate-200 text-sm
                outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400
                transition-all
              "
            />
          </form>

          {/* Status filter pills */}
          <div className="flex items-center gap-1.5">
            <Filter size={14} className="text-slate-400" />
            {LIFECYCLE_OPTIONS.map((f) => (
              <button
                key={f}
                onClick={() => handleStatusChange(f)}
                className={`
                  px-3 py-1.5 rounded-lg text-xs font-medium transition-all
                  ${
                    statusFilter === f
                      ? 'bg-indigo-600 text-white shadow-sm'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }
                `}
              >
                {f}
              </button>
            ))}
          </div>

          {/* Total count */}
          <span className="text-xs text-slate-400 ml-auto tabular-nums">
            {total} tool{total !== 1 ? 's' : ''}
          </span>
        </div>
      </div>

      {/* ── Table ───────────────────────────────────────────────────────── */}
      <div className="card overflow-hidden">
        {isError ? (
          <ErrorState message="Failed to load tools" onRetry={() => refetch()} />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50/60">
                    {COLUMNS.map((col) => (
                      <th
                        key={col.key}
                        onClick={() => handleSort(col.key)}
                        className={`
                          py-3 px-5 font-medium text-slate-500 text-xs uppercase tracking-wider
                          cursor-pointer select-none hover:text-slate-700 transition-colors
                          ${col.align}
                        `}
                      >
                        <span className="inline-flex items-center gap-1">
                          {col.label}
                          <SortIcon active={sortKey === col.key} dir={sortDir} />
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {isLoading
                    ? Array.from({ length: 6 }).map((_, i) => <TableRowSkeleton key={i} />)
                    : sorted.map((tool) => {
                        const lcBadge = LIFECYCLE_BADGE[tool.lifecycle_status] ?? LIFECYCLE_BADGE.Active;
                        return (
                          <tr
                            key={tool.tool_name}
                            onClick={() => navigate(`/catalog/${tool.tool_name}`)}
                            className="hover:bg-indigo-50/40 cursor-pointer transition-colors group"
                          >
                            {/* Tool Name */}
                            <td className="py-3.5 px-5">
                              <span className="font-medium text-slate-900 group-hover:text-indigo-600 transition-colors">
                                {tool.tool_name}
                              </span>
                            </td>
                            {/* Version */}
                            <td className="py-3.5 px-5 font-mono text-slate-600 text-xs">
                              {tool.latest_version ? `v${tool.latest_version}` : '—'}
                            </td>
                            {/* Status badge */}
                            <td className="py-3.5 px-5 text-center">
                              <span
                                className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold"
                                style={{ background: lcBadge.bg, color: lcBadge.color }}
                              >
                                {tool.lifecycle_status}
                              </span>
                            </td>
                            {/* EOL Date */}
                            <td className="py-3.5 px-5 text-center text-xs text-slate-500 tabular-nums">
                              {tool.eol_date ? (
                                <span className="inline-flex items-center gap-1">
                                  <Calendar size={12} className="text-slate-400" />
                                  {new Date(tool.eol_date).toLocaleDateString('en-CA')}
                                </span>
                              ) : (
                                <span className="text-slate-300">—</span>
                              )}
                            </td>
                            {/* Critical CVEs */}
                            <td className="py-3.5 px-5 text-center">
                              {tool.total_cve_critical > 0 ? (
                                <span className="inline-flex items-center gap-1 text-xs font-semibold text-red-600">
                                  <Shield size={12} />
                                  {tool.total_cve_critical}
                                </span>
                              ) : (
                                <span className="text-xs text-emerald-600">0</span>
                              )}
                            </td>
                            {/* Last Updated */}
                            <td className="py-3.5 px-5 text-right text-xs text-slate-400 tabular-nums">
                              {tool.last_updated
                                ? new Date(tool.last_updated).toLocaleDateString('en-CA')
                                : '—'}
                            </td>
                          </tr>
                        );
                      })}
                </tbody>
              </table>
            </div>

            {/* Empty state */}
            {!isLoading && sorted.length === 0 && (
              <div className="py-16 text-center">
                <Database size={40} className="mx-auto text-slate-300" />
                <p className="text-sm text-slate-500 mt-3">
                  No tools found matching your filters
                </p>
              </div>
            )}

            {/* ── Pagination ──────────────────────────────────────────────── */}
            {total > pageSize && (
              <div className="flex items-center justify-between px-5 py-3 border-t border-slate-100 bg-slate-50/30">
                <span className="text-xs text-slate-500 tabular-nums">
                  Page {page} of {totalPages} · {total} total
                </span>
                <div className="flex items-center gap-1">
                  <button
                    disabled={page <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    className="
                      w-8 h-8 rounded-lg flex items-center justify-center
                      text-slate-500 hover:bg-slate-100 disabled:opacity-30
                      disabled:cursor-not-allowed transition-colors
                    "
                  >
                    <ChevronLeft size={16} />
                  </button>
                  {/* Page numbers */}
                  {Array.from({ length: Math.min(5, totalPages) }).map((_, i) => {
                    // Show pages around current
                    let p = page - 2 + i;
                    if (page <= 2) p = i + 1;
                    if (page >= totalPages - 1) p = totalPages - 4 + i;
                    p = Math.max(1, Math.min(totalPages, p));
                    return (
                      <button
                        key={p}
                        onClick={() => setPage(p)}
                        className={`
                          w-8 h-8 rounded-lg flex items-center justify-center text-xs font-medium transition-colors
                          ${
                            page === p
                              ? 'bg-indigo-600 text-white'
                              : 'text-slate-600 hover:bg-slate-100'
                          }
                        `}
                      >
                        {p}
                      </button>
                    );
                  })}
                  <button
                    disabled={page >= totalPages}
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    className="
                      w-8 h-8 rounded-lg flex items-center justify-center
                      text-slate-500 hover:bg-slate-100 disabled:opacity-30
                      disabled:cursor-not-allowed transition-colors
                    "
                  >
                    <ChevronRight size={16} />
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
