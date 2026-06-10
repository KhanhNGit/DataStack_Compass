import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import AppLayout from './components/Layout/AppLayout';
import Dashboard from './pages/Dashboard';
import TechCatalog from './pages/TechCatalog';
import ToolDetail from './pages/ToolDetail';
import AnalysisWorkspace from './pages/AnalysisWorkspace';
import GovernanceKnowledge from './pages/GovernanceKnowledge';

/* ─── React Query client ──────────────────────────────────────────────────── */
const queryClient = new QueryClient({
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
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<Dashboard />} />
            <Route path="catalog" element={<TechCatalog />} />
            <Route path="catalog/:toolName" element={<ToolDetail />} />
            <Route path="analysis" element={<AnalysisWorkspace />} />
            <Route path="governance" element={<GovernanceKnowledge />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
