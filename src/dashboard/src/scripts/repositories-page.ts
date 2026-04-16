import * as d3 from "d3";
import {
  addRepositoryBranch,
  deleteRepositoryBranchLink,
  deleteRepository,
  getRepositoryBranchLinks,
  getRepositoryBranches,
  getRepositoryGraphImpact,
  getRepositoryGraphMap,
  getRepositoryGraphSummary,
  getRepositoryLandscape,
  listRepositories,
  removeRepositoryBranch,
  searchRepositoryGraph,
  upsertRepositoryBranchLink,
  updateRepository,
  type RepositoryBranchLinkPayload,
  type RepositoryBranchListPayload,
  type RepositoryBranchPayload,
  type RepositoryGraphEdgePayload,
  type RepositoryGraphNodePayload,
  type RepositoryGraphSummaryPayload,
  type RepositoryLandscapePayload,
  type RepositoryPayload,
} from "../lib/api/admin";

// ============================================================
// Types
// ============================================================

/** D3 simulation node — must extend SimulationNodeDatum so D3 can track x/y/vx/vy/fx/fy */
interface SimNode extends d3.SimulationNodeDatum {
  id: string;
  label: string;
  type: string;
  radius: number;
  color: string;
  metadata: Record<string, unknown>;
  emphasis?: "hub" | "seed" | "result";
  score?: number;
  direction?: string;
  distance?: number;
}

/** D3 simulation edge — extends SimulationLinkDatum so D3 resolves source/target to objects */
interface SimEdge extends d3.SimulationLinkDatum<SimNode> {
  id: string;
  relation?: string;
  dashed?: boolean;
  edgeColor?: string;
}

// ============================================================
// Visual constants — GitNexus-inspired palette
// ============================================================

const NODE_COLORS: Record<string, string> = {
  repository: "#2dd4bf",
  folder: "#818cf8",
  file: "#60a5fa",
  module: "#c084fc",
  service: "#e879f9",
  controller: "#22d3ee",
  class: "#fbbf24",
  abstract_class: "#f59e0b",
  function: "#34d399",
  interface: "#fb7185",
  route: "#f87171",
  // v2 — new node types
  api_endpoint: "#fbbf24", // amber — HTTP endpoints
  websocket_endpoint: "#22d3ee", // cyan — WebSocket channels
  mq_topic: "#a78bfa", // violet — message topics
  mq_producer: "#f97316", // orange — message producers
  mq_consumer: "#4ade80", // green — message consumers
  todo: "#ef4444",
  external_service_api: "#e879f9",
  query: "#fb923c",
  target: "#f43f5e",
};

const NODE_RADII: Record<string, number> = {
  repository: 20,
  folder: 14,
  file: 9,
  module: 14,
  service: 16,
  controller: 11,
  class: 9,
  abstract_class: 9,
  function: 7,
  interface: 8,
  route: 7,
  // v2 — new node types
  api_endpoint: 10,
  websocket_endpoint: 10,
  mq_topic: 12,
  mq_producer: 8,
  mq_consumer: 8,
  todo: 6,
  external_service_api: 8,
  query: 12,
  target: 12,
};

const EDGE_STYLES: Record<
  string,
  { color: string; opacity: number; dashed?: boolean }
> = {
  contains: { color: "#818cf8", opacity: 0.28 },
  imports: { color: "#c084fc", opacity: 0.32 },
  calls: { color: "#22d3ee", opacity: 0.32 },
  defines: { color: "#2dd4bf", opacity: 0.32 },
  depends_on: { color: "#f87171", opacity: 0.38, dashed: true },
  upstream: { color: "#ef4444", opacity: 0.38, dashed: true },
  downstream: { color: "#38bdf8", opacity: 0.38, dashed: true },
  search_match: { color: "#fb923c", opacity: 0.38 },
};

function colorForType(t: string): string {
  return NODE_COLORS[t] ?? "#a8a29e";
}
function radiusForType(t: string): number {
  return NODE_RADII[t] ?? 7;
}

// ============================================================
// D3 Graph Renderer
// ============================================================

class D3GraphRenderer {
  private readonly container: HTMLElement;
  private readonly tooltipEl: HTMLElement;
  private svg!: d3.Selection<SVGSVGElement, unknown, null, undefined>;
  private g!: d3.Selection<SVGGElement, unknown, null, undefined>;
  private edgeGrp!: d3.Selection<SVGGElement, unknown, null, undefined>;
  private nodeGrp!: d3.Selection<SVGGElement, unknown, null, undefined>;
  private sim!: d3.Simulation<SimNode, SimEdge>;
  private zoom!: d3.ZoomBehavior<SVGSVGElement, unknown>;
  private nodes: SimNode[] = [];
  private edges: SimEdge[] = [];
  private selectedId: string | null = null;
  private ro: ResizeObserver;
  private onSelectCb: ((n: SimNode | null) => void) | null = null;
  private onSimCb: ((running: boolean) => void) | null = null;
  private simRunning = false;
  private readonly uid: string;

  constructor(container: HTMLElement, tooltipEl: HTMLElement) {
    this.container = container;
    this.tooltipEl = tooltipEl;
    this.uid = container.id || `g${Math.random().toString(36).slice(2, 8)}`;
    this.initSvg();
    this.initSim();
    this.ro = new ResizeObserver(() => this.onResize());
    this.ro.observe(container);
  }

  private w(): number {
    return Math.max(this.container.clientWidth, 400);
  }
  private h(): number {
    return Math.max(this.container.clientHeight, 300);
  }

