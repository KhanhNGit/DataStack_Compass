import { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  Database,
  GitCompareArrows,
  Shield,
  Search,
  Bell,
  ChevronLeft,
  ChevronRight,
  Compass,
  Menu,
} from 'lucide-react';

/* ─── Navigation items ─────────────────────────────────────────────────────── */
const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/catalog', label: 'Tech Catalog', icon: Database },
  { to: '/analysis', label: 'Analysis Workspace', icon: GitCompareArrows },
  { to: '/governance', label: 'Governance & Knowledge', icon: Shield },
] as const;

/* ─── Component ────────────────────────────────────────────────────────────── */
export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const navigate = useNavigate();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      navigate(`/catalog?search=${encodeURIComponent(searchQuery.trim())}`);
    }
  };

  const sidebarWidth = collapsed ? 'w-16' : 'w-60';

  return (
    <div className="flex h-screen overflow-hidden">
      {/* ═══ Sidebar ═══ */}
      <aside
        className={`
          ${sidebarWidth} flex flex-col flex-shrink-0
          transition-all duration-300 ease-in-out
        `}
        style={{ background: 'var(--sidebar-bg)' }}
      >
        {/* Logo area */}
        <div className="flex items-center h-14 px-4 border-b border-white/5">
          <div className="flex items-center gap-2.5 overflow-hidden">
            <div className="flex-shrink-0 w-8 h-8 rounded-lg gradient-animated flex items-center justify-center">
              <Compass className="w-4.5 h-4.5 text-white" size={18} />
            </div>
            {!collapsed && (
              <span className="text-sm font-semibold text-slate-100 whitespace-nowrap truncate">
                DataStack Compass
              </span>
            )}
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium
                 transition-all duration-150 group
                 ${
                   isActive
                     ? 'text-white bg-white/10'
                     : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
                 }`
              }
            >
              <Icon
                size={20}
                className="flex-shrink-0 transition-colors"
              />
              {!collapsed && (
                <span className="truncate">{label}</span>
              )}
              {/* Active indicator */}
            </NavLink>
          ))}
        </nav>

        {/* Collapse toggle */}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="
            flex items-center justify-center h-10 mx-2 mb-3
            rounded-lg text-slate-500 hover:text-slate-300
            hover:bg-white/5 transition-all
          "
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </aside>

      {/* ═══ Main area ═══ */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header
          className="
            flex items-center h-14 px-6 gap-4 flex-shrink-0
            border-b
          "
          style={{
            background: 'var(--header-bg)',
            borderColor: 'var(--header-border)',
          }}
        >
          {/* Mobile menu toggle */}
          <button
            className="lg:hidden text-slate-500 hover:text-slate-700"
            onClick={() => setCollapsed(!collapsed)}
          >
            <Menu size={20} />
          </button>

          {/* Global search */}
          <form onSubmit={handleSearch} className="flex-1 max-w-md">
            <div className="relative">
              <Search
                size={16}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
              />
              <input
                type="text"
                placeholder="Search tools, versions, CVEs..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="
                  w-full h-9 pl-9 pr-4 rounded-lg
                  bg-slate-50 border border-slate-200
                  text-sm text-slate-700 placeholder:text-slate-400
                  outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400
                  transition-all
                "
              />
            </div>
          </form>

          {/* Right side */}
          <div className="flex items-center gap-3">
            <button
              className="
                relative w-9 h-9 rounded-lg flex items-center justify-center
                text-slate-500 hover:text-slate-700 hover:bg-slate-100
                transition-colors
              "
            >
              <Bell size={18} />
              {/* Notification dot */}
              <span
                className="absolute top-2 right-2 pulse-dot"
                style={{ background: 'var(--danger)' }}
              />
            </button>

            {/* User avatar */}
            <div
              className="
                w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600
                flex items-center justify-center text-white text-xs font-semibold
                cursor-pointer
              "
            >
              DC
            </div>
          </div>
        </header>

        {/* Content */}
        <main
          className="flex-1 overflow-y-auto p-6"
          style={{ background: 'var(--content-bg)' }}
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}
