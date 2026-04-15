import {
  getRepositoryGraphImpact,
  getRepositoryGraphSummary,
  listRepositories,
  searchRepositoryGraph,
  type RepositoryGraphImpactPayload,
  type RepositoryGraphNodePayload,
  type RepositoryGraphSummaryPayload,
  type RepositoryPayload,
} from "../lib/api/admin";

const repositoriesList = document.querySelector("#repositories-list");
const repositoriesStatus = document.querySelector("#repositories-status");
const refreshButton = document.querySelector("#repositories-refresh");
const summaryTitle = document.querySelector("#repo-summary-title");
const summaryMeta = document.querySelector("#repo-summary-meta");
const summarySync = document.querySelector("#repo-summary-sync");
const summaryCards = document.querySelector("#repo-summary-cards");
const routesRegion = document.querySelector("#repo-routes");
const todosRegion = document.querySelector("#repo-todos");
const servicesRegion = document.querySelector("#repo-services");
const dependenciesRegion = document.querySelector("#repo-dependencies");
const searchForm = document.querySelector("#graph-search-form");
const searchQueryInput = document.querySelector(
  "#graph-search-query",
) as HTMLInputElement | null;
const searchTypesInput = document.querySelector(
  "#graph-search-types",
) as HTMLInputElement | null;
const searchStatus = document.querySelector("#graph-search-status");
const searchCanvas = document.querySelector(
  "#graph-search-canvas",
) as HTMLCanvasElement | null;
const searchLegend = document.querySelector("#graph-search-legend");
const searchDetails = document.querySelector("#graph-search-details");
const impactForm = document.querySelector("#graph-impact-form");
const impactTargetInput = document.querySelector(
  "#graph-impact-target",
) as HTMLInputElement | null;
const impactDepthInput = document.querySelector(
  "#graph-impact-depth",
) as HTMLInputElement | null;
const impactLimitInput = document.querySelector(
  "#graph-impact-limit",
) as HTMLInputElement | null;
const impactStatus = document.querySelector("#graph-impact-status");
const impactSummary = document.querySelector("#graph-impact-summary");
const impactCanvas = document.querySelector(
  "#graph-impact-canvas",
) as HTMLCanvasElement | null;
const impactLegend = document.querySelector("#graph-impact-legend");
const impactDetails = document.querySelector("#graph-impact-details");

let repositories: RepositoryPayload[] = [];
let activeRepositoryId: string | null = null;

type GraphCanvasNode = {
  id: string;
  label: string;
  type: string;
  x: number;
  y: number;
  radius: number;
  metadata: Record<string, unknown>;
  score?: number;
  direction?: string;
  distance?: number;
  emphasis?: "hub" | "seed" | "result";
};

type GraphCanvasEdge = {
  from: string;
  to: string;
  color?: string;
};

type GraphCanvasState = {
  emptyMessage: string;
  nodes: GraphCanvasNode[];
  edges: GraphCanvasEdge[];
  selectedNodeId: string | null;
};

const NODE_TYPE_COLORS: Record<string, string> = {
  query: "#d97706",
  target: "#0284c7",
  route: "#b45309",
  controller: "#0f766e",
  service: "#1d4ed8",
  external_service_api: "#7c3aed",
  todo: "#dc2626",
  file: "#475569",
  function: "#0f766e",
  class: "#2563eb",
  interface: "#7c3aed",
  module: "#4f46e5",
  repository: "#1f2937",
};

let searchGraphState: GraphCanvasState = {
  emptyMessage: "Run a graph search to visualize matching nodes.",
  nodes: [],
  edges: [],
  selectedNodeId: null,
};
let impactGraphState: GraphCanvasState = {
  emptyMessage: "Run an impact scan to visualize nearby graph nodes.",
  nodes: [],
  edges: [],
  selectedNodeId: null,
};

const escapeHtml = (value: string): string =>
  value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

function setText(element: Element | null, value: string): void {
  if (element) {
    element.textContent = value;
  }
}

function colorForNodeType(nodeType: string): string {
  return NODE_TYPE_COLORS[nodeType] ?? "#57534e";
}

function normalizeLabel(label: string, limit = 28): string {
  if (label.length <= limit) {
    return label;
  }
  return `${label.slice(0, limit - 1)}…`;
}

