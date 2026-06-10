import { useParams, Link } from 'react-router-dom';
import {
  ArrowLeft,
  ShieldAlert,
  GitBranch,
  AlertTriangle,
  Calendar,
  ExternalLink,
} from 'lucide-react';

/* ─── Mock data ───────────────────────────────────────────────────────────── */
const TOOL_DATA: Record<string, any> = {
  'apache-kafka': {
    tool_name: 'apache-kafka',
    latest_version: '3.7.1',
    lifecycle_status: 'Active',
    risk_level: 'medium',
    total_cve_critical: 1,
    total_cve_high: 3,
    eol_date: null,
    versions: [
      { version: '3.7.1', release_date: '2024-04-15', cve_count: 0, has_breaking_changes: false },
      { version: '3.7.0', release_date: '2024-02-01', cve_count: 1, has_breaking_changes: true },
      { version: '3.6.2', release_date: '2023-11-20', cve_count: 0, has_breaking_changes: false },
      { version: '3.6.1', release_date: '2023-09-10', cve_count: 2, has_breaking_changes: false },
      { version: '3.6.0', release_date: '2023-07-01', cve_count: 1, has_breaking_changes: true },
    ],
    recent_breaking: [
      { version: '3.7.0', changes: ['Removed deprecated Consumer API', 'Changed default partition strategy'] },
      { version: '3.6.0', changes: ['KRaft mode now default', 'ZooKeeper deprecated'] },
    ],
    cve_breakdown: [
      { severity: 'Critical', count: 1 },
      { severity: 'High', count: 3 },
      { severity: 'Medium', count: 5 },
      { severity: 'Low', count: 2 },
    ],
  },
};

/* ─── Page ─────────────────────────────────────────────────────────────────── */
export default function ToolDetail() {
  const { toolName } = useParams<{ toolName: string }>();
  const tool = TOOL_DATA[toolName ?? ''] ?? TOOL_DATA['apache-kafka'];

  const riskColors: Record<string, string> = {
    critical: '#ef4444', high: '#f59e0b', medium: '#6366f1', low: '#10b981',
  };

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <Link
        to="/catalog"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-indigo-600 transition-colors"
      >
        <ArrowLeft size={14} /> Back to Catalog
      </Link>

      {/* Header */}
      <div className="card p-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">{tool.tool_name}</h1>
            <div className="flex items-center gap-3 mt-2">
              <span className="text-sm font-mono text-slate-600">v{tool.latest_version}</span>
              <span className={`badge badge-${tool.lifecycle_status.toLowerCase()}`}>
                {tool.lifecycle_status}
              </span>
              <span
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold"
                style={{
                  background: `${riskColors[tool.risk_level]}15`,
                  color: riskColors[tool.risk_level],
                }}
              >
                <span
                  className="w-1.5 h-1.5 rounded-full"
                  style={{ background: riskColors[tool.risk_level] }}
                />
                {tool.risk_level} risk
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {tool.cve_breakdown.map((cve: any) => (
          <div key={cve.severity} className="card p-4">
            <p className="text-xs text-slate-500 uppercase tracking-wide">{cve.severity} CVEs</p>
            <p className="text-2xl font-bold text-slate-900 mt-1">{cve.count}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Version history */}
        <div className="lg:col-span-2 card">
          <div className="px-5 py-4 border-b border-slate-100">
            <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
              <GitBranch size={16} className="text-indigo-500" />
              Version History
            </h2>
          </div>
          <div className="divide-y divide-slate-50">
            {tool.versions.map((v: any) => (
              <div key={v.version} className="flex items-center justify-between px-5 py-3.5 hover:bg-slate-50/50 transition-colors">
                <div className="flex items-center gap-3">
                  <span className="font-mono text-sm font-medium text-slate-900">
                    v{v.version}
                  </span>
                  {v.has_breaking_changes && (
                    <span className="badge badge-high">Breaking</span>
                  )}
                </div>
                <div className="flex items-center gap-4">
                  {v.cve_count > 0 && (
                    <span className="flex items-center gap-1 text-xs text-red-600">
                      <ShieldAlert size={12} /> {v.cve_count} CVEs
                    </span>
                  )}
                  <span className="text-xs text-slate-400 flex items-center gap-1">
                    <Calendar size={12} /> {v.release_date}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Breaking changes */}
        <div className="card">
          <div className="px-5 py-4 border-b border-slate-100">
            <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
              <AlertTriangle size={16} className="text-amber-500" />
              Recent Breaking Changes
            </h2>
          </div>
          <div className="p-5 space-y-4">
            {tool.recent_breaking.map((bc: any) => (
              <div key={bc.version}>
                <p className="text-xs font-semibold text-slate-700 mb-1.5">v{bc.version}</p>
                <ul className="space-y-1">
                  {bc.changes.map((change: string, i: number) => (
                    <li key={i} className="text-xs text-slate-600 pl-3 border-l-2 border-amber-300">
                      {change}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
