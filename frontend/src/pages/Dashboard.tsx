import {
  Shield,
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  TrendingUp,
  Database,
  Bug,
  ArrowUpRight,
} from 'lucide-react';

/* ─── Stat card data (placeholder — sẽ fetch từ API) ──────────────────────── */
const STATS = [
  {
    label: 'Tools Tracked',
    value: '5',
    icon: Database,
    change: '+2 this month',
    color: '#6366f1',
    bg: '#eef2ff',
  },
  {
    label: 'Critical CVEs',
    value: '3',
    icon: ShieldAlert,
    change: '-1 from last week',
    color: '#ef4444',
    bg: '#fef2f2',
  },
  {
    label: 'Breaking Changes',
    value: '12',
    icon: AlertTriangle,
    change: '+4 new',
    color: '#f59e0b',
    bg: '#fffbeb',
  },
  {
    label: 'Compliance Score',
    value: '87%',
    icon: ShieldCheck,
    change: '+3% improvement',
    color: '#10b981',
    bg: '#ecfdf5',
  },
];

const RECENT_CVES = [
  { id: 'CVE-2024-12345', tool: 'apache-kafka', severity: 'Critical', cvss: 9.8 },
  { id: 'CVE-2024-67890', tool: 'apache-flink', severity: 'High', cvss: 8.2 },
  { id: 'CVE-2024-11111', tool: 'apache-spark', severity: 'Medium', cvss: 5.4 },
  { id: 'CVE-2024-22222', tool: 'starrocks', severity: 'High', cvss: 7.5 },
];

const TOOLS_STATUS = [
  { name: 'Apache Kafka', version: '3.7.1', status: 'Active', risk: 'medium' },
  { name: 'Apache Flink', version: '1.19.0', status: 'Active', risk: 'low' },
  { name: 'Apache Spark', version: '3.5.1', status: 'Maintenance', risk: 'high' },
  { name: 'Delta Lake', version: '3.1.0', status: 'Active', risk: 'low' },
  { name: 'StarRocks', version: '3.3.0', status: 'Active', risk: 'medium' },
];

/* ─── Severity badge ──────────────────────────────────────────────────────── */
function SeverityBadge({ severity }: { severity: string }) {
  const cls = `badge badge-${severity.toLowerCase()}`;
  return <span className={cls}>{severity}</span>;
}

function RiskDot({ risk }: { risk: string }) {
  const colors: Record<string, string> = {
    critical: '#ef4444',
    high: '#f59e0b',
    medium: '#6366f1',
    low: '#10b981',
  };
  return (
    <span
      className="inline-block w-2 h-2 rounded-full mr-2"
      style={{ background: colors[risk] ?? '#94a3b8' }}
    />
  );
}

/* ─── Page ─────────────────────────────────────────────────────────────────── */
export default function Dashboard() {
  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
        <p className="text-sm text-slate-500 mt-1">
          Real-time overview of your Data Stack risk posture
        </p>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {STATS.map((stat) => (
          <div key={stat.label} className="card p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">
                  {stat.label}
                </p>
                <p className="text-2xl font-bold text-slate-900 mt-1">{stat.value}</p>
              </div>
              <div
                className="w-10 h-10 rounded-lg flex items-center justify-center"
                style={{ background: stat.bg }}
              >
                <stat.icon size={20} style={{ color: stat.color }} />
              </div>
            </div>
            <div className="flex items-center mt-3 text-xs text-slate-500">
              <TrendingUp size={12} className="mr-1" />
              {stat.change}
            </div>
          </div>
        ))}
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Recent CVEs */}
        <div className="lg:col-span-3 card">
          <div className="px-5 py-4 border-b border-slate-100">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                <Bug size={16} className="text-red-500" />
                Recent CVEs
              </h2>
              <a
                href="/catalog"
                className="text-xs text-indigo-600 hover:text-indigo-700 flex items-center gap-1"
              >
                View all <ArrowUpRight size={12} />
              </a>
            </div>
          </div>
          <div className="divide-y divide-slate-50">
            {RECENT_CVES.map((cve) => (
              <div
                key={cve.id}
                className="flex items-center justify-between px-5 py-3.5 hover:bg-slate-50/50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <Shield size={16} className="text-slate-400" />
                  <div>
                    <p className="text-sm font-medium text-slate-900">{cve.id}</p>
                    <p className="text-xs text-slate-500">{cve.tool}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs font-mono text-slate-600">
                    CVSS {cve.cvss}
                  </span>
                  <SeverityBadge severity={cve.severity} />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Tool Status */}
        <div className="lg:col-span-2 card">
          <div className="px-5 py-4 border-b border-slate-100">
            <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
              <Database size={16} className="text-indigo-500" />
              Tool Status
            </h2>
          </div>
          <div className="divide-y divide-slate-50">
            {TOOLS_STATUS.map((tool) => (
              <div
                key={tool.name}
                className="flex items-center justify-between px-5 py-3 hover:bg-slate-50/50 transition-colors"
              >
                <div>
                  <p className="text-sm font-medium text-slate-900 flex items-center">
                    <RiskDot risk={tool.risk} />
                    {tool.name}
                  </p>
                  <p className="text-xs text-slate-500 ml-4">v{tool.version}</p>
                </div>
                <span
                  className={`badge badge-${tool.status.toLowerCase()}`}
                >
                  {tool.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
