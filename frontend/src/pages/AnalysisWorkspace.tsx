import { useState, useEffect } from 'react';
import { GitCompareArrows, ArrowRight, Route, BarChart3, AlertTriangle, CheckCircle, ShieldAlert, Download, X } from 'lucide-react';
import axios from 'axios';

/* ─── Types & Mocks ───────────────────────────────────────────────────────── */
type Tab = 'version-diff' | 'stack-compare' | 'upgrade-path';

const TABS: { id: Tab; label: string; icon: typeof GitCompareArrows }[] = [
  { id: 'version-diff', label: 'Version Diff', icon: GitCompareArrows },
  { id: 'stack-compare', label: 'Stack Comparator', icon: BarChart3 },
  { id: 'upgrade-path', label: 'Upgrade Path', icon: Route },
];

const TOOL_VERSIONS: Record<string, string[]> = {
  'apache-kafka': ['3.4.0', '3.5.0', '3.6.0', '3.7.0', '3.7.1'],
  'apache-flink': ['1.17.0', '1.18.0', '1.19.0'],
  'apache-spark': ['3.3.0', '3.4.0', '3.5.0', '3.5.1'],
  'delta-io': ['2.4.0', '3.0.0', '3.1.0'],
  'starrocks': ['3.1.0', '3.2.0', '3.3.0']
};

type VersionDiffResult = {
  breakingChanges: string[];
  resolvedCVEs: string[];
  newCVEs: { id: string; cvss: number }[];
  configChanges: { key: string; type: 'add' | 'remove' | 'modify'; oldVal?: string; newVal?: string }[];
  featureCount: number;
  bugFixCount: number;
};

