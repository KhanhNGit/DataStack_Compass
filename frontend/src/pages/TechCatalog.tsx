import { Database, Search, Filter, ArrowUpRight } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

/* ─── Mock data (sẽ được thay bằng API calls) ────────────────────────────── */
const TOOLS = [
  {
    tool_name: 'apache-kafka',
    latest_version: '3.7.1',
    lifecycle_status: 'Active',
    risk_level: 'medium',
    total_cve_critical: 1,
    total_cve_high: 3,
    eol_date: null,
  },
  {
    tool_name: 'apache-flink',
    latest_version: '1.19.0',
    lifecycle_status: 'Active',
    risk_level: 'low',
    total_cve_critical: 0,
    total_cve_high: 1,
    eol_date: null,
  },
  {
    tool_name: 'apache-spark',
    latest_version: '3.5.1',
    lifecycle_status: 'Maintenance',
    risk_level: 'high',
    total_cve_critical: 2,
    total_cve_high: 5,
    eol_date: '2024-06-01',
  },
  {
    tool_name: 'delta-io',
    latest_version: '3.1.0',
    lifecycle_status: 'Active',
    risk_level: 'low',
    total_cve_critical: 0,
    total_cve_high: 0,
    eol_date: null,
  },
  {
    tool_name: 'starrocks',
    latest_version: '3.3.0',
    lifecycle_status: 'Active',
    risk_level: 'medium',
    total_cve_critical: 0,
    total_cve_high: 2,
    eol_date: null,
  },
];

const STATUS_FILTERS = ['All', 'Active', 'Maintenance', 'EOL'] as const;

/* ─── Risk indicator ──────────────────────────────────────────────────────── */
function RiskIndicator({ level }: { level: string }) {
  const config: Record<string, { label: string; color: string; bg: string }> = {
    critical: { label: 'Critical', color: '#dc2626', bg: '#fef2f2' },
    high:     { label: 'High',     color: '#ea580c', bg: '#fff7ed' },
    medium:   { label: 'Medium',   color: '#6366f1', bg: '#eef2ff' },
    low:      { label: 'Low',      color: '#16a34a', bg: '#f0fdf4' },
  };
  const c = config[level] ?? config.low;
  return (
    <span
      className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold"
      style={{ background: c.bg, color: c.color }}
    >
      {c.label}
    </span>
  );
}

/* ─── Page ─────────────────────────────────────────────────────────────────── */
export default function TechCatalog() {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('All');
  const navigate = useNavigate();

  const filtered = TOOLS.filter((t) => {
    const matchSearch = t.tool_name.toLowerCase().includes(search.toLowerCase());
    const matchStatus = statusFilter === 'All' || t.lifecycle_status === statusFilter;
    return matchSearch && matchStatus;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Database size={24} className="text-indigo-500" />
            Tech Catalog
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Track versions, CVEs, and lifecycle status of your Data Stack tools
          </p>
        </div>
      </div>

      {/* Filters bar */}
      <div className="card p-4">
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
          {/* Search */}
          <div className="relative flex-1 max-w-sm">
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
          </div>

          {/* Status filter */}
          <div className="flex items-center gap-1.5">
            <Filter size={14} className="text-slate-400" />
            {STATUS_FILTERS.map((f) => (
              <button
                key={f}
                onClick={() => setStatusFilter(f)}
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
        </div>
      </div>

      {/* Tool grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {filtered.map((tool) => (
          <div
            key={tool.tool_name}
            className="card p-5 cursor-pointer hover:border-indigo-200 transition-all"
            onClick={() => navigate(`/catalog/${tool.tool_name}`)}
          >
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-sm font-semibold text-slate-900">{tool.tool_name}</h3>
                <p className="text-xs text-slate-500 mt-0.5 font-mono">
                  v{tool.latest_version}
                </p>
              </div>
              <RiskIndicator level={tool.risk_level} />
            </div>

            {/* CVE stats */}
            <div className="flex items-center gap-4 mt-4">
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-red-500" />
                <span className="text-xs text-slate-600">
                  {tool.total_cve_critical} Critical
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-orange-500" />
                <span className="text-xs text-slate-600">
                  {tool.total_cve_high} High
                </span>
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between mt-4 pt-3 border-t border-slate-100">
              <span
                className={`badge badge-${tool.lifecycle_status.toLowerCase()}`}
              >
                {tool.lifecycle_status}
              </span>
              <span className="text-xs text-indigo-500 flex items-center gap-0.5">
                Details <ArrowUpRight size={12} />
              </span>
            </div>
          </div>
        ))}
      </div>

      {filtered.length === 0 && (
        <div className="card p-12 text-center">
          <Database size={40} className="mx-auto text-slate-300" />
          <p className="text-sm text-slate-500 mt-3">No tools found matching your filters</p>
        </div>
      )}
    </div>
  );
}
