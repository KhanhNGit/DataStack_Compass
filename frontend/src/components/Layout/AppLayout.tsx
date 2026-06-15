import { useCallback, useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
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
  X,
  Loader2,
  Tag,
} from 'lucide-react';
import api from '../../config/api';
import { usePreferences } from '../../hooks/usePreferences';

/* ─── Navigation items ─────────────────────────────────────────────────────── */
const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/catalog', label: 'Tech Catalog', icon: Database },
  { to: '/analysis', label: 'Analysis Workspace', icon: GitCompareArrows },
  { to: '/governance', label: 'Governance & Knowledge', icon: Shield },
] as const;

/* ─── Debounce hook ────────────────────────────────────────────────────────── */
function useDebounce<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

export default function AppLayout() {
  const { preferences, updatePreference } = usePreferences();
  const [collapsed, setCollapsed] = useState(preferences.sidebarCollapsed);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const navigate = useNavigate();
  const searchRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    updatePreference('sidebarCollapsed', collapsed);
  }, [collapsed, updatePreference]);

  // Handle mobile resize
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth >= 1280 && collapsed) {
        // Desktop: expand by default unless user prefers collapsed
        // But since we use user preferences, we can leave it.
      } else if (window.innerWidth >= 768 && window.innerWidth < 1280) {
        setCollapsed(true);
      } else if (window.innerWidth < 768) {
        setMobileMenuOpen(false);
      }
    };
    window.addEventListener('resize', handleResize);
    handleResize(); // Init on mount
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const debouncedQuery = useDebounce(searchQuery.trim(), 300);

  // ── Search API call ───────────────────────────────────────────────────
  const { data: searchResults, isFetching: isSearching } = useQuery({
    queryKey: ['globalSearch', debouncedQuery],
    queryFn: async () => {
      if (!debouncedQuery) return [];
      const res = await api.get('/api/v1/search', {
        params: { q: debouncedQuery, type: 'all' },
      });
      return res.data?.data?.results ?? [];
    },
    enabled: debouncedQuery.length >= 1,
    staleTime: 30_000,
  });

  // Reset selected index when results change
  useEffect(() => {
    setSelectedIndex(-1);
  }, [searchResults]);

  // ── Show dropdown khi có results ──────────────────────────────────────
  useEffect(() => {
    setShowDropdown(
      debouncedQuery.length >= 1 &&
        Array.isArray(searchResults) &&
        searchResults.length > 0,
    );
  }, [debouncedQuery, searchResults]);

  // ── Click outside → close dropdown ────────────────────────────────────
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      setShowDropdown(false);
      navigate(`/catalog?search=${encodeURIComponent(searchQuery.trim())}`);
    }
  };

  const handleSelectResult = useCallback(
    (item: any) => {
      setSearchQuery('');
      setShowDropdown(false);
      setSelectedIndex(-1);
      if (item.result_type === 'tool') {
        navigate(`/catalog/${item.tool_name}`);
      } else if (item.result_type === 'cve') {
        navigate(`/catalog/${item.tool_name}?tab=cves&highlight=${item.cve_id}`);
      } else if (item.result_type === 'version') {
        navigate(`/catalog/${item.tool_name}?tab=versions&highlight=${item.version}`);
      }
    },
    [navigate],
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!showDropdown || !searchResults?.length) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev < searchResults.length - 1 ? prev + 1 : prev));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev > 0 ? prev - 1 : 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (selectedIndex >= 0 && selectedIndex < searchResults.length) {
        handleSelectResult(searchResults[selectedIndex]);
      } else {
        handleSearchSubmit(e as any);
      }
    } else if (e.key === 'Escape') {
      setShowDropdown(false);
    }
  };

  const sidebarWidth = collapsed ? 'w-16' : 'w-60';

  return (
    <div className="flex h-screen overflow-hidden">
      {/* ═══ Mobile Nav Overlay ═══ */}
      {mobileMenuOpen && (
        <div 
          className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40 lg:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* ═══ Sidebar ═══ */}
      <aside
        className={`
          fixed md:relative z-50 h-full flex flex-col flex-shrink-0
          transition-all duration-300 ease-in-out
          ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
          ${sidebarWidth}
        `}
        style={{ background: 'var(--sidebar-bg)' }}
      >
        {/* Mobile close button */}
        <button 
          onClick={() => setMobileMenuOpen(false)}
          className="md:hidden absolute top-4 right-[-40px] text-white p-2"
        >
          <X size={24} />
        </button>

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
              <Icon size={20} className="flex-shrink-0 transition-colors" />
              {!collapsed && <span className="truncate">{label}</span>}
            </NavLink>
          ))}
        </nav>

        </button>
      </aside>

      {/* ═══ Main area ═══ */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header
          className="flex items-center h-14 px-4 md:px-6 gap-3 md:gap-4 flex-shrink-0 border-b"
          style={{
            background: 'var(--header-bg)',
            borderColor: 'var(--header-border)',
          }}
        >
          {/* Mobile menu toggle */}
          <button
            className="md:hidden text-slate-500 hover:text-slate-700 p-1"
            onClick={() => setMobileMenuOpen(true)}
          >
            <Menu size={20} />
          </button>

          {/* Desktop collapse toggle */}
          <button
            className="hidden md:block text-slate-400 hover:text-slate-600 p-1 mr-2"
            onClick={() => setCollapsed(!collapsed)}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            <Menu size={20} />
          </button>

          {/* ── Global search with live dropdown ──────────────────────── */}
          <div ref={searchRef} className="relative flex-1 max-w-md">
            <form onSubmit={handleSearchSubmit}>
              <div className="relative">
                {isSearching ? (
                  <Loader2
                    size={16}
                    className="absolute left-3 top-1/2 -translate-y-1/2 text-indigo-500 animate-spin"
                  />
                ) : (
                  <Search
                    size={16}
                    className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                  />
                )}
                <input
                  type="text"
                  placeholder="Search tools, versions, CVEs..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onFocus={() => {
                    if (searchResults?.length) setShowDropdown(true);
                  }}
                  onKeyDown={handleKeyDown}
                  className="
                    w-full h-9 pl-9 pr-8 rounded-lg
                    bg-slate-50 border border-slate-200
                    text-sm text-slate-700 placeholder:text-slate-400
                    outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400
                    transition-all
                  "
                />
                {searchQuery && (
                  <button
                    type="button"
                    onClick={() => {
                      setSearchQuery('');
                      setShowDropdown(false);
                    }}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                  >
                    <X size={14} />
                  </button>
                )}
              </div>
            </form>

            {/* Dropdown results */}
            {showDropdown && (
              <div
                className="
                  absolute top-full left-0 right-0 mt-1.5 z-50
                  bg-white border border-slate-200 rounded-xl shadow-lg
                  max-h-[32rem] overflow-y-auto py-2
                "
              >
                {(searchResults ?? []).map((item: any, index: number) => {
                  const isSelected = index === selectedIndex;
                  const prevItem = index > 0 ? searchResults[index - 1] : null;
                  const showHeader = !prevItem || prevItem.result_type !== item.result_type;

                  let Icon = Database;
                  let headerText = 'Tools';
                  if (item.result_type === 'cve') {
                    Icon = Shield;
                    headerText = 'CVEs';
                  } else if (item.result_type === 'version') {
                    Icon = Tag;
                    headerText = 'Versions';
                  }

                  return (
                    <div key={`${item.result_type}-${item.display_title}`}>
                      {showHeader && (
                        <div className="px-4 py-1.5 mt-1 first:mt-0 bg-slate-50/80 sticky top-0 backdrop-blur-sm z-10 border-y border-slate-100 first:border-t-0">
                          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                            {headerText}
                          </span>
                        </div>
                      )}
                      <button
                        type="button"
                        onClick={() => handleSelectResult(item)}
                        className={`
                          w-full flex items-start gap-3 px-4 py-2.5 text-left transition-colors
                          ${isSelected ? 'bg-indigo-50/50' : 'hover:bg-slate-50'}
                        `}
                      >
                        <div className="mt-0.5 flex-shrink-0 text-slate-400">
                          <Icon size={16} className={item.result_type === 'cve' && (item.severity === 'Critical' || item.severity === 'High') ? 'text-red-400' : ''} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-slate-800 truncate">
                              {item.display_title}
                            </span>
                            {item.result_type === 'cve' && (
                              <span className={`
                                px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide
                                ${item.severity === 'Critical' ? 'bg-red-100 text-red-700' : 
                                  item.severity === 'High' ? 'bg-orange-100 text-orange-700' : 
                                  'bg-slate-100 text-slate-600'}
                              `}>
                                {item.severity}
                              </span>
                            )}
                          </div>
                          <div className="text-xs text-slate-500 truncate mt-0.5">
                            {item.display_subtitle}
                          </div>
                        </div>
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

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
              <span
                className="absolute top-2 right-2 pulse-dot"
                style={{ background: 'var(--danger)' }}
              />
            </button>
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