function renderNodeLegend(
  element: Element | null,
  nodes: GraphCanvasNode[],
): void {
  if (!element) {
    return;
  }
  const uniqueTypes = [...new Set(nodes.map((node) => node.type))];
  if (!uniqueTypes.length) {
    element.innerHTML = `<p class="text-sm leading-6 text-stone-500">Legend appears once graph data is available.</p>`;
    return;
  }
  element.innerHTML = `
    <p class="eyebrow">Node Palette</p>
    <div class="mt-3 flex flex-wrap gap-2">
      ${uniqueTypes
        .map(
          (type) => `
            <span class="inline-flex items-center gap-2 rounded-full border border-stone-200 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-stone-700">
              <span class="h-2.5 w-2.5 rounded-full" style="background:${escapeHtml(colorForNodeType(type))}"></span>
              ${escapeHtml(type.replaceAll("_", " "))}
            </span>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderNodeDetails(
  element: Element | null,
  state: GraphCanvasState,
  fallbackMessage: string,
): void {
  if (!element) {
    return;
  }
  const activeNode =
    state.nodes.find((node) => node.id === state.selectedNodeId) ??
    state.nodes[0];
  if (!activeNode) {
    element.innerHTML = `<p class="text-sm leading-6 text-stone-500">${escapeHtml(fallbackMessage)}</p>`;
    return;
  }
  const path =
    typeof activeNode.metadata.path === "string"
      ? activeNode.metadata.path
      : null;
  const routePath =
    typeof activeNode.metadata.route_path === "string"
      ? activeNode.metadata.route_path
      : null;
  const text =
    typeof activeNode.metadata.text === "string"
      ? activeNode.metadata.text
      : null;
  element.innerHTML = `
    <p class="eyebrow">Focused Node</p>
    <div class="mt-3 rounded-[1.5rem] border border-stone-200 bg-stone-50 p-4">
      <div class="flex flex-wrap items-center gap-3">
        <span class="h-3 w-3 rounded-full" style="background:${escapeHtml(colorForNodeType(activeNode.type))}"></span>
        <strong class="text-base text-stone-950">${escapeHtml(activeNode.label)}</strong>
      </div>
      <p class="mt-3 text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">${escapeHtml(activeNode.type.replaceAll("_", " "))}</p>
      ${typeof activeNode.score === "number" ? `<p class="mt-3 text-sm text-stone-600">Search score: <strong class="text-stone-950">${escapeHtml(String(activeNode.score))}</strong></p>` : ""}
      ${activeNode.direction ? `<p class="mt-3 text-sm text-stone-600">Direction: <strong class="text-stone-950">${escapeHtml(activeNode.direction)}</strong></p>` : ""}
      ${typeof activeNode.distance === "number" ? `<p class="mt-3 text-sm text-stone-600">Hop distance: <strong class="text-stone-950">${escapeHtml(String(activeNode.distance))}</strong></p>` : ""}
      ${path ? `<p class="mt-3 break-all text-sm text-stone-600">Path: <span class="text-stone-950">${escapeHtml(path)}</span></p>` : ""}
      ${routePath ? `<p class="mt-3 break-all text-sm text-stone-600">Route: <span class="text-stone-950">${escapeHtml(routePath)}</span></p>` : ""}
      ${text ? `<p class="mt-3 text-sm leading-6 text-stone-600">${escapeHtml(normalizeLabel(text, 120))}</p>` : ""}
    </div>
  `;
}

function clearCanvas(canvas: HTMLCanvasElement | null, message: string): void {
  if (!canvas) {
    return;
  }
  const context = canvas.getContext("2d");
  if (!context) {
    return;
  }
  const bounds = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(bounds.width * ratio));
  canvas.height = Math.max(1, Math.floor(bounds.height * ratio));
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, bounds.width, bounds.height);
  context.fillStyle = "#57534e";
  context.font = "500 14px ui-sans-serif, system-ui, sans-serif";
  context.textAlign = "center";
  context.fillText(message, bounds.width / 2, bounds.height / 2);
}

