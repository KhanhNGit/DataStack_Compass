import { useState, useEffect } from 'react';
import { GitCompareArrows, ArrowRight, Route, BarChart3, AlertTriangle, CheckCircle, ShieldAlert, Download, X, Calendar, Lock } from 'lucide-react';
import axios from 'axios';
import { useToast } from '../components/Toast/ToastProvider';
import ExportButton from '../components/ExportButton/ExportButton';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';

/* ─── Types & Mocks ───────────────────────────────────────────────────────── */
type Tab = 'version-diff' | 'stack-compare' | 'upgrade-path' | 'eol-assessment';

const TABS: { id: Tab; label: string; icon: typeof GitCompareArrows }[] = [
  { id: 'version-diff', label: 'Version Diff', icon: GitCompareArrows },
  { id: 'stack-compare', label: 'Stack Comparator', icon: BarChart3 },
  { id: 'upgrade-path', label: 'Upgrade Path', icon: Route },
  { id: 'eol-assessment', label: 'EOL Impact', icon: Calendar },
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
  configChanges: { key: string; type: 'add' | 'remove' | 'modify'; oldVal?: string; newVal?: string; impact_level?: string }[];
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
      {activeTab === 'eol-assessment' && <EolAssessmentPanel />}
    </div>
  );
}

