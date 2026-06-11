import { useState, useEffect } from 'react';
import axios from 'axios';
import { 
  ShieldAlert, Shield, ShieldCheck, 
  Search, ExternalLink, Calendar, 
  Tag as TagIcon, X, Filter, 
  BookOpen, ChevronRight, Activity 
} from 'lucide-react';

/* ─── Types ───────────────────────────────────────────────────────────────── */
type CVE = {
  id: string;
  cvss: number;
  description: string;
};

type Bulletin = {
  id: string;
  date: string;
  tool: string;
  cve_count: number;
  severity: 'Critical' | 'High' | 'Medium' | 'Low';
  status: string;
  cves: CVE[];
};

type Blog = {
  id: string;
  title: string;
  tool: string;
  version: string;
  source: string;
  date: string;
  tags: string[];
  url: string;
};

/* ─── Page ─────────────────────────────────────────────────────────────────── */
export default function GovernanceKnowledge() {
  const [allBulletins, setAllBulletins] = useState<Bulletin[]>([]);
  const [bulletinsLoading, setBulletinsLoading] = useState(false);
  const [bulletinSeverityFilter, setBulletinSeverityFilter] = useState('All');
  const [bulletinToolFilter, setBulletinToolFilter] = useState('All');
  const [selectedBulletin, setSelectedBulletin] = useState<Bulletin | null>(null);

  const [blogs, setBlogs] = useState<Blog[]>([]);
  const [blogsLoading, setBlogsLoading] = useState(false);
  const [blogToolFilter, setBlogToolFilter] = useState('All');
  const [blogTagFilter, setBlogTagFilter] = useState('All');

  // Fetch Bulletins
  useEffect(() => {
    const fetchBulletins = async () => {
      setBulletinsLoading(true);
      try {
        const res = await axios.get('/api/v1/governance/bulletins', { params: { page: 1 } });
        setAllBulletins(res.data.data);
      } catch (e) {
        console.error('Failed to fetch bulletins', e);
      } finally {
        setBulletinsLoading(false);
      }
    };
    fetchBulletins();
  }, []);

  // Fetch Blogs
  useEffect(() => {
    const fetchBlogs = async () => {
      setBlogsLoading(true);
      try {
        const params: any = {};
        if (blogToolFilter !== 'All') params.tool = blogToolFilter;
        if (blogTagFilter !== 'All') params.tag = blogTagFilter;
        const res = await axios.get('/api/v1/governance/blogs', { params });
        setBlogs(res.data.data);
      } catch (e) {
        console.error('Failed to fetch blogs', e);
      } finally {
        setBlogsLoading(false);
      }
    };
    fetchBlogs();
  }, [blogToolFilter, blogTagFilter]);

  // Derived filtered bulletins
  const filteredBulletins = allBulletins.filter(b => {
    if (bulletinSeverityFilter !== 'All' && b.severity !== bulletinSeverityFilter) return false;
    if (bulletinToolFilter !== 'All' && b.tool !== bulletinToolFilter) return false;
    return true;
  });

  const tools = ['apache-kafka', 'apache-spark', 'apache-flink', 'delta-io', 'starrocks'];
  const severities = ['Critical', 'High', 'Medium', 'Low'];
  const blogTags = ['Breaking Change', 'Security', 'Performance', 'Migration Guide'];

  return (
    <div className="space-y-8 relative">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
          <ShieldAlert size={24} className="text-indigo-500" />
          Governance & Knowledge
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Monitor security bulletins and stay up to date with the latest technical knowledge
        </p>
      </div>

      {/* ─── Security Bulletins Board ────────────────────────────────────────── */}
      <section className="card bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="p-5 border-b border-slate-200 bg-slate-50/50 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Activity size={18} className="text-rose-500" />
            <h2 className="text-lg font-semibold text-slate-900">Security Bulletins Board</h2>
          </div>
          
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 bg-white border border-slate-200 rounded-lg px-3 py-1.5 shadow-sm">
              <Filter size={14} className="text-slate-400" />
              <select 
                value={bulletinToolFilter}
                onChange={(e) => setBulletinToolFilter(e.target.value)}
                className="text-sm bg-transparent outline-none text-slate-700 font-medium cursor-pointer"
              >
                <option value="All">All Tools</option>
                {tools.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            
            <div className="flex items-center gap-2 bg-white border border-slate-200 rounded-lg px-3 py-1.5 shadow-sm">
              <Shield size={14} className="text-slate-400" />
              <select 
                value={bulletinSeverityFilter}
                onChange={(e) => setBulletinSeverityFilter(e.target.value)}
                className="text-sm bg-transparent outline-none text-slate-700 font-medium cursor-pointer"
              >
                <option value="All">All Severities</option>
                {severities.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          </div>
        </div>

        <div className="p-0">
          {bulletinsLoading ? (
            <div className="p-6 space-y-4 animate-pulse">
              {[1, 2, 3].map(i => (
                <div key={i} className="h-16 bg-slate-100 rounded-lg"></div>
              ))}
            </div>
          ) : filteredBulletins.length === 0 ? (
            <div className="p-12 text-center text-slate-500">
              <ShieldCheck size={48} className="mx-auto text-emerald-200 mb-3" />
              <p>No security bulletins found for the selected filters.</p>
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {filteredBulletins.map(bulletin => (
                <div 
                  key={bulletin.id}
                  onClick={() => setSelectedBulletin(bulletin)}
                  className="flex items-center justify-between p-4 hover:bg-slate-50 cursor-pointer transition-colors group"
                >
                  <div className="flex items-center gap-4">
                    <div className="flex-shrink-0">
                      {bulletin.severity === 'Critical' && <div className="w-10 h-10 rounded-full bg-rose-100 flex items-center justify-center"><ShieldAlert size={20} className="text-rose-600" /></div>}
                      {bulletin.severity === 'High' && <div className="w-10 h-10 rounded-full bg-orange-100 flex items-center justify-center"><ShieldAlert size={20} className="text-orange-600" /></div>}
                      {bulletin.severity === 'Medium' && <div className="w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center"><ShieldAlert size={20} className="text-amber-600" /></div>}
                      {bulletin.severity === 'Low' && <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center"><Shield size={20} className="text-blue-600" /></div>}
                    </div>
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-semibold text-slate-900">{bulletin.tool}</span>
                        <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
                          {bulletin.cve_count} {bulletin.cve_count === 1 ? 'CVE' : 'CVEs'}
                        </span>
                        {bulletin.severity === 'Critical' && <span className="text-xs font-bold px-2 py-0.5 rounded border border-rose-200 bg-rose-50 text-rose-700">CRITICAL</span>}
                        {bulletin.severity === 'High' && <span className="text-xs font-bold px-2 py-0.5 rounded border border-orange-200 bg-orange-50 text-orange-700">HIGH</span>}
                      </div>
                      <div className="flex items-center gap-3 text-xs text-slate-500 font-medium">
                        <span className="flex items-center gap-1"><Calendar size={12} /> {new Date(bulletin.date).toLocaleString()}</span>
                        <span className="flex items-center gap-1 text-slate-400">•</span>
                        <span className={`flex items-center gap-1 ${bulletin.status === 'Sent' ? 'text-indigo-500' : 'text-emerald-500'}`}>
                          {bulletin.status === 'Sent' ? 'Status: Sent' : 'Status: Acknowledged'}
                        </span>
                      </div>
                    </div>
                  </div>
                  <ChevronRight size={20} className="text-slate-300 group-hover:text-indigo-500 transition-colors" />
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* ─── Technical Blog Feed ─────────────────────────────────────────────── */}
      <section className="card bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden mt-8">
        <div className="p-5 border-b border-slate-200 bg-slate-50/50 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <BookOpen size={18} className="text-indigo-500" />
            <h2 className="text-lg font-semibold text-slate-900">Technical Blog Feed</h2>
          </div>
          
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 bg-white border border-slate-200 rounded-lg px-3 py-1.5 shadow-sm">
              <Filter size={14} className="text-slate-400" />
              <select 
                value={blogToolFilter}
                onChange={(e) => setBlogToolFilter(e.target.value)}
                className="text-sm bg-transparent outline-none text-slate-700 font-medium cursor-pointer"
              >
                <option value="All">All Tools</option>
                {tools.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            
            <div className="flex items-center gap-2 bg-white border border-slate-200 rounded-lg px-3 py-1.5 shadow-sm">
              <TagIcon size={14} className="text-slate-400" />
              <select 
                value={blogTagFilter}
                onChange={(e) => setBlogTagFilter(e.target.value)}
                className="text-sm bg-transparent outline-none text-slate-700 font-medium cursor-pointer"
              >
                <option value="All">All Tags</option>
                {blogTags.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
          </div>
        </div>

        <div className="p-6">
          {blogsLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 animate-pulse">
              {[1, 2, 3, 4, 5, 6].map(i => (
                <div key={i} className="h-40 bg-slate-100 rounded-xl"></div>
              ))}
            </div>
          ) : blogs.length === 0 ? (
            <div className="p-12 text-center text-slate-500">
              <BookOpen size={48} className="mx-auto text-slate-200 mb-3" />
              <p>No articles found for the selected filters.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {blogs.map(blog => (
                <a 
                  key={blog.id} 
                  href={blog.url} 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="flex flex-col group border border-slate-200 rounded-xl overflow-hidden hover:shadow-md hover:border-indigo-300 transition-all bg-white"
                >
                  <div className="p-5 flex-1">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-xs font-bold text-indigo-600 bg-indigo-50 px-2.5 py-1 rounded-md uppercase tracking-wide">
                        {blog.tool}
                      </span>
                      <ExternalLink size={14} className="text-slate-300 group-hover:text-indigo-500" />
                    </div>
                    <h3 className="text-base font-bold text-slate-900 leading-tight mb-2 group-hover:text-indigo-600 transition-colors line-clamp-2">
                      {blog.title}
                    </h3>
                    <p className="text-sm text-slate-500 mb-4 flex items-center gap-2">
                      <span className="font-medium text-slate-700">{blog.source}</span>
                      <span>•</span>
                      <span>v{blog.version}</span>
                    </p>
                  </div>
                  <div className="px-5 py-3 bg-slate-50 border-t border-slate-100 flex flex-wrap items-center gap-2">
                    {blog.tags.map(tag => (
                      <span key={tag} className="text-[11px] font-medium text-slate-600 bg-white border border-slate-200 px-2 py-0.5 rounded-full shadow-sm">
                        {tag}
                      </span>
                    ))}
                  </div>
                </a>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* ─── Bulletin Detail Modal ──────────────────────────────────────────── */}
      {selectedBulletin && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl overflow-hidden flex flex-col max-h-[90vh]">
            <div className="p-6 border-b border-slate-100 flex items-center justify-between">
              <div>
                <h3 className="text-xl font-bold text-slate-900 mb-1">{selectedBulletin.id} details</h3>
                <p className="text-sm text-slate-500">Alert generated for {selectedBulletin.tool}</p>
              </div>
              <button 
                onClick={() => setSelectedBulletin(null)}
                className="p-2 rounded-full hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
              >
                <X size={20} />
              </button>
            </div>
            
            <div className="p-6 overflow-y-auto flex-1 bg-slate-50">
              <div className="space-y-4">
                {selectedBulletin.cves.map(cve => (
                  <div key={cve.id} className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
                    <div className="flex items-center justify-between mb-3">
                      <h4 className="text-base font-bold text-slate-900 flex items-center gap-2">
                        {cve.id}
                      </h4>
                      <span className={`px-2.5 py-1 rounded text-xs font-bold ${
                        cve.cvss >= 9.0 ? 'bg-rose-100 text-rose-700' :
                        cve.cvss >= 7.0 ? 'bg-orange-100 text-orange-700' :
                        cve.cvss >= 4.0 ? 'bg-amber-100 text-amber-700' : 'bg-blue-100 text-blue-700'
                      }`}>
                        CVSS {cve.cvss}
                      </span>
                    </div>
                    <p className="text-sm text-slate-600 leading-relaxed">
                      {cve.description}
                    </p>
                  </div>
                ))}
              </div>
            </div>
            
            <div className="p-5 border-t border-slate-100 bg-white flex justify-end">
              <button 
                onClick={() => setSelectedBulletin(null)}
                className="px-5 py-2 rounded-lg bg-slate-900 text-white text-sm font-medium hover:bg-slate-800 transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