function resolveCanvasNodeAt(
  canvas: HTMLCanvasElement,
  state: GraphCanvasState,
  event: MouseEvent,
): GraphCanvasNode | null {
  const rect = canvas.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  const layoutNodes = layoutNodesForCanvas(canvas, state.nodes);
  return (
    layoutNodes.find((node) => {
      const dx = x - node.x;
      const dy = y - node.y;
      return Math.sqrt(dx * dx + dy * dy) <= node.radius + 4;
    }) ?? null
  );
}

function layoutNodesForCanvas(
  canvas: HTMLCanvasElement,
  nodes: GraphCanvasNode[],
): GraphCanvasNode[] {
  const bounds = canvas.getBoundingClientRect();
  if (!nodes.length || bounds.width <= 0 || bounds.height <= 0) {
    return nodes;
  }
  const padding = 34;
  const minX = Math.min(...nodes.map((node) => node.x - node.radius));
  const maxX = Math.max(...nodes.map((node) => node.x + node.radius));
  const minY = Math.min(...nodes.map((node) => node.y - node.radius));
  const maxY = Math.max(...nodes.map((node) => node.y + node.radius));
  const logicalWidth = Math.max(maxX - minX, 1);
  const logicalHeight = Math.max(maxY - minY, 1);
  const scale = Math.min(
    (bounds.width - padding * 2) / logicalWidth,
    (bounds.height - padding * 2) / logicalHeight,
    1.2,
  );
  const offsetX = (bounds.width - logicalWidth * scale) / 2 - minX * scale;
  const offsetY = (bounds.height - logicalHeight * scale) / 2 - minY * scale;
  return nodes.map((node) => ({
    ...node,
    x: node.x * scale + offsetX,
    y: node.y * scale + offsetY,
    radius: Math.max(10, node.radius * Math.min(scale, 1)),
  }));
}

function drawGraphCanvas(
  canvas: HTMLCanvasElement | null,
  state: GraphCanvasState,
): void {
  if (!canvas) {
    return;
  }
  if (!state.nodes.length) {
    clearCanvas(canvas, state.emptyMessage);
    return;
  }
  const context = canvas.getContext("2d");
  if (!context) {
    return;
  }
  const bounds = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(bounds.width * ratio));
  canvas.height = Math.max(1, Math.floor(bounds.height * ratio));
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, bounds.width, bounds.height);
  const layoutNodes = layoutNodesForCanvas(canvas, state.nodes);

  context.fillStyle = "rgba(255,255,255,0.92)";
  context.fillRect(0, 0, bounds.width, bounds.height);

  for (const edge of state.edges) {
    const source = layoutNodes.find((node) => node.id === edge.from);
    const target = layoutNodes.find((node) => node.id === edge.to);
    if (!source || !target) {
      continue;
    }
    context.beginPath();
    context.moveTo(source.x, source.y);
    context.lineTo(target.x, target.y);
    context.strokeStyle = edge.color ?? "rgba(120,113,108,0.35)";
    context.lineWidth = 1.4;
    context.stroke();
  }

  for (const node of layoutNodes) {
    const fill = colorForNodeType(node.type);
    const isSelected = node.id === state.selectedNodeId;
    context.beginPath();
    context.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
    context.fillStyle = fill;
    context.shadowColor = isSelected ? `${fill}99` : "rgba(0,0,0,0.08)";
    context.shadowBlur = isSelected ? 18 : 8;
    context.fill();
    context.shadowBlur = 0;
    context.lineWidth = isSelected ? 3 : 1.5;
    context.strokeStyle = isSelected ? "#111827" : "rgba(255,255,255,0.85)";
    context.stroke();

    context.fillStyle = "#1c1917";
    context.font = `${node.emphasis === "hub" ? 700 : 600} 12px ui-sans-serif, system-ui, sans-serif`;
    context.textAlign = "center";
    context.fillText(
      normalizeLabel(node.label),
      node.x,
      node.y + node.radius + 16,
    );
  }
}

function attachCanvasInteraction(
  canvas: HTMLCanvasElement | null,
  getState: () => GraphCanvasState,
  setState: (state: GraphCanvasState) => void,
  detailsElement: Element | null,
  emptyMessage: string,
): void {
  canvas?.addEventListener("click", (event) => {
    if (!canvas) {
      return;
    }
    const state = getState();
    const hit = resolveCanvasNodeAt(canvas, state, event);
    if (!hit) {
      return;
    }
    const nextState = { ...state, selectedNodeId: hit.id };
    setState(nextState);
    drawGraphCanvas(canvas, nextState);
    renderNodeDetails(detailsElement, nextState, emptyMessage);
  });
}