/* ─── Version Diff panel ──────────────────────────────────────────────────── */
function VersionDiffPanel() {
  const toast = useToast();
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
      const data = res.data.data;
      setResult({
        breakingChanges: data.diff.new_breaking_changes || [],
        resolvedCVEs: data.diff.resolved_cves?.map((c: any) => c.cve_id) || [],
        newCVEs: data.diff.new_cves?.map((c: any) => ({ id: c.cve_id, cvss: c.cvss_score })) || [],
        configChanges: data.diff.config_changes || [],
        featureCount: 0, // Not accurately provided by API yet
        bugFixCount: 0,  // Not accurately provided by API yet
      });
      toast.success('Comparison completed successfully');
    } catch (e) {
      toast.warning('Using mock data as API is unavailable');
      // Mock result as fallback
      setTimeout(() => {
        setResult({
          breakingChanges: ['Removed deprecated Producer API', 'Changed default partitioner'],
          resolvedCVEs: ['CVE-2023-44487', 'CVE-2023-34040'],
          newCVEs: [{ id: 'CVE-2024-21287', cvss: 8.5 }, { id: 'CVE-2024-21288', cvss: 6.2 }],
          configChanges: [
            { key: 'log.retention.hours', type: 'modify', oldVal: '168', newVal: '72', impact_level: 'High' },
            { key: 'new.feature.enable', type: 'add', newVal: 'true', impact_level: 'Low' },
            { key: 'old.feature.enable', type: 'remove', impact_level: 'Low' }
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
                {result.configChanges.length > 0 ? result.configChanges.map((c, i) => (
                  <div key={i} className="flex flex-col">
                    <div className="flex items-center gap-2 mb-1">
                      {c.impact_level === 'High' && (
                        <span className="bg-red-500 text-white text-[10px] px-1.5 py-0.5 rounded font-sans uppercase">High Impact</span>
                      )}
                    </div>
                    {c.type === 'add' && <div className="text-emerald-400">+ {c.key} = {c.newVal}</div>}
                    {c.type === 'remove' && <div className="text-rose-400">- {c.key}</div>}
                    {c.type === 'modify' && (
                      <div className="bg-slate-800/50 p-1.5 rounded">
                        <div className="text-rose-400">- {c.key} = {c.oldVal}</div>
                        <div className="text-emerald-400">+ {c.key} = {c.newVal}</div>
                      </div>
                    )}
                  </div>
                )) : (
                  <div className="text-slate-500 italic font-sans">No config changes detected.</div>
                )}
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
  const toast = useToast();
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
      toast.success('Stack comparison successful');
    } catch (e) {
      toast.warning('Using mock data as API is unavailable');
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
    toast.success('CSV exported successfully');
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
  const [tool, setTool] = useState('apache-kafka');
  const versions = TOOL_VERSIONS[tool] || [];
  const [currentVersion, setCurrentVersion] = useState(versions[0] || '');
  const [targetVersion, setTargetVersion] = useState(versions[versions.length - 1] || '');
  
  const [loading, setLoading] = useState(false);
  const [steps, setSteps] = useState<any[] | null>(null);

  // Auto-update versions when tool changes
  useEffect(() => {
    const v = TOOL_VERSIONS[tool] || [];
    setCurrentVersion(v[0] || '');
    setTargetVersion(v[v.length - 1] || '');
    setSteps(null);
  }, [tool]);

  const targetVersions = versions.filter(v => versions.indexOf(v) > versions.indexOf(currentVersion));

  const handlePlanUpgrade = () => {
    setLoading(true);
    // Simulate API request and generating steps
    setTimeout(() => {
      const startIndex = versions.indexOf(currentVersion);
      const endIndex = versions.indexOf(targetVersion);
      const generatedSteps = [];
      
      for (let i = startIndex; i < endIndex; i++) {
        generatedSteps.push({
          fromVer: versions[i],
          toVer: versions[i+1],
          breakingChanges: i === startIndex ? [
            `KIP-792: Changed default value of log.retention.bytes`,
            `KIP-811: Deprecated GroupMetadata`
          ] : [
            `Minor configuration changes`
          ],
          cvesFixed: [
            { id: `CVE-202${i}-1234`, isCritical: i % 2 === 0 },
            { id: `CVE-202${i}-5678`, isCritical: false }
          ],
          newFeatures: 10 + i * 2
        });
      }
      setSteps(generatedSteps);
      setLoading(false);
    }, 600);
  };

  const totalBreaking = steps?.reduce((acc, step) => acc + step.breakingChanges.length, 0) || 0;
  const totalCves = steps?.reduce((acc, step) => acc + step.cvesFixed.length, 0) || 0;
  const effort = totalBreaking > 5 ? 'High' : totalBreaking > 2 ? 'Medium' : 'Low';

  return (
    <div className="card p-6 space-y-6 bg-white rounded-xl shadow-sm border border-slate-200">
      <h2 className="text-lg font-semibold text-slate-900">Upgrade Path Planner</h2>
      <p className="text-sm text-slate-500">
        Find the safest upgrade route between two versions with cumulative breaking changes
      </p>

      {/* Input */}
      <div className="flex flex-wrap items-end gap-4">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Tool</label>
          <select 
            value={tool} 
            onChange={e => setTool(e.target.value)}
            className="h-9 px-3 rounded-lg border border-slate-200 text-sm bg-white outline-none focus:ring-2 focus:ring-indigo-500/20"
          >
            {Object.keys(TOOL_VERSIONS).map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Current Version</label>
          <select 
            value={currentVersion} 
            onChange={e => setCurrentVersion(e.target.value)}
            className="h-9 px-3 rounded-lg border border-slate-200 text-sm bg-white outline-none focus:ring-2 focus:ring-indigo-500/20 w-32"
          >
            {versions.map(v => <option key={v} value={v}>{v}</option>)}
          </select>
        </div>
        <ArrowRight size={20} className="text-slate-400 mb-1" />
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Target Version</label>
          <select 
            value={targetVersion} 
            onChange={e => setTargetVersion(e.target.value)}
            className="h-9 px-3 rounded-lg border border-slate-200 text-sm bg-white outline-none focus:ring-2 focus:ring-indigo-500/20 w-32"
          >
            {targetVersions.map(v => <option key={v} value={v}>{v}</option>)}
          </select>
        </div>
        <button 
          onClick={handlePlanUpgrade}
          disabled={!targetVersion || currentVersion === targetVersion}
          className="h-9 px-5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? 'Planning...' : 'Plan Upgrade'}
        </button>
      </div>

      {!steps && !loading && (
        <div className="bg-slate-50 rounded-xl p-8 text-center border border-slate-100">
          <Route size={40} className="mx-auto text-slate-300" />
          <p className="text-sm text-slate-500 mt-3">
            Select versions and click Plan Upgrade to see the timeline
          </p>
        </div>
      )}

      {steps && (
        <div className="mt-8 relative">
          <div className="space-y-6 relative before:absolute before:inset-0 before:ml-5 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-slate-200 before:to-transparent">
            {steps.map((step, idx) => (
              <div key={idx} className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
                <div className="flex items-center justify-center w-10 h-10 rounded-full border border-white bg-indigo-100 text-indigo-600 shadow shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 z-10">
                  <ArrowRight size={18} className="md:hidden" />
                  <ArrowRight size={18} className="hidden md:block group-odd:rotate-180" />
                </div>
                <div className="w-[calc(100%-4rem)] md:w-[calc(50%-2.5rem)] card p-4 hover:shadow-md transition-shadow">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="font-bold text-slate-800 text-base">{step.fromVer} → {step.toVer}</h3>
                  </div>
                  
                  <div className="space-y-3 text-sm">
                    {step.breakingChanges.length > 0 && (
                      <div>
                        <div className="font-semibold text-rose-600 flex items-center gap-1.5 mb-1.5">
                          <AlertTriangle size={14} />
                          {step.breakingChanges.length} Breaking Changes
                        </div>
                        <ul className="text-slate-600 space-y-1 text-xs">
                          {step.breakingChanges.map((bc: string, i: number) => (
                            <li key={i} className="flex items-start gap-1.5">
                              <span className="text-rose-400 mt-0.5">•</span> {bc}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    
                    <div className="flex items-center gap-4 border-t border-slate-100 pt-3">
                      <div className="flex items-center gap-1.5 text-emerald-600 font-medium text-xs">
                        <Lock size={14} />
                        {step.cvesFixed.length} CVEs Fixed ({step.cvesFixed.filter((c: any) => c.isCritical).length} Critical)
                      </div>
                      <div className="flex items-center gap-1.5 text-indigo-600 font-medium text-xs">
                        <BarChart3 size={14} />
                        {step.newFeatures} New Features
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Summary Box */}
          <div className="mt-8 max-w-xl mx-auto card bg-slate-900 border-slate-800 text-slate-200 p-6 shadow-xl relative z-20">
            <h3 className="text-lg font-bold text-white mb-4">Migration Summary</h3>
            <div className="grid grid-cols-3 gap-4 mb-6">
              <div className="text-center">
                <div className="text-3xl font-bold text-rose-400 mb-1">{totalBreaking}</div>
                <div className="text-xs uppercase tracking-wider text-slate-400 font-medium">Breaking Changes</div>
              </div>
              <div className="text-center">
                <div className="text-3xl font-bold text-emerald-400 mb-1">{totalCves}</div>
                <div className="text-xs uppercase tracking-wider text-slate-400 font-medium">CVEs Resolved</div>
              </div>
              <div className="text-center">
                <div className="text-3xl font-bold text-indigo-400 mb-1">
                  <span className={effort === 'High' ? 'text-rose-400' : effort === 'Medium' ? 'text-amber-400' : 'text-emerald-400'}>{effort}</span>
                </div>
                <div className="text-xs uppercase tracking-wider text-slate-400 font-medium">Est. Effort</div>
              </div>
            </div>
            <ExportButton
              data={steps}
              columns={{}}
              filename={`${tool}_migration_checklist`}
              format="markdown"
              label="Export Migration Checklist"
              className="w-full h-10 rounded-lg bg-white/10 hover:bg-white/20 text-white font-medium flex items-center justify-center gap-2 transition-colors border border-white/10"
              customFormatter={(data) => {
                let md = `# Migration Checklist: ${tool}\n\n`;
                md += `**Upgrade Path:** ${currentVersion} -> ${targetVersion}\n\n`;
                
                data.forEach((step, idx) => {
                  md += `## Step ${idx + 1}: ${step.fromVer} to ${step.toVer}\n`;
                  md += `### ⚠ Breaking Changes\n`;
                  step.breakingChanges.forEach((bc: string) => md += `- [ ] ${bc}\n`);
                  md += `\n### 🔒 CVEs Fixed\n`;
                  step.cvesFixed.forEach((cve: any) => md += `- ${cve.id} ${cve.isCritical ? '(Critical)' : ''}\n`);
                  md += `\n`;
                });
                return md;
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── EOL Impact Assessment panel ─────────────────────────────────────────── */
function EolAssessmentPanel() {
  const toast = useToast();
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchEolData();
  }, []);

  const fetchEolData = async () => {
    setLoading(true);
    try {
      const res = await axios.get('/api/v1/assets/eol-timeline');
      setData(res.data.data);
    } catch (e) {
      toast.error('Failed to load EOL timeline data');
    } finally {
      setLoading(false);
    }
  };

  const getBarColor = (days: number) => {
    if (days > 180) return '#10b981'; // Green
    if (days >= 90) return '#eab308'; // Yellow
    if (days >= 30) return '#f97316'; // Orange
    return '#ef4444'; // Red
  };

  const handleExportCSV = () => {
    if (!data.length) return;
    
    const rows = [
      ['Tool', 'Current Version', 'EOL Date', 'Days Remaining', 'Recommended Action']
    ];
    
    data.forEach(item => {
      const action = item.days_remaining < 30 ? 'Immediate Upgrade Required' : 
                     item.days_remaining < 90 ? 'Plan Upgrade Soon' : 'Monitor';
      rows.push([
        item.tool_name, 
        item.version_in_use, 
        item.eol_date ? new Date(item.eol_date).toISOString().split('T')[0] : 'N/A', 
        item.days_remaining?.toString() || '0', 
        action
      ]);
    });
    
    const csvContent = "data:text/csv;charset=utf-8," + rows.map(e => e.join(",")).join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "eol_assessment_report.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast.success('EOL Report exported successfully');
  };

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const p = payload[0].payload;
      return (
        <div className="bg-slate-900 text-white p-3 rounded-lg shadow-xl text-sm border border-slate-700 min-w-[200px]">
          <p className="font-bold mb-1 text-indigo-300">{p.tool_name}</p>
          <p className="text-slate-300">Version: <span className="text-white font-medium">{p.version_in_use}</span></p>
          <p className="text-slate-300">EOL Date: <span className="text-white font-medium">{p.eol_date ? new Date(p.eol_date).toLocaleDateString() : 'N/A'}</span></p>
          <p className="text-slate-300">Days Left: <span className="text-white font-medium">{p.days_remaining}</span></p>
          
          <div className="mt-3 pt-3 border-t border-slate-700 flex flex-col gap-2">
            <a href={`/catalog/${p.tool_name}`} className="text-indigo-400 hover:text-indigo-300 text-xs font-medium flex items-center gap-1">
              Check Latest Versions <ArrowRight size={12} />
            </a>
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="card p-6 space-y-6 bg-white rounded-xl shadow-sm border border-slate-200">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">EOL Impact Assessment</h2>
          <p className="text-sm text-slate-500 mt-1">
            Evaluate all team assets against their End-of-Life deadlines
          </p>
        </div>
        <button 
          onClick={handleExportCSV}
          disabled={!data.length}
          className="flex items-center gap-2 h-9 px-4 rounded-lg border border-slate-200 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors shadow-sm disabled:opacity-50"
        >
          <Download size={16} />
          Export EOL Report
        </button>
      </div>

      {loading ? (
        <div className="h-[400px] flex items-center justify-center">
          <div className="animate-pulse flex flex-col items-center gap-3">
            <div className="w-8 h-8 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin"></div>
            <p className="text-sm text-slate-500">Loading EOL data...</p>
          </div>
        </div>
      ) : data.length === 0 ? (
        <div className="bg-slate-50 rounded-xl p-8 text-center border border-slate-100">
          <Calendar size={40} className="mx-auto text-slate-300" />
          <p className="text-sm text-slate-500 mt-3">No EOL timeline data found for current assets.</p>
        </div>
      ) : (
        <div className="h-[400px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              layout="vertical"
              margin={{ top: 20, right: 30, left: 40, bottom: 5 }}
            >
              <XAxis type="number" label={{ value: 'Days Remaining', position: 'insideBottom', offset: -5 }} />
              <YAxis dataKey="tool_name" type="category" width={100} tick={{fontSize: 12}} />
              <Tooltip cursor={{fill: '#f8fafc'}} content={<CustomTooltip />} />
              <Bar dataKey="days_remaining" radius={[0, 4, 4, 0]} maxBarSize={40}>
                {data.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={getBarColor(entry.days_remaining)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
