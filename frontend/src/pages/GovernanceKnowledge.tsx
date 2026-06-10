import {
  Shield,
  ShieldCheck,
  ShieldAlert,
  FileText,
  AlertTriangle,
  CheckCircle2,
  XCircle,
} from 'lucide-react';

/* ─── Mock data ───────────────────────────────────────────────────────────── */
const COMPLIANCE = [
  { tool: 'apache-kafka', status: 'compliant', critical: 0, eol: false },
  { tool: 'apache-flink', status: 'at_risk', critical: 0, eol: false },
  { tool: 'apache-spark', status: 'non_compliant', critical: 2, eol: true },
  { tool: 'delta-io', status: 'compliant', critical: 0, eol: false },
  { tool: 'starrocks', status: 'compliant', critical: 0, eol: false },
];

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; icon: typeof CheckCircle2 }> = {
  compliant:      { label: 'Compliant',     color: '#059669', bg: '#ecfdf5', icon: CheckCircle2 },
  at_risk:        { label: 'At Risk',       color: '#d97706', bg: '#fffbeb', icon: AlertTriangle },
  non_compliant:  { label: 'Non-Compliant', color: '#dc2626', bg: '#fef2f2', icon: XCircle },
};

/* ─── Page ─────────────────────────────────────────────────────────────────── */
export default function GovernanceKnowledge() {
  const compliant = COMPLIANCE.filter((c) => c.status === 'compliant').length;
  const atRisk    = COMPLIANCE.filter((c) => c.status === 'at_risk').length;
  const nonComp   = COMPLIANCE.filter((c) => c.status === 'non_compliant').length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
          <Shield size={24} className="text-indigo-500" />
          Governance & Knowledge
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Compliance status, EOL tracking, and license governance
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="card p-5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-emerald-50 flex items-center justify-center">
              <ShieldCheck size={20} className="text-emerald-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{compliant}</p>
              <p className="text-xs text-slate-500">Compliant</p>
            </div>
          </div>
        </div>
        <div className="card p-5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-amber-50 flex items-center justify-center">
              <AlertTriangle size={20} className="text-amber-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{atRisk}</p>
              <p className="text-xs text-slate-500">At Risk</p>
            </div>
          </div>
        </div>
        <div className="card p-5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-red-50 flex items-center justify-center">
              <ShieldAlert size={20} className="text-red-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{nonComp}</p>
              <p className="text-xs text-slate-500">Non-Compliant</p>
            </div>
          </div>
        </div>
      </div>

      {/* Compliance table */}
      <div className="card">
        <div className="px-5 py-4 border-b border-slate-100">
          <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
            <FileText size={16} className="text-indigo-500" />
            Compliance Summary
          </h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/50">
                <th className="text-left py-3 px-5 font-medium text-slate-500">Tool</th>
                <th className="text-center py-3 px-5 font-medium text-slate-500">Status</th>
                <th className="text-center py-3 px-5 font-medium text-slate-500">Critical CVEs</th>
                <th className="text-center py-3 px-5 font-medium text-slate-500">EOL</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {COMPLIANCE.map((item) => {
                const cfg = STATUS_CONFIG[item.status];
                const StatusIcon = cfg.icon;
                return (
                  <tr key={item.tool} className="hover:bg-slate-50/50 transition-colors">
                    <td className="py-3.5 px-5 font-medium text-slate-900">{item.tool}</td>
                    <td className="py-3.5 px-5 text-center">
                      <span
                        className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold"
                        style={{ background: cfg.bg, color: cfg.color }}
                      >
                        <StatusIcon size={12} /> {cfg.label}
                      </span>
                    </td>
                    <td className="py-3.5 px-5 text-center">
                      {item.critical > 0 ? (
                        <span className="badge badge-critical">{item.critical}</span>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                    <td className="py-3.5 px-5 text-center">
                      {item.eol ? (
                        <span className="badge badge-eol">EOL</span>
                      ) : (
                        <span className="text-emerald-600 text-xs">Active</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
