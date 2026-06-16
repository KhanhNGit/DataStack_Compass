import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import AppLayout from './components/Layout/AppLayout';
import Dashboard from './pages/Dashboard';
import TechCatalog from './pages/TechCatalog';
import ToolDetail from './pages/ToolDetail';
import AnalysisWorkspace from './pages/AnalysisWorkspace';
import GovernanceKnowledge from './pages/GovernanceKnowledge';
import DependencyGraph from './pages/DependencyGraph';
import { ToastProvider } from './components/Toast/ToastProvider';

/* ─── React Query client ──────────────────────────────────────────────────── */
import { QueryCache } from '@tanstack/react-query';

const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error) => {
      // Dispatch a custom event to be picked up by a global toast listener
      // or directly show a toast if we had access to the toast function here.
      console.error(`Global Query Error: ${error.message}`);
      window.dispatchEvent(new CustomEvent('app-toast', { detail: { type: 'error', message: error.message } }));
    },
  }),
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,    // 5 minutes
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
});

/* ─── App ──────────────────────────────────────────────────────────────────── */
export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<AppLayout />}>
              <Route index element={<Dashboard />} />
              <Route path="catalog" element={<TechCatalog />} />
              <Route path="catalog/dependency-graph" element={<DependencyGraph />} />
              <Route path="catalog/:toolName" element={<ToolDetail />} />
              <Route path="analysis" element={<AnalysisWorkspace />} />
              <Route path="governance" element={<GovernanceKnowledge />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}