type StackCompareResult = {
  tool: string;
  latestVersion: string;
  license: string;
  eolDate: string; // YYYY-MM-DD
  criticalCVEs: number;
  javaRequired: string;
  scalaVersion: string;
};

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
      <div className="card p-1.5 inline-flex gap-1 border border-slate-200 bg-white rounded-lg shadow-sm">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`
              flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium
              transition-all duration-150
              ${
                activeTab === tab.id
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
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
  const versions = TOOL_VERSIONS[tool] || [];
  const [fromVer, setFromVer] = useState(versions[0] || '');
  const [toVer, setToVer] = useState(versions[versions.length - 1] || '');

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<VersionDiffResult | null>(null);

  // Auto-update versions when tool changes
  useEffect(() => {
    const v = TOOL_VERSIONS[tool] || [];
    setFromVer(v[0] || '');
    setToVer(v[v.length - 1] || '');
    setResult(null);
  }, [tool]);

  const handleCompare = async () => {
    if (!tool || !fromVer || !toVer) return;
    setLoading(true);
    try {
      const res = await axios.get('/api/v1/analysis/version-diff', {
        params: { tool, from: fromVer, to: toVer }
      });
      setResult(res.data.data);
    } catch (e) {
      // Mock result as fallback
      setTimeout(() => {
        setResult({
          breakingChanges: ['Removed deprecated Producer API', 'Changed default partitioner'],
          resolvedCVEs: ['CVE-2023-44487', 'CVE-2023-34040'],
          newCVEs: [{ id: 'CVE-2024-21287', cvss: 8.5 }, { id: 'CVE-2024-21288', cvss: 6.2 }],
          configChanges: [
            { key: 'log.retention.hours', type: 'modify', oldVal: '168', newVal: '72' },
            { key: 'new.feature.enable', type: 'add', newVal: 'true' },
            { key: 'old.feature.enable', type: 'remove' }
          ],
          featureCount: 12,
          bugFixCount: 45
        });
        setLoading(false);
      }, 800);
    }
  };

  return (
    <div className="card p-6 space-y-6 bg-white rounded-xl shadow-sm border border-slate-200">
      <h2 className="text-lg font-semibold text-slate-900">Version Diff</h2>

      {/* Input form */}
      <div className="flex flex-wrap items-end gap-4">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Tool</label>
          <input
            list="tool-list"
            value={tool}
            onChange={(e) => setTool(e.target.value)}
            className="h-9 px-3 rounded-lg border border-slate-200 text-sm bg-white outline-none focus:ring-2 focus:ring-indigo-500/20 w-40"
            placeholder="Select or type..."
          />
          <datalist id="tool-list">
            {Object.keys(TOOL_VERSIONS).map(t => <option key={t} value={t} />)}
          </datalist>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">From Version</label>
          <select
            value={fromVer}
            onChange={(e) => setFromVer(e.target.value)}
            className="h-9 px-3 rounded-lg border border-slate-200 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 w-32 bg-white"
          >
            {versions.map(v => <option key={v} value={v}>{v}</option>)}
          </select>
        </div>
        <ArrowRight size={20} className="text-slate-400 mb-1" />
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">To Version</label>
          <select
            value={toVer}
            onChange={(e) => setToVer(e.target.value)}
            className="h-9 px-3 rounded-lg border border-slate-200 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 w-32 bg-white"
          >
            {versions.map(v => <option key={v} value={v}>{v}</option>)}
          </select>
        </div>
        <button 
          onClick={handleCompare}
          disabled={loading}
          className="h-9 px-5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors shadow-sm disabled:opacity-50"
        >
          {loading ? 'Comparing...' : 'Compare'}
        </button>
      </div>

      {loading && (
        <div className="animate-pulse space-y-4 mt-6">
          <div className="h-40 bg-slate-100 rounded-lg"></div>
        </div>
      )}

      {/* Result Display */}
      {!loading && result && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
          {/* Left Column */}
          <div className="space-y-6">
            <div className="bg-white border border-slate-200 rounded-lg p-4 shadow-sm">
              <h3 className="text-sm font-semibold text-slate-900 mb-3 flex items-center gap-2">
                <AlertTriangle size={16} className="text-rose-500" />
                New Breaking Changes
              </h3>
              <ul className="space-y-2">
                {result.breakingChanges.map((bc, i) => (
                  <li key={i} className="text-sm text-slate-600 flex items-start gap-2">
                    <span className="text-rose-500 mt-0.5">•</span> {bc}
                  </li>
                ))}
              </ul>
            </div>

            <div className="bg-white border border-slate-200 rounded-lg p-4 shadow-sm">
              <h3 className="text-sm font-semibold text-slate-900 mb-3 flex items-center gap-2">
                <CheckCircle size={16} className="text-emerald-500" />
                Resolved CVEs
              </h3>
              <ul className="space-y-2">
                {result.resolvedCVEs.map((cve, i) => (
                  <li key={i} className="text-sm text-slate-600 flex items-start gap-2">
                    <CheckCircle size={14} className="text-emerald-500 mt-0.5" /> {cve}
                  </li>
                ))}
              </ul>
            </div>

            <div className="bg-white border border-slate-200 rounded-lg p-4 shadow-sm">
              <h3 className="text-sm font-semibold text-slate-900 mb-3 flex items-center gap-2">
                <ShieldAlert size={16} className="text-rose-500" />
                New CVEs
              </h3>
              <div className="flex flex-wrap gap-2">
                {result.newCVEs.map((cve, i) => (
                  <span key={i} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-rose-50 border border-rose-200 text-rose-700 text-xs font-medium">
                    {cve.id}
                    <span className="bg-rose-600 text-white px-1.5 py-0.5 rounded-sm">{cve.cvss}</span>
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Right Column */}
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-indigo-50 border border-indigo-100 rounded-lg p-4 text-center shadow-sm">
                <div className="text-4xl font-bold text-indigo-600 mb-1">{result.featureCount}</div>
                <div className="text-xs font-medium text-indigo-800 uppercase tracking-wide">New Features</div>
              </div>
              <div className="bg-emerald-50 border border-emerald-100 rounded-lg p-4 text-center shadow-sm">
                <div className="text-4xl font-bold text-emerald-600 mb-1">{result.bugFixCount}</div>
                <div className="text-xs font-medium text-emerald-800 uppercase tracking-wide">Bug Fixes</div>
              </div>
            </div>

            <div className="bg-slate-900 rounded-lg p-4 overflow-x-auto shadow-sm">
              <h3 className="text-sm font-semibold text-slate-100 mb-3">Config Changes</h3>
              <div className="font-mono text-xs space-y-2">
                {result.configChanges.map((c, i) => (
                  <div key={i} className="flex flex-col">
                    {c.type === 'add' && <div className="text-emerald-400">+ {c.key} = {c.newVal}</div>}
                    {c.type === 'remove' && <div className="text-rose-400">- {c.key}</div>}
                    {c.type === 'modify' && (
                      <div className="bg-slate-800/50 p-1.5 rounded">
                        <div className="text-rose-400">- {c.key} = {c.oldVal}</div>
                        <div className="text-emerald-400">+ {c.key} = {c.newVal}</div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {!loading && !result && (
        <div className="bg-slate-50 rounded-xl p-8 text-center border border-slate-100 mt-6">
          <GitCompareArrows size={40} className="mx-auto text-slate-300" />
          <p className="text-sm text-slate-500 mt-3">
            Select two versions and click Compare to see the diff
          </p>
        </div>
      )}
    </div>
  );
}

/* ─── Stack Compare panel ─────────────────────────────────────────────────── */
function StackComparePanel() {
  const [selectedTools, setSelectedTools] = useState<string[]>(['apache-kafka', 'apache-spark']);
  const [inputValue, setInputValue] = useState('');
  
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<StackCompareResult[] | null>(null);

  const availableTools = Object.keys(TOOL_VERSIONS).filter(t => !selectedTools.includes(t));

  const addTool = (t: string) => {
    if (selectedTools.length < 5 && !selectedTools.includes(t)) {
      setSelectedTools([...selectedTools, t]);
    }
    setInputValue('');
  };

  const removeTool = (t: string) => {
    setSelectedTools(selectedTools.filter(x => x !== t));
  };

  const handleCompare = async () => {
    if (selectedTools.length === 0) return;
    setLoading(true);
    try {
      const res = await axios.get('/api/v1/analysis/stack-comparator', {
        params: { tools: selectedTools.join(',') }
      });
      setResults(res.data.data);
    } catch (e) {
      setTimeout(() => {
        const mocks: StackCompareResult[] = selectedTools.map(t => ({
          tool: t,
          latestVersion: TOOL_VERSIONS[t]?.[TOOL_VERSIONS[t].length - 1] || '1.0.0',
          license: 'Apache 2.0',
          eolDate: t === 'apache-kafka' ? '2025-12-31' : t === 'apache-flink' ? '2025-06-30' : '2026-12-31',
          criticalCVEs: t === 'apache-spark' ? 2 : t === 'apache-kafka' ? 1 : 0,
          javaRequired: '11+',
          scalaVersion: t === 'apache-spark' ? '2.12/2.13' : '-'
        }));
        setResults(mocks);
        setLoading(false);
      }, 800);
    }
  };

  const handleExport = () => {
    if (!results) return;
    const rows = [
      ['Metric', ...results.map(r => r.tool)],
      ['Latest Version', ...results.map(r => r.latestVersion)],
      ['License', ...results.map(r => r.license)],
      ['EOL Date', ...results.map(r => r.eolDate)],
      ['Critical CVEs', ...results.map(r => r.criticalCVEs.toString())],
      ['Java Required', ...results.map(r => r.javaRequired)],
      ['Scala Version', ...results.map(r => r.scalaVersion)],
    ];
    const csvContent = "data:text/csv;charset=utf-8," + rows.map(e => e.join(",")).join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "stack_comparison.csv");
    document.body.appendChild(link);
    link.click();
    link.remove();
  };

  const maxCVEs = results ? Math.max(...results.map(r => r.criticalCVEs)) : 0;
  const minEol = results ? Math.min(...results.map(r => new Date(r.eolDate).getTime())) : 0;

  return (
    <div className="card p-6 space-y-6 bg-white rounded-xl shadow-sm border border-slate-200">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Stack Comparator</h2>
          <p className="text-sm text-slate-500 mt-1">
            Compare up to 5 tools side-by-side: versions, CVEs, licenses, and compatibility
          </p>
        </div>
        {results && (
          <button onClick={handleExport} className="flex items-center gap-2 h-9 px-4 rounded-lg border border-slate-200 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors shadow-sm">
            <Download size={16} />
            Export CSV
          </button>
        )}
      </div>

      <div className="flex flex-col gap-4">
        <label className="text-xs font-medium text-slate-600">Select Tools (Max 5)</label>
        <div className="flex flex-wrap gap-2 items-center bg-white border border-slate-200 p-2 rounded-lg min-h-[44px]">
          {selectedTools.map(t => (
            <span key={t} className="flex items-center gap-1.5 bg-indigo-50 text-indigo-700 px-2.5 py-1 rounded-md text-sm font-medium border border-indigo-100">
              {t}
              <button onClick={() => removeTool(t)} className="hover:text-indigo-900 bg-indigo-100/50 rounded-full p-0.5">
                <X size={14} />
              </button>
            </span>
          ))}
          {selectedTools.length < 5 && (
            <div className="relative flex-1 min-w-[120px]">
              <input
                list="available-tools"
                value={inputValue}
                onChange={(e) => {
                  if (availableTools.includes(e.target.value)) {
                    addTool(e.target.value);
                  } else {
                    setInputValue(e.target.value);
                  }
                }}
                placeholder="Add tool..."
                className="outline-none text-sm bg-transparent w-full h-full px-2 py-1"
              />
              <datalist id="available-tools">
                {availableTools.map(t => <option key={t} value={t} />)}
              </datalist>
            </div>
          )}
        </div>
        <div>
          <button 
            onClick={handleCompare}
            disabled={loading || selectedTools.length === 0}
            className="h-9 px-5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors shadow-sm disabled:opacity-50"
          >
            {loading ? 'Comparing...' : 'Compare Stack'}
          </button>
        </div>
      </div>

      {loading && (
        <div className="animate-pulse space-y-2 mt-6">
          <div className="h-10 bg-slate-100 rounded-md"></div>
          <div className="h-10 bg-slate-100 rounded-md"></div>
          <div className="h-10 bg-slate-100 rounded-md"></div>
          <div className="h-10 bg-slate-100 rounded-md"></div>
        </div>
      )}

      {!loading && results && (
        <div className="overflow-x-auto mt-6 border border-slate-200 rounded-lg shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50">
                <th className="text-left py-3 px-4 font-medium text-slate-500 w-40">Metric</th>
                {results.map(r => (
                  <th key={r.tool} className="text-center py-3 px-4 font-medium text-slate-900">{r.tool}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              <tr>
                <td className="py-3 px-4 text-slate-600 font-medium bg-slate-50/30">Latest Version</td>
                {results.map(r => (
                  <td key={r.tool} className="py-3 px-4 text-center font-mono">{r.latestVersion}</td>
                ))}
              </tr>
              <tr>
                <td className="py-3 px-4 text-slate-600 font-medium bg-slate-50/30">License</td>
                {results.map(r => (
                  <td key={r.tool} className="py-3 px-4 text-center">{r.license}</td>
                ))}
              </tr>
              <tr>
                <td className="py-3 px-4 text-slate-600 font-medium bg-slate-50/30">EOL Date</td>
                {results.map(r => (
                  <td key={r.tool} className={`py-3 px-4 text-center ${new Date(r.eolDate).getTime() === minEol ? 'bg-rose-50 text-rose-700 font-semibold' : ''}`}>
                    {r.eolDate}
                  </td>
                ))}
              </tr>
              <tr>
                <td className="py-3 px-4 text-slate-600 font-medium bg-slate-50/30">Critical CVEs</td>
                {results.map(r => (
                  <td key={r.tool} className={`py-3 px-4 text-center ${r.criticalCVEs === maxCVEs && maxCVEs > 0 ? 'bg-rose-50 text-rose-700 font-semibold' : ''}`}>
                    {r.criticalCVEs > 0 ? (
                      <span className="inline-flex items-center gap-1 justify-center">
                        <AlertTriangle size={14} className={r.criticalCVEs === maxCVEs ? 'text-rose-600' : 'text-amber-500'} />
                        {r.criticalCVEs}
                      </span>
                    ) : (
                      <span className="text-emerald-600 flex items-center justify-center gap-1"><CheckCircle size={14} /> 0</span>
                    )}
                  </td>
                ))}
              </tr>
              <tr>
                <td className="py-3 px-4 text-slate-600 font-medium bg-slate-50/30">Java Required</td>
                {results.map(r => (
                  <td key={r.tool} className="py-3 px-4 text-center">{r.javaRequired}</td>
                ))}
              </tr>
              <tr>
                <td className="py-3 px-4 text-slate-600 font-medium bg-slate-50/30">Scala Version</td>
                {results.map(r => (
                  <td key={r.tool} className="py-3 px-4 text-center">{r.scalaVersion}</td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ─── Upgrade Path panel ──────────────────────────────────────────────────── */
function UpgradePathPanel() {
  return (
    <div className="card p-6 space-y-6 bg-white rounded-xl shadow-sm border border-slate-200">
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
      <div className="bg-slate-50 rounded-xl p-8 text-center border border-slate-100">
        <Route size={40} className="mx-auto text-slate-300" />
        <p className="text-sm text-slate-500 mt-3">
          Select versions and click Find Path to see the upgrade route
        </p>
      </div>
    </div>
  );
}
