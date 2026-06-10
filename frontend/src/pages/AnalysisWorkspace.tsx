import { useState } from 'react';
import { GitCompareArrows, ArrowRight, Route, BarChart3 } from 'lucide-react';

/* ─── Tab type ────────────────────────────────────────────────────────────── */
type Tab = 'version-diff' | 'stack-compare' | 'upgrade-path';

const TABS: { id: Tab; label: string; icon: typeof GitCompareArrows }[] = [
  { id: 'version-diff', label: 'Version Diff', icon: GitCompareArrows },
  { id: 'stack-compare', label: 'Stack Comparator', icon: BarChart3 },
  { id: 'upgrade-path', label: 'Upgrade Path', icon: Route },
];

/* ─── Page ─────────────────────────────────────────────────────────────────── */
export default function AnalysisWorkspace() {
  const [activeTab, setActiveTab] = useState<Tab>('version-diff');

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
          <GitCompareArrows size={24} className="text-indigo-500" />
          Analysis Workspace
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Compare versions, analyze upgrade paths, and evaluate stack risk
        </p>
      </div>

      {/* Tab bar */}
      <div className="card p-1.5 inline-flex gap-1">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`
              flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
              transition-all duration-150
              ${
                activeTab === tab.id
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }
            `}
          >
            <tab.icon size={16} />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'version-diff' && <VersionDiffPanel />}
      {activeTab === 'stack-compare' && <StackComparePanel />}
      {activeTab === 'upgrade-path' && <UpgradePathPanel />}
    </div>
  );
}

/* ─── Version Diff panel ──────────────────────────────────────────────────── */
function VersionDiffPanel() {
  const [tool, setTool] = useState('apache-kafka');
  const [fromVer, setFromVer] = useState('3.5.0');
  const [toVer, setToVer] = useState('3.7.0');

  return (
    <div className="card p-6 space-y-6">
      <h2 className="text-lg font-semibold text-slate-900">Version Diff</h2>

      {/* Input form */}
      <div className="flex flex-wrap items-end gap-4">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Tool</label>
          <select
            value={tool}
            onChange={(e) => setTool(e.target.value)}
            className="h-9 px-3 rounded-lg border border-slate-200 text-sm bg-white outline-none focus:ring-2 focus:ring-indigo-500/20"
          >
            <option value="apache-kafka">apache-kafka</option>
            <option value="apache-flink">apache-flink</option>
            <option value="apache-spark">apache-spark</option>
            <option value="delta-io">delta-io</option>
            <option value="starrocks">starrocks</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">From Version</label>
          <input
            value={fromVer}
            onChange={(e) => setFromVer(e.target.value)}
            className="h-9 px-3 rounded-lg border border-slate-200 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 w-28"
          />
        </div>
        <ArrowRight size={20} className="text-slate-400 mb-1" />
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">To Version</label>
          <input
            value={toVer}
            onChange={(e) => setToVer(e.target.value)}
            className="h-9 px-3 rounded-lg border border-slate-200 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 w-28"
          />
        </div>
        <button className="h-9 px-5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors shadow-sm">
          Compare
        </button>
      </div>

      {/* Placeholder result */}
      <div className="bg-slate-50 rounded-xl p-8 text-center">
        <GitCompareArrows size={40} className="mx-auto text-slate-300" />
        <p className="text-sm text-slate-500 mt-3">
          Select two versions and click Compare to see the diff
        </p>
      </div>
    </div>
  );
}

/* ─── Stack Compare panel ─────────────────────────────────────────────────── */
function StackComparePanel() {
  return (
    <div className="card p-6 space-y-6">
      <h2 className="text-lg font-semibold text-slate-900">Stack Comparator</h2>
      <p className="text-sm text-slate-500">
        Compare up to 5 tools side-by-side: versions, CVEs, licenses, and compatibility
      </p>

      {/* Comparison table placeholder */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200">
              <th className="text-left py-3 px-4 font-medium text-slate-500">Metric</th>
              <th className="text-center py-3 px-4 font-medium text-slate-900">Kafka</th>
              <th className="text-center py-3 px-4 font-medium text-slate-900">Flink</th>
              <th className="text-center py-3 px-4 font-medium text-slate-900">Spark</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            <tr>
              <td className="py-3 px-4 text-slate-600">Latest Version</td>
              <td className="py-3 px-4 text-center font-mono">3.7.1</td>
              <td className="py-3 px-4 text-center font-mono">1.19.0</td>
              <td className="py-3 px-4 text-center font-mono">3.5.1</td>
            </tr>
            <tr>
              <td className="py-3 px-4 text-slate-600">Critical CVEs</td>
              <td className="py-3 px-4 text-center"><span className="badge badge-critical">1</span></td>
              <td className="py-3 px-4 text-center"><span className="badge badge-low">0</span></td>
              <td className="py-3 px-4 text-center"><span className="badge badge-critical">2</span></td>
            </tr>
            <tr>
              <td className="py-3 px-4 text-slate-600">License</td>
              <td className="py-3 px-4 text-center">Apache 2.0</td>
              <td className="py-3 px-4 text-center">Apache 2.0</td>
              <td className="py-3 px-4 text-center">Apache 2.0</td>
            </tr>
            <tr>
              <td className="py-3 px-4 text-slate-600">Status</td>
              <td className="py-3 px-4 text-center"><span className="badge badge-active">Active</span></td>
              <td className="py-3 px-4 text-center"><span className="badge badge-active">Active</span></td>
              <td className="py-3 px-4 text-center"><span className="badge badge-maintenance">Maintenance</span></td>
            </tr>
            <tr>
              <td className="py-3 px-4 text-slate-600">Java</td>
              <td className="py-3 px-4 text-center">11+</td>
              <td className="py-3 px-4 text-center">11+</td>
              <td className="py-3 px-4 text-center">8/11/17</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ─── Upgrade Path panel ──────────────────────────────────────────────────── */
function UpgradePathPanel() {
  return (
    <div className="card p-6 space-y-6">
      <h2 className="text-lg font-semibold text-slate-900">Upgrade Path Finder</h2>
      <p className="text-sm text-slate-500">
        Find the safest upgrade route between two versions with cumulative breaking changes
      </p>

      {/* Input */}
      <div className="flex flex-wrap items-end gap-4">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Tool</label>
          <select className="h-9 px-3 rounded-lg border border-slate-200 text-sm bg-white outline-none focus:ring-2 focus:ring-indigo-500/20">
            <option>apache-kafka</option>
            <option>apache-flink</option>
            <option>apache-spark</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Current</label>
          <input defaultValue="3.3.0" className="h-9 px-3 rounded-lg border border-slate-200 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 w-28" />
        </div>
        <ArrowRight size={20} className="text-slate-400 mb-1" />
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Target</label>
          <input defaultValue="3.7.1" className="h-9 px-3 rounded-lg border border-slate-200 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 w-28" />
        </div>
        <button className="h-9 px-5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors shadow-sm">
          Find Path
        </button>
      </div>

      {/* Placeholder path */}
      <div className="bg-slate-50 rounded-xl p-8 text-center">
        <Route size={40} className="mx-auto text-slate-300" />
        <p className="text-sm text-slate-500 mt-3">
          Select versions and click Find Path to see the upgrade route
        </p>
      </div>
    </div>
  );
}
