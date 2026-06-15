import { useEffect, useRef, useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, RefreshCw, AlertTriangle, Network, Filter } from 'lucide-react';
import api from '../config/api';

declare const d3: any;

type NodeData = {
  id: string;
  version: string;
  lifecycle: string;
  cve_critical: number;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
};

type EdgeData = {
  from: string;
  to: string;
  version_required: string;
  type: string;
  source?: any;
  target?: any;
};

type GraphData = {
  nodes: NodeData[];
  edges: EdgeData[];
};

export default function DependencyGraph() {
  const navigate = useNavigate();
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const [lifecycleFilter, setLifecycleFilter] = useState<Record<string, boolean>>({
    Active: true,
    Maintenance: true,
    EOL: true,
  });
  const [showOnlyEOLAffected, setShowOnlyEOLAffected] = useState(false);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; node: NodeData } | null>(null);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['dependencyGraph'],
    queryFn: async () => {
      const res = await api.get('/api/v1/analysis/dependency-graph');
      return res.data.data as GraphData;
    },
    staleTime: 5 * 60 * 1000,
  });

  // Filter Logic
  const filteredData = useMemo(() => {
    if (!data) return { nodes: [], edges: [] };

    let nodes = data.nodes.filter(n => lifecycleFilter[n.lifecycle]);
    const validNodeIds = new Set(nodes.map(n => n.id));
    let edges = data.edges.filter(e => validNodeIds.has(e.from) && validNodeIds.has(e.to));

    if (showOnlyEOLAffected) {
      // Find EOL nodes
      const eolIds = new Set(nodes.filter(n => n.lifecycle === 'EOL').map(n => n.id));
      
      // We want to find nodes that depend on EOL nodes.
      // Dependency direction: `from` requires `to`.
      // If `to` is EOL, `from` is affected. We do a reverse BFS from EOL nodes.
      const reverseAdj: Record<string, string[]> = {};
      edges.forEach(e => {
        if (!reverseAdj[e.to]) reverseAdj[e.to] = [];
        reverseAdj[e.to].push(e.from);
      });

      const affected = new Set<string>(eolIds);
      const queue = Array.from(eolIds);
      
      while (queue.length > 0) {
        const curr = queue.shift()!;
        if (reverseAdj[curr]) {
          for (const parent of reverseAdj[curr]) {
            if (!affected.has(parent)) {
              affected.add(parent);
              queue.push(parent);
            }
          }
        }
      }

      nodes = nodes.filter(n => affected.has(n.id));
      const affectedIds = new Set(nodes.map(n => n.id));
      edges = edges.filter(e => affectedIds.has(e.from) && affectedIds.has(e.to));
    }

    return { nodes, edges };
  }, [data, lifecycleFilter, showOnlyEOLAffected]);

  // Render D3
  useEffect(() => {
    if (!svgRef.current || !containerRef.current || isLoading || filteredData.nodes.length === 0) return;

    const width = containerRef.current.clientWidth;
    const height = 500;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove(); // Clear previous

    svg.attr("viewBox", [0, 0, width, height]);

    // Zoom
    const zoom = d3.zoom()
      .scaleExtent([0.1, 4])
      .on("zoom", (event: any) => {
        g.attr("transform", event.transform);
      });
    svg.call(zoom);

    const g = svg.append("g");

    // Defs for arrow markers
    svg.append("defs").append("marker")
      .attr("id", "arrow")
      .attr("viewBox", "0 -5 10 10")
      .attr("refX", 25) // Offset to account for node radius
      .attr("refY", 0)
      .attr("markerWidth", 6)
      .attr("markerHeight", 6)
      .attr("orient", "auto")
      .append("path")
      .attr("fill", "#94a3b8")
      .attr("d", "M0,-5L10,0L0,5");

    // Copy data so D3 can mutate
    const nodes = filteredData.nodes.map(d => ({ ...d }));
    const links = filteredData.edges.map(d => ({ ...d, source: d.from, target: d.to }));

    const simulation = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(links).id((d: any) => d.id).distance(150))
      .force("charge", d3.forceManyBody().strength(-400))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide().radius((d: any) => Math.max(20, Math.min(50, 20 + d.cve_critical * 2)) + 10));

    // Links
    const link = g.append("g")
      .attr("stroke", "#cbd5e1")
      .attr("stroke-opacity", 0.6)
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke-width", 2)
      .attr("marker-end", "url(#arrow)");

    // Link Labels
    const linkLabel = g.append("g")
      .selectAll("text")
      .data(links)
      .join("text")
      .attr("font-size", "10px")
      .attr("fill", "#64748b")
      .attr("text-anchor", "middle")
      .attr("dy", -5)
      .text((d: any) => d.version_required);

    const getColor = (lifecycle: string) => {
      if (lifecycle === 'Active') return '#10b981'; // green-500
      if (lifecycle === 'Maintenance') return '#f59e0b'; // amber-500
      return '#ef4444'; // red-500
    };

    // Nodes
    const node = g.append("g")
      .selectAll("g")
      .data(nodes)
      .join("g")
      .attr("cursor", "pointer")
      .call(drag(simulation));

    const radius = (d: any) => Math.max(20, Math.min(50, 20 + d.cve_critical * 2));

    node.append("circle")
      .attr("r", radius)
      .attr("fill", (d: any) => getColor(d.lifecycle))
      .attr("stroke", "#fff")
      .attr("stroke-width", 2)
      .attr("class", "transition-all duration-200");

    // Node labels
    node.append("text")
      .attr("dy", (d: any) => radius(d) + 12)
      .attr("text-anchor", "middle")
      .attr("font-size", "12px")
      .attr("font-weight", "500")
      .attr("fill", "#334155")
      .text((d: any) => d.id);

    // Interactivity
    node.on("mouseover", (event: any, d: any) => {
      // Highlight neighborhood
      const connectedNodeIds = new Set<string>();
      connectedNodeIds.add(d.id);
      
      link.attr("stroke-opacity", (l: any) => {
        if (l.source.id === d.id || l.target.id === d.id) {
          connectedNodeIds.add(l.source.id);
          connectedNodeIds.add(l.target.id);
          return 1;
        }
        return 0.1;
      });

      linkLabel.attr("opacity", (l: any) => {
        return (l.source.id === d.id || l.target.id === d.id) ? 1 : 0.1;
      });

      node.attr("opacity", (n: any) => connectedNodeIds.has(n.id) ? 1 : 0.1);

      setTooltip({
        x: event.pageX,
        y: event.pageY,
        node: d
      });
    });

    node.on("mouseout", () => {
      link.attr("stroke-opacity", 0.6);
      linkLabel.attr("opacity", 1);
      node.attr("opacity", 1);
      setTooltip(null);
    });

    node.on("click", (event: any, d: any) => {
      if (event.defaultPrevented) return; // dragged
      navigate(`/catalog/${d.id}`);
    });

    simulation.on("tick", () => {
      link
        .attr("x1", (d: any) => d.source.x)
        .attr("y1", (d: any) => d.source.y)
        .attr("x2", (d: any) => d.target.x)
        .attr("y2", (d: any) => d.target.y);

      linkLabel
        .attr("x", (d: any) => (d.source.x + d.target.x) / 2)
        .attr("y", (d: any) => (d.source.y + d.target.y) / 2);

      node.attr("transform", (d: any) => `translate(${d.x},${d.y})`);
    });

    function drag(simulation: any) {
      function dragstarted(event: any) {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        event.subject.fx = event.subject.x;
        event.subject.fy = event.subject.y;
      }
      
      function dragged(event: any) {
        event.subject.fx = event.x;
        event.subject.fy = event.y;
      }
      
      function dragended(event: any) {
        if (!event.active) simulation.alphaTarget(0);
        event.subject.fx = null;
        event.subject.fy = null;
      }
      
      return d3.drag()
        .on("start", dragstarted)
        .on("drag", dragged)
        .on("end", dragended);
    }

    return () => {
      simulation.stop();
    };
  }, [filteredData, isLoading, navigate]);

  return (
    <div className="space-y-6">
      <nav className="flex items-center gap-1.5 text-sm text-slate-400">
        <Link to="/" className="hover:text-indigo-600 transition-colors">Dashboard</Link>
        <span>›</span>
        <Link to="/catalog" className="hover:text-indigo-600 transition-colors">Tech Catalog</Link>
        <span>›</span>
        <span className="text-slate-700 font-medium">Dependency Graph</span>
      </nav>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Network size={24} className="text-indigo-500" />
            Ecosystem Dependency Graph
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Visualize relationships and impact of EOL tools across the stack.
          </p>
        </div>
        <Link to="/catalog" className="inline-flex items-center gap-2 h-9 px-4 rounded-lg bg-white border border-slate-200 text-sm font-medium text-slate-700 hover:bg-slate-50">
          <ArrowLeft size={16} /> Back to Catalog
        </Link>
      </div>

      <div className="card p-4 flex flex-wrap items-center gap-6 bg-white border border-slate-200 rounded-xl shadow-sm">
        <div className="flex items-center gap-2">
          <Filter size={16} className="text-slate-400" />
          <span className="text-sm font-medium text-slate-700">Lifecycle:</span>
          {['Active', 'Maintenance', 'EOL'].map(status => (
            <label key={status} className="flex items-center gap-1.5 ml-2 text-sm text-slate-600 cursor-pointer">
              <input 
                type="checkbox" 
                checked={lifecycleFilter[status]} 
                onChange={(e) => setLifecycleFilter(prev => ({...prev, [status]: e.target.checked}))}
                className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
              />
              <span className="flex items-center gap-1">
                <span className={`w-2 h-2 rounded-full ${status === 'Active' ? 'bg-emerald-500' : status === 'Maintenance' ? 'bg-amber-500' : 'bg-red-500'}`}></span>
                {status}
              </span>
            </label>
          ))}
        </div>
        
        <div className="h-6 w-px bg-slate-200 hidden sm:block"></div>

        <label className="flex items-center gap-2 text-sm font-medium text-slate-700 cursor-pointer">
          <input 
            type="checkbox" 
            checked={showOnlyEOLAffected} 
            onChange={(e) => setShowOnlyEOLAffected(e.target.checked)}
            className="rounded border-slate-300 text-rose-600 focus:ring-rose-500"
          />
          <span className="text-rose-600 flex items-center gap-1.5">
            <AlertTriangle size={14} />
            Show only affected by EOL
          </span>
        </label>
      </div>

      <div className="card bg-slate-50/50 border border-slate-200 rounded-xl overflow-hidden relative" ref={containerRef}>
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/50 backdrop-blur-sm z-10">
            <RefreshCw size={24} className="text-indigo-500 animate-spin" />
          </div>
        )}
        {isError && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-white z-10 text-center">
            <AlertTriangle size={32} className="text-rose-500 mb-2" />
            <p className="text-slate-700 font-medium">Failed to load graph data</p>
            <button onClick={() => refetch()} className="mt-4 px-4 py-2 bg-slate-100 hover:bg-slate-200 rounded-lg text-sm font-medium text-slate-700 transition-colors">
              Retry
            </button>
          </div>
        )}
        {!isLoading && filteredData.nodes.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center bg-white z-10">
            <p className="text-slate-500 text-sm">No data matches the selected filters.</p>
          </div>
        )}
        
        <svg ref={svgRef} className="w-full h-[500px] cursor-move"></svg>

        {tooltip && (
          <div 
            className="absolute bg-slate-900 text-white text-xs rounded shadow-lg p-3 pointer-events-none z-50 transform -translate-x-1/2 -translate-y-full mt-[-10px]"
            style={{ left: tooltip.x, top: tooltip.y }}
          >
            <div className="font-bold mb-1 text-sm">{tooltip.node.id}</div>
            <div>Version: {tooltip.node.version}</div>
            <div>Status: <span className={tooltip.node.lifecycle === 'EOL' ? 'text-red-400' : tooltip.node.lifecycle === 'Maintenance' ? 'text-amber-400' : 'text-emerald-400'}>{tooltip.node.lifecycle}</span></div>
            {tooltip.node.cve_critical > 0 && <div className="text-rose-400 font-medium mt-1">{tooltip.node.cve_critical} Critical CVEs</div>}
          </div>
        )}
      </div>
    </div>
  );
}