function renderEmptyRegion(element: Element | null, message: string): void {
  if (!element) {
    return;
  }
  element.innerHTML = `<p class="rounded-2xl border border-dashed border-stone-300 bg-white px-4 py-3 text-sm text-stone-500">${escapeHtml(message)}</p>`;
}

function renderNodeList(
  element: Element | null,
  nodes: RepositoryGraphNodePayload[],
  emptyMessage: string,
): void {
  if (!element) {
    return;
  }
  if (!nodes.length) {
    renderEmptyRegion(element, emptyMessage);
    return;
  }
  element.innerHTML = nodes
    .map((node) => {
      const path =
        typeof node.metadata.path === "string" ? node.metadata.path : "";
      return `
        <article class="rounded-2xl border border-stone-200 bg-white px-4 py-3">
          <div class="flex items-center justify-between gap-3">
            <strong class="text-sm text-stone-900">${escapeHtml(node.name)}</strong>
            <span class="rounded-full bg-stone-100 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-600">${escapeHtml(node.node_type)}</span>
          </div>
          ${path ? `<p class="mt-2 text-xs text-stone-500">${escapeHtml(path)}</p>` : ""}
        </article>
      `;
    })
    .join("");
}

function renderSummaryCards(summary: RepositoryGraphSummaryPayload): void {
  if (!summaryCards) {
    return;
  }
  const cards = [
    { label: "Nodes", value: String(summary.node_count) },
    {
      label: "Node Types",
      value: String(Object.keys(summary.counts_by_type).length),
    },
    { label: "Routes", value: String(summary.routes.length) },
    {
      label: "External Services",
      value: String(summary.external_services.length),
    },
  ];
  summaryCards.innerHTML = cards
    .map(
      (card) => `
        <article class="rounded-3xl border border-stone-200 bg-stone-50 px-5 py-4">
          <p class="text-xs font-semibold uppercase tracking-[0.22em] text-stone-500">${escapeHtml(card.label)}</p>
          <p class="mt-3 text-3xl font-semibold tracking-tight text-stone-950">${escapeHtml(card.value)}</p>
        </article>
      `,
    )
    .join("");
}

function renderDependencies(summary: RepositoryGraphSummaryPayload): void {
  if (!dependenciesRegion) {
    return;
  }
  if (!summary.dependencies.length) {
    renderEmptyRegion(
      dependenciesRegion,
      "No service dependency edges found yet.",
    );
    return;
  }
  dependenciesRegion.innerHTML = summary.dependencies
    .map(
      (dependency) => `
        <article class="rounded-2xl border border-stone-200 bg-white px-4 py-3">
          <p class="text-sm font-semibold text-stone-900">${escapeHtml(dependency.service)}</p>
          <p class="mt-2 text-sm text-stone-600">${dependency.depends_on.map((item) => escapeHtml(item.name)).join(", ")}</p>
        </article>
      `,
    )
    .join("");
}

function renderRepositoryList(): void {
  if (!repositoriesList) {
    return;
  }
  if (!repositories.length) {
    repositoriesList.innerHTML = `
      <article class="rounded-3xl border border-dashed border-stone-300 bg-stone-50 px-4 py-4 text-sm text-stone-600">
        No repositories registered yet.
      </article>
    `;
    return;
  }

  repositoriesList.innerHTML = repositories
    .map((repository) => {
      const active = repository.id === activeRepositoryId;
      return `
        <button
          type="button"
          data-repository-id="${escapeHtml(repository.id)}"
          class="rounded-3xl border px-4 py-4 text-left transition ${active ? "border-amber-700 bg-amber-50" : "border-stone-200 bg-white hover:border-amber-400"}"
        >
          <div class="flex items-center justify-between gap-3">
            <strong class="text-sm text-stone-900">${escapeHtml(repository.name)}</strong>
            <span class="rounded-full bg-stone-100 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-600">${escapeHtml(repository.workflow_state ?? "idle")}</span>
          </div>
          <p class="mt-2 break-all text-xs text-stone-500">${escapeHtml(repository.remote_url || repository.path || "No remote")}</p>
        </button>
      `;
    })
    .join("");

  repositoriesList
    .querySelectorAll("[data-repository-id]")
    .forEach((element) => {
      element.addEventListener("click", () => {
        const repoId = element.getAttribute("data-repository-id");
        if (!repoId || repoId === activeRepositoryId) {
          return;
        }
        activeRepositoryId = repoId;
        renderRepositoryList();
        void loadSummary(repoId);
      });
    });
}

