import * as d3 from "d3";

/** D3 simulation node — must extend SimulationNodeDatum so D3 can track x/y/vx/vy/fx/fy */
export interface SimNode extends d3.SimulationNodeDatum {
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
export interface SimEdge extends d3.SimulationLinkDatum<SimNode> {
  id: string;
  relation?: string;
  dashed?: boolean;
  edgeColor?: string;
}

// ============================================================
// Visual constants — GitNexus-inspired palette
// ============================================================

export const NODE_COLORS: Record<string, string> = {
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

export const NODE_RADII: Record<string, number> = {
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

export const EDGE_STYLES: Record<
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

export function colorForType(t: string): string {
  return NODE_COLORS[t] ?? "#a8a29e";
}
export function radiusForType(t: string): number {
  return NODE_RADII[t] ?? 7;
}

// ============================================================
// D3 Graph Renderer
// ============================================================

export class D3GraphRenderer {
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

  public getNodes(): SimNode[] {
    return this.nodes;
  }
  public getEdges(): SimEdge[] {
    return this.edges;
  }

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

  private finite(value: number | undefined | null, fallback = 0): number {
    if (typeof value !== "number") return fallback;
    return Number.isFinite(value) ? value : fallback;
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
        const t = e.transform;
        if (
          Number.isFinite(t.x) &&
          Number.isFinite(t.y) &&
          Number.isFinite(t.k)
        ) {
          this.g.attr("transform", t.toString());
        }
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
      .attr("x1", (d) => this.finite((d.source as SimNode).x))
      .attr("y1", (d) => this.finite((d.source as SimNode).y))
      .attr("x2", (d) => this.finite((d.target as SimNode).x))
      .attr("y2", (d) => this.finite((d.target as SimNode).y));

    this.nodeGrp
      .selectAll<SVGGElement, SimNode>("g.node")
      .attr("transform", (d) => {
        const x = this.finite(d.x);
        const y = this.finite(d.y);
        return `translate(${x},${y})`;
      });
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
      if (!Number.isFinite(n.x) || !Number.isFinite(n.y)) {
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
    const xs = this.nodes.map((d) => this.finite(d.x));
    const ys = this.nodes.map((d) => this.finite(d.y));
    const x0 = Math.min(...xs),
      x1 = Math.max(...xs);
    const y0 = Math.min(...ys),
      y1 = Math.max(...ys);
    const gw = x1 - x0 || 1,
      gh = y1 - y0 || 1;
    const scale = Math.min((w - pad * 2) / gw, (h - pad * 2) / gh, 3);
    if (!Number.isFinite(scale) || scale <= 0) return;
    const tx = w / 2 - scale * (x0 + gw / 2);
    const ty = h / 2 - scale * (y0 + gh / 2);
    if (!Number.isFinite(tx) || !Number.isFinite(ty)) return;
    const transform = d3.zoomIdentity.translate(tx, ty).scale(scale);
    if (
      !Number.isFinite(transform.x) ||
      !Number.isFinite(transform.y) ||
      !Number.isFinite(transform.k)
    ) {
      return;
    }

    this.svg
      .transition()
      .duration(600)
      .call(this.zoom.transform, transform);
  }

  toggleLayout(running?: boolean): boolean {
    const target = running !== undefined ? running : !this.simRunning;
    if (!target) {
      this.sim.stop();
      this.simRunning = false;
      this.onSimCb?.(false);
      return false;
    } else {
      this.sim.alpha(0.5).restart();
      this.simRunning = true;
      this.onSimCb?.(true);
      return true;
    }
  }

  destroy(): void {
    this.ro.disconnect();
    this.sim.stop();
    this.svg.remove();
  }
}