  private initSvg(): void {
    this.svg = d3
      .select(this.container)
      .append("svg")
      .attr("width", "100%")
      .attr("height", "100%")
      .style("display", "block");

    const defs = this.svg.append("defs");

    // Glow filter for selected nodes
    const f = defs
      .append("filter")
      .attr("id", `glow-${this.uid}`)
      .attr("x", "-60%")
      .attr("y", "-60%")
      .attr("width", "220%")
      .attr("height", "220%");
    f.append("feGaussianBlur").attr("stdDeviation", "5").attr("result", "b1");
    f.append("feGaussianBlur").attr("stdDeviation", "2").attr("result", "b2");
    const m = f.append("feMerge");
    m.append("feMergeNode").attr("in", "b1");
    m.append("feMergeNode").attr("in", "b2");
    m.append("feMergeNode").attr("in", "SourceGraphic");

    // Arrow marker
    defs
      .append("marker")
      .attr("id", `arrow-${this.uid}`)
      .attr("viewBox", "0 -5 10 10")
      .attr("refX", 20)
      .attr("refY", 0)
      .attr("markerWidth", 5)
      .attr("markerHeight", 5)
      .attr("orient", "auto")
      .append("path")
      .attr("d", "M0,-5L10,0L0,5")
      .attr("fill", "rgba(148,163,184,0.35)");

    // Zoomable root group
    this.g = this.svg.append("g");
    this.edgeGrp = this.g.append("g").attr("class", "edges");
    this.nodeGrp = this.g.append("g").attr("class", "nodes");

    // Zoom behavior
    this.zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.02, 12])
      .on("zoom", (e: d3.D3ZoomEvent<SVGSVGElement, unknown>) => {
        this.g.attr("transform", String(e.transform));
      });
    this.svg.call(this.zoom);

    // Deselect on stage click
    this.svg.on("click.deselect", (e: MouseEvent) => {
      const tag = (e.target as Element).tagName;
      if (tag === "svg" || tag === "rect") this.select(null);
    });
  }

  private initSim(): void {
    this.sim = d3
      .forceSimulation<SimNode>()
      .force(
        "charge",
        d3.forceManyBody<SimNode>().strength((d) => -(d.radius * 25)),
      )
      .force(
        "collide",
        d3
          .forceCollide<SimNode>()
          .radius((d) => d.radius + 10)
          .strength(0.9),
      )
      .alphaDecay(0.025)
      .velocityDecay(0.45)
      .on("tick", () => this.tick())
      .on("end", () => {
        this.simRunning = false;
        this.onSimCb?.(false);
      });
  }

  private onResize(): void {
    if (!this.nodes.length) return;
    const w = this.w(),
      h = this.h();
    this.sim
      .force("center", d3.forceCenter<SimNode>(w / 2, h / 2).strength(0.08))
      .alpha(0.1)
      .restart();
  }

  private tick(): void {
    if (!this.simRunning) {
      this.simRunning = true;
      this.onSimCb?.(true);
    }
    this.edgeGrp
      .selectAll<SVGLineElement, SimEdge>("line")
      .attr("x1", (d) => (d.source as SimNode).x ?? 0)
      .attr("y1", (d) => (d.source as SimNode).y ?? 0)
      .attr("x2", (d) => (d.target as SimNode).x ?? 0)
      .attr("y2", (d) => (d.target as SimNode).y ?? 0);

    this.nodeGrp
      .selectAll<SVGGElement, SimNode>("g.node")
      .attr("transform", (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
  }

  onSelect(fn: (n: SimNode | null) => void): void {
    this.onSelectCb = fn;
  }
  onSimStatus(fn: (running: boolean) => void): void {
    this.onSimCb = fn;
  }

  private select(nodeId: string | null): void {
    this.selectedId = nodeId;
    this.applyHighlights();
    const n = nodeId ? (this.nodes.find((d) => d.id === nodeId) ?? null) : null;
    this.onSelectCb?.(n);
  }

  private neighborIds(nodeId: string): Set<string> {
    const s = new Set<string>();
    for (const e of this.edges) {
      const src =
        typeof e.source === "object"
          ? (e.source as SimNode).id
          : String(e.source);
      const tgt =
        typeof e.target === "object"
          ? (e.target as SimNode).id
          : String(e.target);
      if (src === nodeId) s.add(tgt);
      if (tgt === nodeId) s.add(src);
    }
    return s;
  }

  private applyHighlights(): void {
    const sel = this.selectedId;
    const nb = sel ? this.neighborIds(sel) : new Set<string>();
    const glowId = `glow-${this.uid}`;

    this.nodeGrp.selectAll<SVGGElement, SimNode>("g.node").each(function (d) {
      const g = d3.select<SVGGElement, SimNode>(this);
      const circle = g.select<SVGCircleElement>("circle");
      const text = g.select<SVGTextElement>("text");

      if (!sel) {
        circle.attr("opacity", 0.87).attr("stroke", null).attr("filter", null);
        text.attr("opacity", 0.78);
      } else if (d.id === sel) {
        circle
          .attr("opacity", 1)
          .attr("stroke", d.color)
          .attr("stroke-width", 2.5)
          .attr("stroke-opacity", 0.9)
          .attr("filter", `url(#${glowId})`);
        text.attr("opacity", 1).attr("font-weight", "700");
      } else if (nb.has(d.id)) {
        circle.attr("opacity", 0.82).attr("stroke", null).attr("filter", null);
        text.attr("opacity", 0.72);
      } else {
        circle.attr("opacity", 0.1).attr("stroke", null).attr("filter", null);
        text.attr("opacity", 0.06);
      }
    });

    this.edgeGrp.selectAll<SVGLineElement, SimEdge>("line").each(function (d) {
      const src =
        typeof d.source === "object"
          ? (d.source as SimNode).id
          : String(d.source);
      const tgt =
        typeof d.target === "object"
          ? (d.target as SimNode).id
          : String(d.target);

      if (!sel) {
        d3.select(this).attr("opacity", 1);
      } else if (src === sel || tgt === sel) {
        d3.select(this).attr("opacity", 0.9);
      } else {
        d3.select(this).attr("opacity", 0.04);
      }
    });
  }

  render(nodes: SimNode[], edges: SimEdge[]): void {
    this.nodes = nodes;
    this.edges = edges;
    this.selectedId = null;

    const w = this.w(),
      h = this.h();

    // Scatter initial positions around centre
    for (const n of nodes) {
      if (n.x === undefined || n.y === undefined) {
        const angle = Math.random() * Math.PI * 2;
        const r = Math.random() * Math.min(w, h) * 0.3;
        n.x = w / 2 + Math.cos(angle) * r;
        n.y = h / 2 + Math.sin(angle) * r;
      }
    }

    // ── Edges ──────────────────────────────────────
    const eSel = this.edgeGrp
      .selectAll<SVGLineElement, SimEdge>("line")
      .data(edges, (d) => d.id);

    eSel.exit().remove();

    const eAll = eSel.enter().append("line").merge(eSel);

    eAll
      .attr("stroke", (d) => {
        const s = EDGE_STYLES[d.relation ?? ""];
        return d.edgeColor ?? s?.color ?? "rgba(148,163,184,0.22)";
      })
      .attr("stroke-width", 1.4)
      .attr(
        "stroke-opacity",
        (d) => EDGE_STYLES[d.relation ?? ""]?.opacity ?? 0.22,
      )
      .attr("stroke-dasharray", (d) => {
        const s = EDGE_STYLES[d.relation ?? ""];
        return (d.dashed ?? s?.dashed) ? "6,4" : null;
      })
      .attr("marker-end", `url(#arrow-${this.uid})`);

    // ── Nodes ──────────────────────────────────────
    const nSel = this.nodeGrp
      .selectAll<SVGGElement, SimNode>("g.node")
      .data(nodes, (d) => d.id);

    nSel.exit().remove();

    const self = this;
    const drag = d3
      .drag<SVGGElement, SimNode>()
      .on(
        "start",
        function (
          e: d3.D3DragEvent<SVGGElement, SimNode, SimNode>,
          d: SimNode,
        ) {
          if (!e.active) self.sim.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        },
      )
      .on(
        "drag",
        function (
          e: d3.D3DragEvent<SVGGElement, SimNode, SimNode>,
          d: SimNode,
        ) {
          d.fx = e.x;
          d.fy = e.y;
        },
      )
      .on(
        "end",
        function (
          e: d3.D3DragEvent<SVGGElement, SimNode, SimNode>,
          d: SimNode,
        ) {
          if (!e.active) self.sim.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        },
      );

    const nEnter = nSel
      .enter()
      .append("g")
      .attr("class", "node")
      .style("cursor", "pointer")
      .call(drag);

    // Entrance animation: circles grow from zero
    nEnter
      .append("circle")
      .attr("r", 0)
      .transition()
      .duration(350)
      .ease(d3.easeCubicOut)
      .attr("r", (d) => d.radius);

    nEnter
      .append("text")
      .attr("text-anchor", "middle")
      .attr("fill", "#e2e8f0")
      .attr("font-family", "ui-monospace, 'JetBrains Mono', monospace")
      .attr("pointer-events", "none")
      .attr("opacity", 0)
      .transition()
      .delay(200)
      .duration(350)
      .attr("opacity", 0.78);

    const nAll = nEnter.merge(nSel);

    // Apply current attributes
    nAll
      .select<SVGCircleElement>("circle")
      .attr("r", (d) => d.radius)
      .attr("fill", (d) => d.color)
      .attr("fill-opacity", 0.82);

    nAll
      .select<SVGTextElement>("text")
      .attr("font-size", (d) =>
        d.type === "repository" ? 12 : d.type === "folder" ? 10 : 9,
      )
      .attr("dy", (d) => d.radius + 13)
      .attr("opacity", 0.78)
      .text((d) => {
        const max =
          d.type === "repository" ? 22 : d.type === "folder" ? 18 : 14;
        return d.label.length > max ? `${d.label.slice(0, max - 1)}…` : d.label;
      });

    // Events
    nAll
      .on("mouseenter.tooltip", (e: MouseEvent, d) => {
        const rect = self.container.getBoundingClientRect();
        self.tooltipEl.textContent = `${d.type}: ${d.label}`;
        self.tooltipEl.style.opacity = "1";
        self.tooltipEl.style.left = `${e.clientX - rect.left + 14}px`;
        self.tooltipEl.style.top = `${e.clientY - rect.top - 10}px`;
      })
      .on("mousemove.tooltip", (e: MouseEvent) => {
        const rect = self.container.getBoundingClientRect();
        self.tooltipEl.style.left = `${e.clientX - rect.left + 14}px`;
        self.tooltipEl.style.top = `${e.clientY - rect.top - 10}px`;
      })
      .on("mouseleave.tooltip", () => {
        self.tooltipEl.style.opacity = "0";
      })
      .on("click.select", (e: MouseEvent, d) => {
        e.stopPropagation();
        self.select(self.selectedId === d.id ? null : d.id);
      });

    // Start force simulation
    this.sim
      .nodes(nodes)
      .force(
        "link",
        d3
          .forceLink<SimNode, SimEdge>(edges)
          .id((d) => d.id)
          .distance((d) => {
            const rel = (d as SimEdge).relation;
            if (rel === "contains") return 60;
            if (rel === "imports" || rel === "calls") return 100;
            return 85;
          })
          .strength(0.4),
      )
      .force("center", d3.forceCenter<SimNode>(w / 2, h / 2).strength(0.08))
      .alpha(0.9)
      .restart();

    this.simRunning = true;
    this.onSimCb?.(true);

    // Auto-fit after layout converges
    setTimeout(() => this.fitToScreen(), 3200);
  }

  clearGraph(): void {
    this.nodes = [];
    this.edges = [];
    this.selectedId = null;
    this.sim.nodes([]);
    this.edgeGrp.selectAll("*").remove();
    this.nodeGrp.selectAll("*").remove();
    this.onSelectCb?.(null);
  }

  zoomIn(): void {
    this.svg.transition().duration(220).call(this.zoom.scaleBy, 1.5);
  }

  zoomOut(): void {
    this.svg
      .transition()
      .duration(220)
      .call(this.zoom.scaleBy, 1 / 1.5);
  }

  fitToScreen(): void {
    if (!this.nodes.length) return;
    const w = this.w(),
      h = this.h(),
      pad = 64;
    const xs = this.nodes.map((d) => d.x ?? 0);
    const ys = this.nodes.map((d) => d.y ?? 0);
    const x0 = Math.min(...xs),
      x1 = Math.max(...xs);
    const y0 = Math.min(...ys),
      y1 = Math.max(...ys);
    const gw = x1 - x0 || 1,
      gh = y1 - y0 || 1;
    const scale = Math.min((w - pad * 2) / gw, (h - pad * 2) / gh, 3);
    const tx = w / 2 - scale * (x0 + gw / 2);
    const ty = h / 2 - scale * (y0 + gh / 2);
    this.svg
      .transition()
      .duration(600)
      .call(
        this.zoom.transform,
        d3.zoomIdentity.translate(tx, ty).scale(scale),
      );
  }

  toggleLayout(): boolean {
    if (this.simRunning) {
      this.sim.stop();
      this.simRunning = false;
      this.onSimCb?.(false);
      return false;
    } else {
      this.sim.alpha(0.5).restart();
      return true;
    }
  }

  destroy(): void {
    this.ro.disconnect();
    this.sim.stop();
    this.svg.remove();
  }
}

// ============================================================
// Graph data builders
// ============================================================

function escapeHtml(v: string): string {
  return v
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function meta(m: Record<string, unknown>, key: string): string | null {
  const v = m[key];
  return typeof v === "string" && v.trim() ? v.trim() : null;
}

function folderAncestors(paths: string[]): string[] {
  const s = new Set<string>();
  for (const p of paths) {
    const segs = p.split("/").filter(Boolean);
    for (let i = 1; i < segs.length; i++) s.add(segs.slice(0, i).join("/"));
  }
  return [...s].sort((a, b) => a.localeCompare(b));
}

type ExtendedNodePayload = RepositoryGraphNodePayload & {
  score?: number;
  direction?: string;
  distance?: number;
  emphasis?: "seed" | "result";
};

interface BuildResult {
  nodes: SimNode[];
  edges: SimEdge[];
}

function buildGraphData(
  repoName: string,
  apiNodes: ExtendedNodePayload[],
  apiEdges: Array<
    | RepositoryGraphEdgePayload
    | {
        id: string;
        from: string;
        to: string;
        relation?: string;
        dashed?: boolean;
        color?: string;
      }
  >,
  _emptyMsg = "",
): BuildResult {
  const nodeMap = new Map<string, SimNode>();
  const edgeMap = new Map<string, SimEdge>();

  // Repository root
  nodeMap.set("repository-root", {
    id: "repository-root",
    label: repoName,
    type: "repository",
    radius: radiusForType("repository"),
    color: colorForType("repository"),
    metadata: {},
    emphasis: "hub",
  });

  const paths = apiNodes
    .map((n) => meta(n.metadata, "path"))
    .filter((v): v is string => Boolean(v));

  // Folder hierarchy
  for (const fp of folderAncestors(paths)) {
    const segs = fp.split("/").filter(Boolean);
    const fid = `folder:${fp}`;
    const pid =
      segs.length > 1
        ? `folder:${segs.slice(0, -1).join("/")}`
        : "repository-root";
    nodeMap.set(fid, {
      id: fid,
      label: segs[segs.length - 1] ?? fp,
      type: "folder",
      radius: radiusForType("folder"),
      color: colorForType("folder"),
      metadata: { path: fp },
    });
    edgeMap.set(`contains:${pid}:${fid}`, {
      id: `contains:${pid}:${fid}`,
      source: pid,
      target: fid,
      relation: "contains",
    });
  }

  // File nodes from paths where no explicit file node exists
  const fileNodesByPath = new Map<string, string>();
  for (const n of apiNodes) {
    const p = meta(n.metadata, "path");
    if (n.node_type === "file" && p) fileNodesByPath.set(p, n.id);
  }

  for (const p of paths) {
    if (fileNodesByPath.has(p)) continue;
    const segs = p.split("/").filter(Boolean);
    const fid = `file:${p}`;
    const pid =
      segs.length > 1
        ? `folder:${segs.slice(0, -1).join("/")}`
        : "repository-root";
    nodeMap.set(fid, {
      id: fid,
      label: segs[segs.length - 1] ?? p,
      type: "file",
      radius: radiusForType("file"),
      color: colorForType("file"),
      metadata: { path: p },
    });
    edgeMap.set(`contains:${pid}:${fid}`, {
      id: `contains:${pid}:${fid}`,
      source: pid,
      target: fid,
      relation: "contains",
    });
  }

  // API nodes
  for (const n of apiNodes) {
    nodeMap.set(n.id, {
      id: n.id,
      label: n.name,
      type: n.node_type,
      radius: radiusForType(n.node_type),
      color: colorForType(n.node_type),
      metadata: n.metadata,
      emphasis: n.emphasis,
      score: n.score,
      direction: n.direction,
      distance: n.distance,
    });

    const p = meta(n.metadata, "path");
    if (p) {
      const parentId =
        n.node_type === "file"
          ? p.includes("/")
            ? `folder:${p.split("/").slice(0, -1).join("/")}`
            : "repository-root"
          : (fileNodesByPath.get(p) ?? `file:${p}`);
      if (nodeMap.has(parentId)) {
        edgeMap.set(`contains:${parentId}:${n.id}`, {
          id: `contains:${parentId}:${n.id}`,
          source: parentId,
          target: n.id,
          relation: "contains",
        });
      }
    }
  }

  // API edges
  for (const e of apiEdges) {
    let id: string,
      from: string,
      to: string,
      relation: string | undefined,
      dashed: boolean | undefined,
      edgeColor: string | undefined;

    if ("source_id" in e) {
      id = e.id;
      from = e.source_id;
      to = e.target_id;
      relation = e.relation;
    } else {
      id = e.id;
      from = e.from;
      to = e.to;
      relation = e.relation;
      dashed = e.dashed;
      edgeColor = e.color;
    }

    if (nodeMap.has(from) && nodeMap.has(to)) {
      edgeMap.set(id, {
        id,
        source: from,
        target: to,
        relation,
        dashed,
        edgeColor,
      });
    }
  }

  return {
    nodes: [...nodeMap.values()],
    edges: [...edgeMap.values()],
  };
}

// ============================================================
// DOM helpers
// ============================================================

function setText(el: Element | null, text: string): void {
  if (el) el.textContent = text;
}

function splitCsv(v: string | null | undefined): string[] {
  return (v ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function lastSyncLabel(s: RepositoryGraphSummaryPayload): string {
  const ls = s.last_sync;
  if (!ls || typeof ls.accepted_at !== "string")
    return s.graph_available ? "Graph Ready" : "No Sync";
  const d = new Date(ls.accepted_at);
  return Number.isNaN(d.getTime())
    ? "Graph Ready"
    : `Synced ${d.toLocaleString()}`;
}

// ============================================================
// Tab management + full-width graph mode
// ============================================================

const sidebar = document.getElementById("repo-sidebar");
const layoutGrid = document.getElementById("main-layout-grid");

function setGraphFullWidth(enabled: boolean): void {
  if (enabled) {
    // Hide sidebar → canvas takes full container width
    sidebar?.style.setProperty("display", "none");
    // Switch grid to single column
    if (layoutGrid) layoutGrid.style.gridTemplateColumns = "1fr";
    // Tell CSS to expand the canvas height to viewport-relative
    document.body.classList.add("graph-fullwidth");
  } else {
    sidebar?.style.removeProperty("display");
    if (layoutGrid) layoutGrid.style.gridTemplateColumns = "";
    document.body.classList.remove("graph-fullwidth");
  }
}

function switchTab(tabId: string): void {
  document.querySelectorAll("[data-tab-btn]").forEach((b) => {
    b.classList.remove("tab-btn-active");
  });
  document.querySelectorAll("[data-tab-panel]").forEach((p) => {
    p.classList.add("hidden");
  });
  document
    .querySelector(`[data-tab-btn="${tabId}"]`)
    ?.classList.add("tab-btn-active");
  document
    .querySelector(`[data-tab-panel="${tabId}"]`)
    ?.classList.remove("hidden");

  // Graph tab → full width + expand canvas height; other tabs → restore sidebar
  if (tabId === "graph") {
    setGraphFullWidth(true);
    // Give layout time to reflow before re-fitting
    setTimeout(() => repoRenderer?.fitToScreen(), 100);
  } else {
    setGraphFullWidth(false);
    if (tabId === "search" && searchRenderer)
      setTimeout(() => searchRenderer?.fitToScreen(), 50);
    if (tabId === "impact" && impactRenderer)
      setTimeout(() => impactRenderer?.fitToScreen(), 50);
    // Settings tab: load tracked branches and branch links from API
    if (tabId === "settings") {
      void loadTrackedBranches();
      void loadBranchLinks();
    }
  }
}

document
  .querySelector("#repo-tab-nav")
  ?.addEventListener("click", (e: Event) => {
    const btn = (e.target as Element).closest("[data-tab-btn]");
    if (btn) switchTab(btn.getAttribute("data-tab-btn") ?? "graph");
  });

// ============================================================
// Renderer instances
// ============================================================

function getEl<T extends HTMLElement>(id: string): T | null {
  return document.getElementById(id) as T | null;
}

let repoRenderer: D3GraphRenderer | null = null;
let searchRenderer: D3GraphRenderer | null = null;
let impactRenderer: D3GraphRenderer | null = null;

function initRepoRenderer(): D3GraphRenderer | null {
  if (repoRenderer) return repoRenderer;
  const mount = getEl("repo-graph-mount");
  const tip = getEl("repo-graph-tooltip");
  if (!mount || !tip) return null;
  repoRenderer = new D3GraphRenderer(mount, tip);
  repoRenderer.onSelect(showRepoNodeDetails);
  repoRenderer.onSimStatus((running) => {
    const el = getEl("repo-graph-sim-status");
    if (!el) return;
    if (running) (el.classList.remove("hidden"), el.classList.add("flex"));
    else (el.classList.add("hidden"), el.classList.remove("flex"));
    // Update toggle icon
    const icon = getEl("repo-graph-toggle-icon");
    if (icon) {
      icon.innerHTML = running
        ? `<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>` // pause
        : `<polygon points="5,3 19,12 5,21"/>`; // play
    }
  });
  return repoRenderer;
}

function initSearchRenderer(): D3GraphRenderer | null {
  if (searchRenderer) return searchRenderer;
  const mount = getEl("search-graph-mount");
  const tip = getEl("search-graph-tooltip");
  if (!mount || !tip) return null;
  searchRenderer = new D3GraphRenderer(mount, tip);
  searchRenderer.onSelect(showSearchNodeDetails);
  return searchRenderer;
}

function initImpactRenderer(): D3GraphRenderer | null {
  if (impactRenderer) return impactRenderer;
  const mount = getEl("impact-graph-mount");
  const tip = getEl("impact-graph-tooltip");
  if (!mount || !tip) return null;
  impactRenderer = new D3GraphRenderer(mount, tip);
  impactRenderer.onSelect(showImpactNodeDetails);
  return impactRenderer;
}

// ============================================================
// Legend renderer
// ============================================================

function renderLegendOverlay(legendId: string, nodes: SimNode[]): void {
  const el = getEl(legendId);
  if (!el) return;
  const counts = new Map<string, number>();
  for (const n of nodes) counts.set(n.type, (counts.get(n.type) ?? 0) + 1);
  if (!counts.size) {
    el.innerHTML = "";
    return;
  }

  el.innerHTML = [...counts.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(
      ([type, count]) => `
      <div style="display:flex; align-items:center; justify-content:space-between; gap:8px; padding: 1px 0;">
        <span style="display:flex; align-items:center; gap:5px;">
          <span style="width:8px; height:8px; border-radius:50%; background:${escapeHtml(colorForType(type))}; flex-shrink:0;"></span>
          <span style="font-size:10px; color:rgba(226,232,240,0.65); font-family: ui-monospace, monospace;">${escapeHtml(type)}</span>
        </span>
        <span style="font-size:10px; font-weight:600; color:rgba(226,232,240,0.9); font-family: ui-monospace, monospace;">${count}</span>
      </div>
    `,
    )
    .join("");
}

// ============================================================
// Node details panel
// ============================================================

function showNodeDetails(
  typeId: string,
  nameId: string,
  extraId: string,
  metaId: string,
  panelId: string,
  node: SimNode | null,
): void {
  const panel = getEl(panelId);
  if (!panel) return;
  if (!node) {
    panel.classList.add("hidden");
    return;
  }
  panel.classList.remove("hidden");

  setText(getEl(typeId), node.type);
  setText(getEl(nameId), node.label);
  const extraParts: string[] = [];
  if (node.score != null) extraParts.push(`Score ${node.score}`);
  if (node.direction)
    extraParts.push(`${node.direction} · distance ${node.distance ?? 1}`);
  if (node.emphasis) extraParts.push(`Emphasis: ${node.emphasis}`);
  setText(getEl(extraId), extraParts.join("  ·  "));

  const metaEl = getEl(metaId);
  if (!metaEl) return;
  const rows = Object.entries(node.metadata)
    .filter(([, v]) => v != null && v !== "")
    .slice(0, 12)
    .map(
      ([k, v]) => `
      <div class="grid gap-0.5 border border-stone-100 rounded-xl p-3">
        <span class="text-[10px] font-bold uppercase tracking-widest text-stone-400">${escapeHtml(k)}</span>
        <span class="text-sm text-stone-800 break-all">${escapeHtml(String(v))}</span>
      </div>
    `,
    )
    .join("");
  metaEl.innerHTML =
    rows || `<p class="text-sm text-stone-400 col-span-full">No metadata.</p>`;
}

function showRepoNodeDetails(n: SimNode | null): void {
  showNodeDetails(
    "repo-graph-node-type",
    "repo-graph-node-name",
    "repo-graph-node-extra",
    "repo-graph-node-metadata",
    "repo-graph-node-details",
    n,
  );
}
function showSearchNodeDetails(n: SimNode | null): void {
  showNodeDetails(
    "search-graph-node-type",
    "search-graph-node-name",
    "search-graph-node-extra",
    "search-graph-node-metadata",
    "search-graph-node-details",
    n,
  );
}
function showImpactNodeDetails(n: SimNode | null): void {
  showNodeDetails(
    "impact-graph-node-type",
    "impact-graph-node-name",
    "impact-graph-node-extra",
    "impact-graph-node-metadata",
    "impact-graph-node-details",
    n,
  );
}

// Close buttons
getEl("repo-graph-node-close")?.addEventListener("click", () => {
  showRepoNodeDetails(null);
});
getEl("search-graph-node-close")?.addEventListener("click", () => {
  showSearchNodeDetails(null);
});
getEl("impact-graph-node-close")?.addEventListener("click", () => {
  showImpactNodeDetails(null);
});

// ============================================================
// Graph controls
// ============================================================

getEl("repo-graph-zoom-in")?.addEventListener("click", () =>
  repoRenderer?.zoomIn(),
);
getEl("repo-graph-zoom-out")?.addEventListener("click", () =>
  repoRenderer?.zoomOut(),
);
getEl("repo-graph-fit")?.addEventListener("click", () =>
  repoRenderer?.fitToScreen(),
);
getEl("repo-graph-toggle")?.addEventListener("click", () =>
  repoRenderer?.toggleLayout(),
);

// ── Fullscreen button ──────────────────────────────────────
const FS_ICON_EXPAND = `<path d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3"/>`;
const FS_ICON_SHRINK = `<path d="M8 3v3a2 2 0 01-2 2H3m18 0h-3a2 2 0 01-2-2V3m0 18v-3a2 2 0 012-2h3M3 16h3a2 2 0 012 2v3"/>`;

function updateFsIcon(isFs: boolean): void {
  const icon = getEl("repo-graph-fs-icon");
  if (icon) icon.innerHTML = isFs ? FS_ICON_SHRINK : FS_ICON_EXPAND;
}

getEl("repo-graph-fullscreen")?.addEventListener("click", () => {
  const wrap = getEl("repo-graph-wrap");
  if (!wrap) return;

  if (!document.fullscreenElement) {
    wrap
      .requestFullscreen()
      .then(() => {
        updateFsIcon(true);
        // Refit after fullscreen transition
        setTimeout(() => repoRenderer?.fitToScreen(), 120);
      })
      .catch(() => {
        /* fullscreen not supported */
      });
  } else {
    document.exitFullscreen().then(() => {
      updateFsIcon(false);
      setTimeout(() => repoRenderer?.fitToScreen(), 120);
    });
  }
});

// Sync icon when user exits fullscreen via Esc
document.addEventListener("fullscreenchange", () => {
  if (!document.fullscreenElement) {
    updateFsIcon(false);
    setTimeout(() => repoRenderer?.fitToScreen(), 120);
  }
});

getEl("search-graph-zoom-in")?.addEventListener("click", () =>
  searchRenderer?.zoomIn(),
);
getEl("search-graph-zoom-out")?.addEventListener("click", () =>
  searchRenderer?.zoomOut(),
);
getEl("search-graph-fit")?.addEventListener("click", () =>
  searchRenderer?.fitToScreen(),
);

getEl("impact-graph-zoom-in")?.addEventListener("click", () =>
  impactRenderer?.zoomIn(),
);
getEl("impact-graph-zoom-out")?.addEventListener("click", () =>
  impactRenderer?.zoomOut(),
);
getEl("impact-graph-fit")?.addEventListener("click", () =>
  impactRenderer?.fitToScreen(),
);

// ============================================================
// Summary renderers
// ============================================================

function renderSummary(s: RepositoryGraphSummaryPayload): void {
  setText(getEl("repo-summary-title"), s.repository.name);
  const branchLabel = s.active_branch ? ` · ${s.active_branch}` : "";
  setText(
    getEl("repo-summary-meta"),
    `${s.repository.remote_url ?? "No remote"} · ${s.repository.default_branch ?? "No branch"}${branchLabel}`,
  );
  setText(getEl("repo-summary-sync"), lastSyncLabel(s));

  const cards = getEl("repo-summary-cards");
  if (cards) {
    cards.innerHTML = [
      ["Nodes", String(s.node_count)],
      ["Types", String(Object.keys(s.counts_by_type).length)],
      ["Routes", String(s.routes.length)],
      ["TODOs", String(s.todos.length)],
    ]
      .map(
        ([label, value]) => `
      <article class="rounded-3xl border border-stone-200 bg-stone-50 px-5 py-4">
        <p class="text-xs font-semibold uppercase tracking-[0.22em] text-stone-500">${escapeHtml(label)}</p>
        <p class="mt-3 text-3xl font-semibold text-stone-950">${escapeHtml(value)}</p>
      </article>
    `,
      )
      .join("");
  }

  renderNodeCollection(getEl("repo-routes"), s.routes, "No route nodes.");
  renderNodeCollection(getEl("repo-todos"), s.todos, "No TODO nodes.");
  renderNodeCollection(
    getEl("repo-services"),
    s.external_services,
    "No external services.",
  );
  renderDependencies(s);
  renderBranchState(s.branch_state);
  renderBranchLinks(
    s.branch_links,
    s.active_branch
      ? `No cross-repo branch links for ${s.active_branch}.`
      : "No cross-repo branch links.",
  );
  renderLandscapeSummary(repositoryLandscape);
}

function renderBranchState(branchState: RepositoryBranchPayload | null): void {
  const el = getEl("repo-branch-state");
  if (!el) return;
  if (!branchState) {
    el.innerHTML = `<p class="text-sm text-stone-400 italic">No branch sync metadata available yet.</p>`;
    return;
  }

  const items: Array<[string, string]> = [
    ["Branch", branchState.branch],
    ["Last Synced", branchState.last_synced ?? "Never"],
    ["Payload", branchState.payload_version ?? "—"],
    ["Source", branchState.source ?? "—"],
    ["Nodes", String(branchState.node_count)],
    ["Edges", String(branchState.edge_count)],
    ["Deleted", String(branchState.deleted_nodes)],
    ["Diff Base", branchState.diff_base ?? "—"],
  ];

  el.innerHTML = items
    .map(
      ([label, value]) => `
    <article class="rounded-2xl border border-stone-200 bg-stone-50 px-4 py-3">
      <p class="text-xs font-semibold uppercase tracking-[0.18em] text-stone-400">${escapeHtml(label)}</p>
      <p class="mt-1.5 text-sm font-semibold text-stone-950 break-words">${escapeHtml(value)}</p>
    </article>
  `,
    )
    .join("");
}

function renderLandscapeSummary(
  data: RepositoryLandscapePayload | null,
  message?: string,
): void {
  const el = getEl("repo-landscape-summary");
  if (!el) return;
  if (!data) {
    el.innerHTML = `<article class="rounded-2xl border border-stone-200 bg-stone-50 px-4 py-3 text-stone-400 sm:col-span-3">${escapeHtml(message ?? "Repository branch landscape is not available yet.")}</article>`;
    return;
  }

  const items: Array<[string, string]> = [
    ["Repositories", String(data.summary.repo_count)],
    ["Branches", String(data.summary.branch_count)],
    ["Links", String(data.summary.link_count)],
  ];
  el.innerHTML = items
    .map(
      ([label, value]) => `
    <article class="rounded-2xl border border-stone-200 bg-stone-50 px-4 py-3">
      <p class="text-xs font-semibold uppercase tracking-[0.18em] text-stone-400">${escapeHtml(label)}</p>
      <p class="mt-1.5 text-2xl font-semibold text-stone-950">${escapeHtml(value)}</p>
    </article>
  `,
    )
    .join("");
}

function renderBranchLinks(
  links: RepositoryBranchLinkPayload[],
  emptyMessage: string,
): void {
  const overviewEl = getEl("repo-branch-links-list");
  const adminEl = getEl("repo-branch-link-admin-list");
  setText(
    getEl("repo-branch-links-status"),
    links.length
      ? `${links.length} branch link${links.length === 1 ? "" : "s"}`
      : "",
  );

  const renderMarkup = (editable: boolean): string => {
    if (!links.length) {
      return `<p class="text-sm text-stone-400 italic">${escapeHtml(emptyMessage)}</p>`;
    }

    return links
      .map((link) => {
        const outbound = link.source_repo_id === activeRepositoryId;
        const badgeClass = outbound
          ? "bg-amber-100 text-amber-800"
          : "bg-sky-100 text-sky-800";
        const badgeLabel = outbound ? "outbound" : "inbound";
        const note = String(
          link.metadata["reason"] ??
            link.metadata["discovered_by"] ??
            link.source ??
            "No notes",
        );
        return `
        <article class="rounded-2xl border border-stone-200 bg-stone-50 px-4 py-3">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <span class="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${badgeClass}">${escapeHtml(badgeLabel)}</span>
                <span class="rounded-full bg-stone-200 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-stone-700">${escapeHtml(link.relation)}</span>
              </div>
              <p class="mt-2 text-sm font-semibold text-stone-950 break-words">${escapeHtml(link.source_repo_name)} · ${escapeHtml(link.source_branch)} → ${escapeHtml(link.target_repo_name)} · ${escapeHtml(link.target_branch)}</p>
              <p class="mt-1 text-xs text-stone-500">${escapeHtml(link.target_repo_url ?? "No remote")} · confidence ${escapeHtml(link.confidence.toFixed(2))}</p>
              <p class="mt-1 text-xs text-stone-500">${escapeHtml(note)}</p>
            </div>
            ${
              editable && outbound
                ? `
              <button
                data-branch-link-id="${escapeHtml(link.id)}"
                class="shrink-0 rounded-full border border-red-200 bg-white px-3 py-1 text-xs font-medium text-red-600 transition hover:bg-red-50"
              >
                Remove
              </button>
            `
                : ""
            }
          </div>
        </article>
      `;
      })
      .join("");
  };

  if (overviewEl) overviewEl.innerHTML = renderMarkup(false);
  if (adminEl) adminEl.innerHTML = renderMarkup(true);
}

function renderNodeCollection(
  el: HTMLElement | null,
  nodes: RepositoryGraphNodePayload[],
  msg: string,
): void {
  if (!el) return;
  if (!nodes.length) {
    el.innerHTML = `<div class="rounded-2xl border border-dashed border-stone-200 px-4 py-4 text-sm text-stone-400">${escapeHtml(msg)}</div>`;
    return;
  }
  el.innerHTML = nodes
    .map((n) => {
      const p = meta(n.metadata, "path");
      const lang = meta(n.metadata, "language");
      return `<article class="rounded-2xl border border-stone-100 bg-white px-4 py-3">
      <p class="text-xs font-semibold uppercase tracking-widest text-stone-400">${escapeHtml(n.node_type)}</p>
      <p class="mt-1.5 text-sm font-semibold text-stone-900">${escapeHtml(n.name)}</p>
      <p class="mt-1 text-xs text-stone-500">${escapeHtml(p ?? lang ?? "—")}</p>
    </article>`;
    })
    .join("");
}

function renderDependencies(s: RepositoryGraphSummaryPayload): void {
  const el = getEl("repo-dependencies");
  if (!el) return;
  if (!s.dependencies.length) {
    el.innerHTML = `<div class="rounded-2xl border border-dashed border-stone-200 px-4 py-4 text-sm text-stone-400">No dependency edges.</div>`;
    return;
  }
  el.innerHTML = s.dependencies
    .map((dep) => {
      const targets = dep.depends_on.map((t) => escapeHtml(t.name)).join(", ");
      return `<article class="rounded-2xl border border-stone-100 bg-white px-4 py-3">
      <p class="text-xs font-semibold uppercase tracking-widest text-stone-400">Service</p>
      <p class="mt-1.5 text-sm font-semibold text-stone-900">${escapeHtml(dep.service)}</p>
      <p class="mt-1 text-xs text-stone-500">${targets || "No targets"}</p>
    </article>`;
    })
    .join("");
}

function renderGraphSummaryStats(
  nodeCount: number,
  edgeCount: number,
  typeCount: number,
  relationCount: number,
): void {
  const el = getEl("repo-graph-summary");
  if (!el) return;
  const items = [
    ["Nodes", String(nodeCount)],
    ["Edges", String(edgeCount)],
    ["Types", String(typeCount)],
    ["Relations", String(relationCount)],
  ];
  el.innerHTML = items
    .map(
      ([label, value]) => `
    <article class="rounded-2xl border border-stone-200 bg-stone-50 px-4 py-3">
      <p class="text-xs font-semibold uppercase tracking-[0.18em] text-stone-400">${escapeHtml(label)}</p>
      <p class="mt-1.5 text-2xl font-semibold text-stone-950">${escapeHtml(value)}</p>
    </article>
  `,
    )
    .join("");
}

// ============================================================
// Repository list
// ============================================================

let repositories: RepositoryPayload[] = [];
let activeRepositoryId: string | null = null;
let activeRepository: RepositoryPayload | null = null;
let activeBranch: string | null = null; // currently selected branch for graph view
let repositoryLandscape: RepositoryLandscapePayload | null = null;

function renderRepositories(): void {
  const list = getEl("repositories-list");
  if (!list) return;
  if (!repositories.length) {
    list.innerHTML = `<article class="rounded-2xl border border-dashed border-stone-200 px-4 py-4 text-sm text-stone-400">No repositories found.</article>`;
    return;
  }
  list.innerHTML = repositories
    .map((r) => {
      const active = r.id === activeRepositoryId;
      return `
      <button type="button" data-repository-id="${escapeHtml(r.id)}"
        class="rounded-2xl border px-4 py-3.5 text-left transition w-full ${
          active
            ? "border-amber-800 bg-amber-800 text-white shadow-md"
            : "border-stone-200 bg-white text-stone-800 hover:border-amber-700 hover:bg-amber-50"
        }"
      >
        <p class="text-[10px] font-bold uppercase tracking-widest ${active ? "text-amber-200" : "text-stone-400"}">Repository</p>
        <p class="mt-2 text-sm font-semibold">${escapeHtml(r.name)}</p>
        <p class="mt-1 text-xs ${active ? "text-amber-200" : "text-stone-400"}">${escapeHtml(r.default_branch ?? "—")}</p>
        <p class="mt-0.5 text-xs truncate ${active ? "text-amber-200" : "text-stone-400"}">${escapeHtml(r.remote_url ?? r.path)}</p>
      </button>
    `;
    })
    .join("");

  list.querySelectorAll("[data-repository-id]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-repository-id");
      if (id) void selectRepository(id);
    });
  });
}

function populateSettings(r: RepositoryPayload | null): void {
  const name = getEl<HTMLInputElement>("repo-settings-name");
  const remote = getEl<HTMLInputElement>("repo-settings-remote");
  const branch = getEl<HTMLInputElement>("repo-settings-branch");
  const path = getEl<HTMLInputElement>("repo-settings-path");
  if (!name || !remote || !branch || !path) return;
  name.value = r?.name ?? "";
  remote.value = r?.remote_url ?? "";
  branch.value = r?.default_branch ?? "";
  path.value = r?.path ?? "";

  const sourceBranch = getEl<HTMLInputElement>("repo-branch-link-source");
  if (sourceBranch) {
    sourceBranch.value = activeBranch ?? r?.default_branch ?? "";
  }

  const targetRepo = getEl<HTMLSelectElement>("repo-branch-link-target-repo");
  if (targetRepo) {
    targetRepo.innerHTML = [
      `<option value="">Select a repository</option>`,
      ...repositories
        .filter((repo) => repo.id !== r?.id)
        .map(
          (repo) =>
            `<option value="${escapeHtml(repo.id)}">${escapeHtml(repo.name)}${repo.default_branch ? ` · ${escapeHtml(repo.default_branch)}` : ""}</option>`,
        ),
    ].join("");
  }
}

function resetPanels(msg: string): void {
  setText(getEl("repo-summary-title"), "Select a repository");
  setText(getEl("repo-summary-meta"), msg);
  setText(getEl("repo-summary-sync"), "Waiting");

  const cards = getEl("repo-summary-cards");
  if (cards)
    cards.innerHTML = `<article class="rounded-3xl border border-stone-200 bg-stone-50 px-5 py-4 text-sm text-stone-400 col-span-4">${escapeHtml(msg)}</article>`;

  setText(getEl("repo-graph-status"), "");
  const gs = getEl("repo-graph-summary");
  if (gs) gs.innerHTML = "";

  repoRenderer?.clearGraph();
  searchRenderer?.clearGraph();
  impactRenderer?.clearGraph();

  renderNodeCollection(getEl("repo-routes"), [], msg);
  renderNodeCollection(getEl("repo-todos"), [], msg);
  renderNodeCollection(getEl("repo-services"), [], msg);
  renderDependencies({
    dependencies: [],
    routes: [],
    todos: [],
    external_services: [],
  } as unknown as RepositoryGraphSummaryPayload);
  renderBranchState(null);
  renderBranchLinks([], msg);
  renderLandscapeSummary(null, msg);

  populateSettings(null);
}

// ============================================================
// Data loading
// ============================================================

async function loadRepositories(): Promise<void> {
  setText(getEl("repositories-status"), "Loading…");
  try {
    const res = await listRepositories();
    repositories = res.repositories;
    await loadRepositoryLandscape();
    if (!repositories.length) {
      activeRepositoryId = null;
      activeRepository = null;
      renderRepositories();
      resetPanels("No repositories registered yet.");
      setText(getEl("repositories-status"), "No repositories found.");
      return;
    }
    if (
      !activeRepositoryId ||
      !repositories.some((r) => r.id === activeRepositoryId)
    ) {
      activeRepositoryId = repositories[0]?.id ?? null;
    }
    activeRepository =
      repositories.find((r) => r.id === activeRepositoryId) ?? null;
    renderRepositories();
    setText(
      getEl("repositories-status"),
      `${repositories.length} repositor${repositories.length === 1 ? "y" : "ies"}`,
    );
    if (activeRepositoryId) await selectRepository(activeRepositoryId);
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to load";
    setText(getEl("repositories-status"), msg);
    resetPanels(msg);
  }
}

// ============================================================
// Branch selector
// ============================================================

function renderBranchSelector(repo: RepositoryPayload | null): void {
  const wrap = getEl("repo-branch-selector-wrap");
  const sel = getEl<HTMLSelectElement>("repo-branch-selector");
  if (!wrap || !sel) return;

  if (!repo) {
    wrap.classList.add("hidden");
    return;
  }

  const branches = repo.tracked_branches ?? [];
  const def = repo.default_branch ?? "";

  // Ensure default branch is always in list
  const all = def && !branches.includes(def) ? [def, ...branches] : branches;

  if (!all.length) {
    wrap.classList.add("hidden");
    return;
  }

  wrap.classList.remove("hidden");
  sel.innerHTML = all
    .map(
      (b) =>
        `<option value="${escapeHtml(b)}" ${b === (activeBranch ?? def) ? "selected" : ""}>${escapeHtml(b)}${b === def ? " (default)" : ""}</option>`,
    )
    .join("");

  // Set activeBranch to current selection
  activeBranch = sel.value || def || null;
}

async function selectRepository(repoId: string): Promise<void> {
  activeRepositoryId = repoId;
  activeRepository = repositories.find((r) => r.id === repoId) ?? null;
  // When switching repos reset branch to default
  activeBranch = activeRepository?.default_branch ?? null;
  renderRepositories();
  populateSettings(activeRepository);
  renderBranchSelector(activeRepository);
  setText(getEl("repo-settings-status"), "");
  setText(getEl("graph-search-status"), "");
  setText(getEl("graph-impact-status"), "");
  setText(getEl("repo-graph-status"), "Loading graph…");

  await loadRepoGraph(repoId, activeBranch);
}

async function loadRepoGraph(
  repoId: string,
  branch: string | null,
): Promise<void> {
  setText(getEl("repo-graph-status"), "Loading graph…");
  try {
    const [summary, graphMap] = await Promise.all([
      getRepositoryGraphSummary(repoId, branch ?? undefined),
      getRepositoryGraphMap(repoId, branch ?? undefined),
    ]);
    activeRepository = summary.repository;
    repositories = repositories.map((r) =>
      r.id === summary.repository.id ? summary.repository : r,
    );
    renderRepositories();
    populateSettings(summary.repository);
    renderBranchSelector(summary.repository);
    renderSummary(summary);

    const { nodes, edges } = buildGraphData(
      summary.repository.name,
      graphMap.nodes,
      graphMap.edges,
      graphMap.graph_available ? "Graph loaded." : "No graph snapshot.",
    );

    renderGraphSummaryStats(
      graphMap.summary.node_count,
      graphMap.summary.edge_count,
      Object.keys(graphMap.summary.counts_by_type).length,
      Object.keys(graphMap.summary.counts_by_relation).length,
    );

    const renderer = initRepoRenderer();
    if (renderer) {
      renderer.render(nodes, edges);
      renderLegendOverlay("repo-graph-legend", nodes);
    }

    const branchLabel = graphMap.branch ? ` · ${graphMap.branch}` : "";
    setText(
      getEl("repo-graph-status"),
      graphMap.graph_available
        ? `${graphMap.summary.node_count} nodes · ${graphMap.summary.edge_count} edges${branchLabel}`
        : "No graph snapshot for this repository yet.",
    );
  } catch (err) {
    const msg =
      err instanceof Error ? err.message : "Failed to load repository";
    resetPanels(msg);
    setText(getEl("repo-graph-status"), msg);
  }
}

async function refreshActiveGraph(): Promise<void> {
  if (activeRepositoryId) await loadRepoGraph(activeRepositoryId, activeBranch);
}

async function loadRepositoryLandscape(): Promise<void> {
  try {
    repositoryLandscape = await getRepositoryLandscape();
    renderLandscapeSummary(repositoryLandscape);
  } catch (err) {
    repositoryLandscape = null;
    renderLandscapeSummary(
      null,
      err instanceof Error ? err.message : "Failed to load landscape.",
    );
  }
}

// ============================================================
// Search
// ============================================================

async function handleSearchSubmit(e: SubmitEvent): Promise<void> {
  e.preventDefault();
  if (!activeRepositoryId) {
    setText(getEl("graph-search-status"), "Select a repository first.");
    return;
  }
  const q = getEl<HTMLInputElement>("graph-search-query")?.value.trim() ?? "";
  if (!q) {
    setText(getEl("graph-search-status"), "Enter a search query.");
    return;
  }
  setText(getEl("graph-search-status"), "Searching…");
  try {
    const res = await searchRepositoryGraph(activeRepositoryId, {
      query: q,
      branch: activeBranch ?? undefined,
      nodeTypes: splitCsv(getEl<HTMLInputElement>("graph-search-types")?.value),
      languages: splitCsv(
        getEl<HTMLInputElement>("graph-search-languages")?.value,
      ),
      lastStates: splitCsv(
        getEl<HTMLInputElement>("graph-search-states")?.value,
      ),
      limit: 18,
    });
    const { nodes, edges } = buildGraphData(
      res.repository.name,
      res.results,
      [],
    );
    const renderer = initSearchRenderer();
    if (renderer) {
      renderer.render(nodes, edges);
      renderLegendOverlay("search-graph-legend", nodes);
    }
    setText(getEl("graph-search-status"), `${res.count} matching nodes.`);
  } catch (err) {
    setText(
      getEl("graph-search-status"),
      err instanceof Error ? err.message : "Search failed.",
    );
  }
}

// ============================================================
// Impact
// ============================================================

async function handleImpactSubmit(e: SubmitEvent): Promise<void> {
  e.preventDefault();
  if (!activeRepositoryId) {
    setText(getEl("graph-impact-status"), "Select a repository first.");
    return;
  }
  const target =
    getEl<HTMLInputElement>("graph-impact-target")?.value.trim() ?? "";
  if (!target) {
    setText(getEl("graph-impact-status"), "Enter a target symbol or route.");
    return;
  }
  const depth = Math.max(
    1,
    Math.min(
      Number(getEl<HTMLInputElement>("graph-impact-depth")?.value ?? "2") || 2,
      6,
    ),
  );
  const limit = Math.max(
    1,
    Math.min(
      Number(getEl<HTMLInputElement>("graph-impact-limit")?.value ?? "25") ||
        25,
      100,
    ),
  );
  setText(getEl("graph-impact-status"), "Analyzing impact…");

  try {
    const res = await getRepositoryGraphImpact(
      activeRepositoryId,
      target,
      depth,
      limit,
      activeBranch ?? undefined,
    );
    const matchNodes: ExtendedNodePayload[] = res.matches.map((n) => ({
      ...n,
      emphasis: "seed" as const,
    }));
    const impactNodes: ExtendedNodePayload[] = res.impacted.map((n) => ({
      ...n,
      emphasis: "result" as const,
    }));

    const edges: Array<{
      id: string;
      from: string;
      to: string;
      relation?: string;
      dashed?: boolean;
    }> = [];
    const seedId = res.matches[0]?.id;
    if (seedId) {
      for (const n of res.impacted) {
        edges.push({
          id: `${seedId}:${n.id}:${n.direction ?? "impact"}`,
          from: n.direction === "upstream" ? n.id : seedId,
          to: n.direction === "upstream" ? seedId : n.id,
          relation: n.direction === "upstream" ? "upstream" : "downstream",
          dashed: true,
        });
      }
    }

    const { nodes, edges: simEdges } = buildGraphData(
      res.repository.name,
      [...matchNodes, ...impactNodes],
      edges,
    );
    const renderer = initImpactRenderer();
    if (renderer) {
      renderer.render(nodes, simEdges);
      renderLegendOverlay("impact-graph-legend", nodes);
    }

    // Render impact summary stats
    const summaryEl = getEl("graph-impact-summary");
    if (summaryEl) {
      summaryEl.innerHTML = Object.entries(res.summary)
        .map(
          ([k, v]) => `
          <article class="rounded-2xl border border-stone-200 bg-stone-50 px-4 py-3">
            <p class="text-xs font-semibold uppercase tracking-[0.18em] text-stone-400">${escapeHtml(k)}</p>
            <p class="mt-1.5 text-xl font-semibold text-stone-950">${escapeHtml(typeof v === "object" ? JSON.stringify(v) : String(v))}</p>
          </article>
        `,
        )
        .join("");
    }

    setText(
      getEl("graph-impact-status"),
      `${res.impacted.length} impacted nodes.`,
    );
  } catch (err) {
    setText(
      getEl("graph-impact-status"),
      err instanceof Error ? err.message : "Impact scan failed.",
    );
  }
}

// ============================================================
// Settings
// ============================================================

async function handleSettingsSave(e: SubmitEvent): Promise<void> {
  e.preventDefault();
  if (!activeRepositoryId) {
    setText(getEl("repo-settings-status"), "Select a repository first.");
    return;
  }
  setText(getEl("repo-settings-status"), "Saving…");
  try {
    const res = await updateRepository(activeRepositoryId, {
      name: getEl<HTMLInputElement>("repo-settings-name")?.value.trim() ?? "",
      remote_url:
        getEl<HTMLInputElement>("repo-settings-remote")?.value.trim() ?? "",
      default_branch:
        getEl<HTMLInputElement>("repo-settings-branch")?.value.trim() ?? "",
      path: getEl<HTMLInputElement>("repo-settings-path")?.value.trim() ?? "",
    });
    activeRepository = res.repository;
    repositories = repositories.map((r) =>
      r.id === res.repository.id ? res.repository : r,
    );
    renderRepositories();
    populateSettings(res.repository);
    setText(getEl("repo-settings-status"), "Saved.");
    await refreshActiveGraph();
  } catch (err) {
    setText(
      getEl("repo-settings-status"),
      err instanceof Error ? err.message : "Failed to save.",
    );
  }
}

async function handleRepositoryDelete(): Promise<void> {
  if (!activeRepositoryId || !activeRepository) {
    setText(getEl("repo-settings-status"), "Select a repository first.");
    return;
  }
  if (!window.confirm(`Delete repository "${activeRepository.name}"?`)) return;
  setText(getEl("repo-settings-status"), "Deleting…");
  try {
    await deleteRepository(activeRepositoryId);
    repositories = repositories.filter((r) => r.id !== activeRepositoryId);
    activeRepositoryId = repositories[0]?.id ?? null;
    activeRepository =
      repositories.find((r) => r.id === activeRepositoryId) ?? null;
    renderRepositories();
    setText(getEl("repo-settings-status"), "Deleted.");
    if (activeRepositoryId) await selectRepository(activeRepositoryId);
    else resetPanels("No repositories registered yet.");
  } catch (err) {
    setText(
      getEl("repo-settings-status"),
      err instanceof Error ? err.message : "Failed to delete.",
    );
  }
}

// ============================================================
// Branch management (Settings tab)
// ============================================================

/** Render the tracked-branches list in the Settings tab */
function renderTrackedBranchesList(
  data: RepositoryBranchListPayload | null,
): void {
  const container = getEl("repo-branches-list");
  if (!container) return;

  if (!data) {
    container.innerHTML = `<p class="text-sm text-stone-400 italic">No repository selected.</p>`;
    return;
  }

  const all = data.tracked_branches;

  if (!all.length) {
    container.innerHTML = `<p class="text-sm text-stone-400 italic">No branches tracked yet.</p>`;
    return;
  }

  container.innerHTML = all
    .map((branchState) => {
      const branch = branchState.branch;
      const isDefault = branchState.is_default;
      const lastSynced = branchState.last_synced;
      return `
      <div class="flex items-center justify-between gap-3 rounded-2xl border border-stone-200 bg-stone-50 px-4 py-2.5">
        <div class="flex items-center gap-2 min-w-0">
          <svg class="h-3.5 w-3.5 shrink-0 text-stone-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 01-9 9"/>
          </svg>
          <span class="truncate text-sm font-medium text-stone-800">${escapeHtml(branch)}</span>
          ${isDefault ? `<span class="shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-700">default</span>` : ""}
          ${lastSynced ? `<span class="shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-700">synced</span>` : ""}
        </div>
        ${
          isDefault
            ? ""
            : `
          <button
            data-remove-branch="${escapeHtml(branch)}"
            class="shrink-0 rounded-full border border-red-200 bg-white px-3 py-1 text-xs font-medium text-red-600 transition hover:bg-red-50"
          >
            Remove
          </button>
        `
        }
      </div>`;
    })
    .join("");
}

/** Load branches from API and render */
async function loadTrackedBranches(): Promise<void> {
  if (!activeRepositoryId) return;
  const statusEl = getEl("repo-branches-status");
  try {
    const data = await getRepositoryBranches(activeRepositoryId);
    renderTrackedBranchesList(data);
    setText(statusEl, "");
  } catch (err) {
    setText(statusEl, `Failed to load branches: ${String(err)}`);
  }
}

async function loadBranchLinks(): Promise<void> {
  if (!activeRepositoryId) return;
  try {
    const data = await getRepositoryBranchLinks(
      activeRepositoryId,
      activeBranch ?? undefined,
    );
    renderBranchLinks(
      data.links,
      activeBranch
        ? `No cross-repo branch links for ${activeBranch}.`
        : "No cross-repo branch links.",
    );
  } catch (err) {
    renderBranchLinks(
      [],
      err instanceof Error ? err.message : "Failed to load branch links.",
    );
  }
}

/** Handle adding a new tracked branch */
async function handleAddBranch(): Promise<void> {
  if (!activeRepositoryId) return;
  const input = getEl<HTMLInputElement>("repo-branch-add-input");
  const btn = getEl<HTMLButtonElement>("repo-branch-add-btn");
  const statusEl = getEl("repo-branches-status");
  if (!input) return;

  const branch = input.value.trim();
  if (!branch) {
    setText(statusEl, "Please enter a branch name.");
    return;
  }

  if (btn) btn.disabled = true;
  setText(statusEl, "Adding branch…");

  try {
    await addRepositoryBranch(activeRepositoryId, branch);
    input.value = "";
    setText(statusEl, `Branch "${branch}" added.`);
    await loadTrackedBranches();
    // Also refresh the branch selector in Graph tab
    if (activeRepository) {
      activeRepository = {
        ...activeRepository,
        tracked_branches: [
          ...(activeRepository.tracked_branches ?? []),
          branch,
        ],
      };
      renderBranchSelector(activeRepository);
    }
  } catch (err) {
    setText(statusEl, `Error: ${String(err)}`);
  } finally {
    if (btn) btn.disabled = false;
  }
}

/** Handle removing a tracked branch */
async function handleRemoveBranch(branch: string): Promise<void> {
  if (!activeRepositoryId) return;
  const statusEl = getEl("repo-branches-status");
  setText(statusEl, `Removing "${branch}"…`);

  try {
    await removeRepositoryBranch(activeRepositoryId, branch);
    setText(statusEl, `Branch "${branch}" removed.`);
    await loadTrackedBranches();
    // Also refresh branch selector
    if (activeRepository) {
      activeRepository = {
        ...activeRepository,
        tracked_branches: (activeRepository.tracked_branches ?? []).filter(
          (b) => b !== branch,
        ),
      };
      renderBranchSelector(activeRepository);
      // If removed branch was active, reset to default
      if (activeBranch === branch) {
        activeBranch = activeRepository.default_branch ?? null;
        if (activeRepositoryId)
          void loadRepoGraph(activeRepositoryId, activeBranch);
      }
    }
  } catch (err) {
    setText(statusEl, `Error: ${String(err)}`);
  }
}

async function handleBranchLinkSubmit(e: SubmitEvent): Promise<void> {
  e.preventDefault();
  if (!activeRepositoryId) return;

  const statusEl = getEl("repo-branch-link-status");
  const sourceBranch =
    getEl<HTMLInputElement>("repo-branch-link-source")?.value.trim() ??
    activeBranch ??
    "";
  const targetRepoId =
    getEl<HTMLSelectElement>("repo-branch-link-target-repo")?.value.trim() ??
    "";
  const targetBranch =
    getEl<HTMLInputElement>("repo-branch-link-target-branch")?.value.trim() ??
    "";
  const relation =
    getEl<HTMLSelectElement>("repo-branch-link-relation")?.value.trim() ??
    "depends_on";
  const direction = (getEl<HTMLSelectElement>(
    "repo-branch-link-direction",
  )?.value.trim() ?? "outbound") as "outbound" | "inbound" | "bidirectional";
  const notes =
    getEl<HTMLInputElement>("repo-branch-link-notes")?.value.trim() ?? "";
  const targetRepo =
    repositories.find((repo) => repo.id === targetRepoId) ?? null;

  if (!sourceBranch || !targetRepo || !targetBranch) {
    setText(
      statusEl,
      "Source branch, target repository, and target branch are required.",
    );
    return;
  }

  setText(statusEl, "Saving link…");
  try {
    await upsertRepositoryBranchLink(activeRepositoryId, {
      source_branch: sourceBranch,
      target_repo_id: targetRepo.id,
      target_repo_name: targetRepo.name,
      target_repo_url: targetRepo.remote_url,
      target_branch: targetBranch,
      relation,
      direction,
      confidence: 1,
      metadata: notes ? { reason: notes } : {},
    });
    const targetBranchInput = getEl<HTMLInputElement>(
      "repo-branch-link-target-branch",
    );
    const notesInput = getEl<HTMLInputElement>("repo-branch-link-notes");
    if (targetBranchInput) targetBranchInput.value = "";
    if (notesInput) notesInput.value = "";
    setText(statusEl, "Link saved.");
    await loadBranchLinks();
    await loadRepositoryLandscape();
    await refreshActiveGraph();
  } catch (err) {
    setText(
      statusEl,
      err instanceof Error ? err.message : "Failed to save branch link.",
    );
  }
}

async function handleBranchLinkDelete(linkId: string): Promise<void> {
  if (!activeRepositoryId) return;
  const statusEl = getEl("repo-branch-link-status");
  setText(statusEl, "Removing link…");
  try {
    await deleteRepositoryBranchLink(
      activeRepositoryId,
      linkId,
      activeBranch ?? undefined,
    );
    setText(statusEl, "Link removed.");
    await loadBranchLinks();
    await loadRepositoryLandscape();
    await refreshActiveGraph();
  } catch (err) {
    setText(
      statusEl,
      err instanceof Error ? err.message : "Failed to remove branch link.",
    );
  }
}

// ============================================================
// Event bindings
// ============================================================

getEl("repositories-refresh")?.addEventListener("click", () => {
  void loadRepositories();
});
getEl("repo-graph-refresh")?.addEventListener("click", () => {
  void refreshActiveGraph();
});
getEl("graph-search-form")?.addEventListener("submit", (e) => {
  void handleSearchSubmit(e);
});
getEl("graph-impact-form")?.addEventListener("submit", (e) => {
  void handleImpactSubmit(e);
});
getEl("repo-settings-form")?.addEventListener("submit", (e) => {
  void handleSettingsSave(e);
});
getEl("repo-settings-delete")?.addEventListener("click", () => {
  void handleRepositoryDelete();
});
getEl("repo-branch-link-form")?.addEventListener("submit", (e) => {
  void handleBranchLinkSubmit(e);
});

// Branch selector: reload graph when branch changes
getEl<HTMLSelectElement>("repo-branch-selector")?.addEventListener(
  "change",
  (e) => {
    const newBranch = (e.target as HTMLSelectElement).value;
    if (newBranch && newBranch !== activeBranch && activeRepositoryId) {
      activeBranch = newBranch;
      populateSettings(activeRepository);
      void loadBranchLinks();
      void loadRepoGraph(activeRepositoryId, activeBranch);
    }
  },
);

// Branch management: add button
getEl("repo-branch-add-btn")?.addEventListener("click", () => {
  void handleAddBranch();
});

// Branch management: Enter key in input
getEl<HTMLInputElement>("repo-branch-add-input")?.addEventListener(
  "keydown",
  (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      void handleAddBranch();
    }
  },
);

// Branch management: remove buttons (event delegation)
getEl("repo-branches-list")?.addEventListener("click", (e) => {
  const btn = (e.target as Element).closest<HTMLButtonElement>(
    "[data-remove-branch]",
  );
  if (btn) {
    const branch = btn.dataset["removeBranch"] ?? "";
    if (branch) void handleRemoveBranch(branch);
  }
});

getEl("repo-branch-link-admin-list")?.addEventListener("click", (e) => {
  const btn = (e.target as Element).closest<HTMLButtonElement>(
    "[data-branch-link-id]",
  );
  if (btn) {
    const linkId = btn.dataset["branchLinkId"] ?? "";
    if (linkId) void handleBranchLinkDelete(linkId);
  }
});

// ============================================================
// Init — default tab is "graph" (applied at page load)
// ============================================================

// Apply full-width graph layout immediately (Graph is default active tab)
setGraphFullWidth(true);

void loadRepositories();