async function loadRepositories(): Promise<void> {
  setText(repositoriesStatus, "Loading repositories...");
  try {
    const payload = await listRepositories();
    repositories = payload.repositories;
    if (!activeRepositoryId && repositories.length) {
      activeRepositoryId = repositories[0].id;
    }
    renderRepositoryList();
    setText(
      repositoriesStatus,
      `${repositories.length} repositories available.`,
    );
    if (activeRepositoryId) {
      await loadSummary(activeRepositoryId);
    }
  } catch (error) {
    renderEmptyRegion(
      repositoriesList,
      error instanceof Error ? error.message : "Failed to load repositories.",
    );
    setText(repositoriesStatus, "Repository load failed.");
  }
}

async function loadSummary(repoId: string): Promise<void> {
  const repository = repositories.find((item) => item.id === repoId);
  setText(summaryTitle, repository ? repository.name : "Loading...");
  setText(
    summaryMeta,
    repository?.remote_url ||
      repository?.path ||
      "Loading repository graph summary...",
  );
  setText(summarySync, "Loading");
  try {
    const summary = await getRepositoryGraphSummary(repoId);
    setText(summaryTitle, summary.repository.name);
    setText(
      summaryMeta,
      summary.graph_available
        ? `${summary.node_count} graph nodes indexed from ${summary.repository.remote_url || summary.repository.path || "unknown repository"}`
        : "Graph store is not configured for this environment.",
    );
    const acceptedAt =
      typeof summary.last_sync?.accepted_at === "string"
        ? summary.last_sync.accepted_at
        : null;
    setText(
      summarySync,
      acceptedAt
        ? `Synced ${new Date(acceptedAt).toLocaleString()}`
        : "No sync yet",
    );
    renderSummaryCards(summary);
    renderNodeList(routesRegion, summary.routes, "No route nodes found yet.");
    renderNodeList(todosRegion, summary.todos, "No TODO nodes found yet.");
    renderNodeList(
      servicesRegion,
      summary.external_services,
      "No external service nodes found yet.",
    );
    renderDependencies(summary);
  } catch (error) {
    renderEmptyRegion(
      summaryCards,
      error instanceof Error ? error.message : "Failed to load graph summary.",
    );
    renderEmptyRegion(routesRegion, "Summary unavailable.");
    renderEmptyRegion(todosRegion, "Summary unavailable.");
    renderEmptyRegion(servicesRegion, "Summary unavailable.");
    renderEmptyRegion(dependenciesRegion, "Summary unavailable.");
    setText(summarySync, "Unavailable");
  }
}

function buildSearchCanvasState(
  query: string,
  results: Array<RepositoryGraphNodePayload & { score?: number }>,
): GraphCanvasState {
  if (!results.length) {
    return {
      emptyMessage: "No graph matches found.",
      nodes: [],
      edges: [],
      selectedNodeId: null,
    };
  }
  const centerX = 260;
  const centerY = 175;
  const hubId = `query:${query}`;
  const nodes: GraphCanvasNode[] = [
    {
      id: hubId,
      label: `Search: ${query}`,
      type: "query",
      x: centerX,
      y: centerY,
      radius: 22,
      metadata: { query },
      emphasis: "hub",
    },
  ];
  const edges: GraphCanvasEdge[] = [];
  results.forEach((item, index) => {
    const ring = index < 6 ? 1 : 2;
    const ringItems =
      ring === 1
        ? Math.min(results.length, 6)
        : Math.max(results.length - 6, 1);
    const ringIndex = ring === 1 ? index : index - 6;
    const angle = -Math.PI / 2 + (Math.PI * 2 * ringIndex) / ringItems;
    const radiusFromCenter = ring === 1 ? 105 : 145;
    const nodeId = item.id || `${item.node_type}:${item.name}`;
    nodes.push({
      id: nodeId,
      label: item.name,
      type: item.node_type,
      x: centerX + Math.cos(angle) * radiusFromCenter,
      y: centerY + Math.sin(angle) * radiusFromCenter,
      radius: 16,
      metadata: item.metadata,
      score: item.score,
      emphasis: "result",
    });
    edges.push({ from: hubId, to: nodeId, color: "rgba(217,119,6,0.28)" });
  });
  return {
    emptyMessage: "No graph matches found.",
    nodes,
    edges,
    selectedNodeId: results[0]?.id ?? null,
  };
}

function renderImpact(payload: RepositoryGraphImpactPayload): void {
  if (impactSummary) {
    const byNodeType = payload.summary.by_node_type as
      | Record<string, number>
      | undefined;
    impactSummary.innerHTML = `
      <div class="grid gap-3 sm:grid-cols-2">
        <article class="rounded-2xl border border-stone-200 bg-stone-50 px-4 py-4 text-sm text-stone-700">Matches: <strong class="text-stone-950">${escapeHtml(String(payload.summary.match_count ?? 0))}</strong></article>
        <article class="rounded-2xl border border-stone-200 bg-stone-50 px-4 py-4 text-sm text-stone-700">Impacted: <strong class="text-stone-950">${escapeHtml(String(payload.summary.impacted_count ?? 0))}</strong></article>
      </div>
      <article class="rounded-2xl border border-stone-200 bg-white px-4 py-4 text-sm text-stone-700">
        ${
          byNodeType && Object.keys(byNodeType).length
            ? Object.entries(byNodeType)
                .map(
                  ([key, value]) =>
                    `${escapeHtml(key)}: ${escapeHtml(String(value))}`,
                )
                .join(" · ")
            : "No nearby impacted node types."
        }
      </article>
    `;
  }

  const centerX = 260;
  const centerY = 175;
  const hubId = `impact:${payload.target}`;
  const nodes: GraphCanvasNode[] = [
    {
      id: hubId,
      label: payload.target,
      type: "target",
      x: centerX,
      y: centerY,
      radius: 24,
      metadata: { target: payload.target },
      emphasis: "hub",
    },
  ];
  const edges: GraphCanvasEdge[] = [];

  payload.matches.forEach((match, index) => {
    const angle =
      -Math.PI / 2 +
      (Math.PI * 2 * index) / Math.max(payload.matches.length, 1);
    const nodeId = match.id || `match:${match.node_type}:${match.name}`;
    nodes.push({
      id: nodeId,
      label: match.name,
      type: match.node_type,
      x: centerX + Math.cos(angle) * 76,
      y: centerY + Math.sin(angle) * 76,
      radius: 16,
      metadata: match.metadata,
      emphasis: "seed",
    });
    edges.push({ from: hubId, to: nodeId, color: "rgba(2,132,199,0.28)" });
  });

  const upstream = payload.impacted.filter(
    (item) => item.direction === "upstream",
  );
  const downstream = payload.impacted.filter(
    (item) => item.direction !== "upstream",
  );

  upstream.forEach((item, index) => {
    const distance = typeof item.distance === "number" ? item.distance : 1;
    const nodeId = item.id || `impact:${item.node_type}:${item.name}:up`;
    nodes.push({
      id: nodeId,
      label: item.name,
      type: item.node_type,
      x: 120 + (distance - 1) * 56,
      y: 88 + index * 42,
      radius: 14,
      metadata: item.metadata,
      direction: item.direction,
      distance,
      emphasis: "result",
    });
    edges.push({ from: hubId, to: nodeId, color: "rgba(220,38,38,0.25)" });
  });

  downstream.forEach((item, index) => {
    const distance = typeof item.distance === "number" ? item.distance : 1;
    const nodeId = item.id || `impact:${item.node_type}:${item.name}:down`;
    nodes.push({
      id: nodeId,
      label: item.name,
      type: item.node_type,
      x: 400 + (distance - 1) * 44,
      y: 88 + index * 42,
      radius: 14,
      metadata: item.metadata,
      direction: item.direction,
      distance,
      emphasis: "result",
    });
    edges.push({ from: hubId, to: nodeId, color: "rgba(14,165,233,0.25)" });
  });

  impactGraphState = {
    emptyMessage: "No impact path found.",
    nodes,
    edges,
    selectedNodeId: payload.matches[0]?.id ?? payload.impacted[0]?.id ?? hubId,
  };
  drawGraphCanvas(impactCanvas, impactGraphState);
  renderNodeLegend(impactLegend, impactGraphState.nodes);
  renderNodeDetails(
    impactDetails,
    impactGraphState,
    "Select a node in the impact graph to inspect its details.",
  );
}

searchForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!activeRepositoryId) {
    setText(searchStatus, "Select a repository first.");
    return;
  }
  const query = searchQueryInput?.value.trim() ?? "";
  if (!query) {
    setText(searchStatus, "Enter a search query.");
    return;
  }
  const nodeTypes = (searchTypesInput?.value ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  setText(searchStatus, "Searching graph...");
  try {
    const payload = await searchRepositoryGraph(
      activeRepositoryId,
      query,
      nodeTypes,
      12,
    );
    searchGraphState = buildSearchCanvasState(query, payload.results);
    drawGraphCanvas(searchCanvas, searchGraphState);
    renderNodeLegend(searchLegend, searchGraphState.nodes);
    renderNodeDetails(
      searchDetails,
      searchGraphState,
      "Select a node in the search graph to inspect its details.",
    );
    setText(searchStatus, `${payload.count} matches returned.`);
  } catch (error) {
    searchGraphState = {
      emptyMessage: error instanceof Error ? error.message : "Search failed.",
      nodes: [],
      edges: [],
      selectedNodeId: null,
    };
    drawGraphCanvas(searchCanvas, searchGraphState);
    renderNodeLegend(searchLegend, []);
    renderNodeDetails(searchDetails, searchGraphState, "Search failed.");
    setText(searchStatus, "Search failed.");
  }
});

impactForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!activeRepositoryId) {
    setText(impactStatus, "Select a repository first.");
    return;
  }
  const target = impactTargetInput?.value.trim() ?? "";
  if (!target) {
    setText(impactStatus, "Enter a target symbol or route.");
    return;
  }
  const depth = Number.parseInt(impactDepthInput?.value ?? "2", 10);
  const limit = Number.parseInt(impactLimitInput?.value ?? "25", 10);
  setText(impactStatus, "Running impact scan...");
  try {
    const payload = await getRepositoryGraphImpact(
      activeRepositoryId,
      target,
      depth,
      limit,
    );
    renderImpact(payload);
    setText(
      impactStatus,
      `${payload.summary.impacted_count ?? 0} impacted nodes found.`,
    );
  } catch (error) {
    renderEmptyRegion(
      impactSummary,
      error instanceof Error ? error.message : "Impact scan failed.",
    );
    impactGraphState = {
      emptyMessage:
        error instanceof Error ? error.message : "Impact scan failed.",
      nodes: [],
      edges: [],
      selectedNodeId: null,
    };
    drawGraphCanvas(impactCanvas, impactGraphState);
    renderNodeLegend(impactLegend, []);
    renderNodeDetails(impactDetails, impactGraphState, "Impact scan failed.");
    setText(impactStatus, "Impact scan failed.");
  }
});

attachCanvasInteraction(
  searchCanvas,
  () => searchGraphState,
  (state) => {
    searchGraphState = state;
  },
  searchDetails,
  "Select a node in the search graph to inspect its details.",
);
attachCanvasInteraction(
  impactCanvas,
  () => impactGraphState,
  (state) => {
    impactGraphState = state;
  },
  impactDetails,
  "Select a node in the impact graph to inspect its details.",
);

window.addEventListener("resize", () => {
  drawGraphCanvas(searchCanvas, searchGraphState);
  drawGraphCanvas(impactCanvas, impactGraphState);
});

drawGraphCanvas(searchCanvas, searchGraphState);
drawGraphCanvas(impactCanvas, impactGraphState);
renderNodeLegend(searchLegend, []);
renderNodeLegend(impactLegend, []);
renderNodeDetails(
  searchDetails,
  searchGraphState,
  "Run a graph search to visualize matching nodes.",
);
renderNodeDetails(
  impactDetails,
  impactGraphState,
  "Run an impact scan to visualize nearby graph nodes.",
);

refreshButton?.addEventListener("click", () => {
  void loadRepositories();
});

void loadRepositories();
