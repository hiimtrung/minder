import {
  deleteRepository,
  getRepositoryGraphImpact,
  getRepositoryGraphMap,
  getRepositoryGraphSummary,
  listRepositories,
  searchRepositoryGraph,
  updateRepository,
  type RepositoryGraphEdgePayload,
  type RepositoryGraphImpactPayload,
  type RepositoryGraphMapPayload,
  type RepositoryGraphNodePayload,
  type RepositoryGraphSummaryPayload,
  type RepositoryPayload,
} from "../lib/api/admin";

type GraphCanvasNode = {
  id: string;
  label: string;
  type: string;
  x: number;
  y: number;
  radius: number;
  metadata: Record<string, unknown>;
  emphasis?: "hub" | "seed" | "result";
  score?: number;
  direction?: string;
  distance?: number;
};

type GraphCanvasEdge = {
  id: string;
  from: string;
  to: string;
  relation?: string;
  dashed?: boolean;
  color?: string;
};

type GraphCanvasState = {
  emptyMessage: string;
  nodes: GraphCanvasNode[];
  edges: GraphCanvasEdge[];
  selectedNodeId: string | null;
};

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
const repoGraphRefreshButton = document.querySelector("#repo-graph-refresh");
const repoGraphStatus = document.querySelector("#repo-graph-status");
const repoGraphSummary = document.querySelector("#repo-graph-summary");
const repoGraphCanvas = document.querySelector(
  "#repo-graph-canvas",
) as HTMLCanvasElement | null;
const repoGraphLegend = document.querySelector("#repo-graph-legend");
const repoGraphDetails = document.querySelector("#repo-graph-details");
const repoSettingsForm = document.querySelector(
  "#repo-settings-form",
) as HTMLFormElement | null;
const repoSettingsName = document.querySelector(
  "#repo-settings-name",
) as HTMLInputElement | null;
const repoSettingsRemote = document.querySelector(
  "#repo-settings-remote",
) as HTMLInputElement | null;
const repoSettingsBranch = document.querySelector(
  "#repo-settings-branch",
) as HTMLInputElement | null;
const repoSettingsPath = document.querySelector(
  "#repo-settings-path",
) as HTMLInputElement | null;
const repoSettingsStatus = document.querySelector("#repo-settings-status");
const repoSettingsDeleteButton = document.querySelector(
  "#repo-settings-delete",
) as HTMLButtonElement | null;
const searchForm = document.querySelector(
  "#graph-search-form",
) as HTMLFormElement | null;
const searchQueryInput = document.querySelector(
  "#graph-search-query",
) as HTMLInputElement | null;
const searchTypesInput = document.querySelector(
  "#graph-search-types",
) as HTMLInputElement | null;
const searchLanguagesInput = document.querySelector(
  "#graph-search-languages",
) as HTMLInputElement | null;
const searchStatesInput = document.querySelector(
  "#graph-search-states",
) as HTMLInputElement | null;
const searchStatus = document.querySelector("#graph-search-status");
const searchCanvas = document.querySelector(
  "#graph-search-canvas",
) as HTMLCanvasElement | null;
const searchLegend = document.querySelector("#graph-search-legend");
const searchDetails = document.querySelector("#graph-search-details");
const impactForm = document.querySelector(
  "#graph-impact-form",
) as HTMLFormElement | null;
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

const NODE_TYPE_COLORS: Record<string, string> = {
  repository: "#0f766e",
  folder: "#4f46e5",
  file: "#2563eb",
  module: "#7c3aed",
  service: "#9333ea",
  controller: "#0d9488",
  class: "#d97706",
  function: "#059669",
  interface: "#db2777",
  route: "#e11d48",
  todo: "#dc2626",
  external_service_api: "#a21caf",
  query: "#f97316",
  target: "#f43f5e",
};

const NODE_TYPE_SIZES: Record<string, number> = {
  repository: 18,
  folder: 11,
  file: 8,
  module: 12,
  service: 14,
  controller: 9,
  class: 8,
  function: 6,
  interface: 7,
  route: 6,
  todo: 5,
  external_service_api: 6,
  query: 10,
  target: 10,
};

const EDGE_RELATION_STYLES: Record<
  string,
  { color: string; dashed?: boolean }
> = {
  contains: { color: "rgba(37,99,235,0.28)" },
  imports: { color: "rgba(79,70,229,0.32)" },
  calls: { color: "rgba(147,51,234,0.34)" },
  defines: { color: "rgba(13,148,136,0.32)" },
  depends_on: { color: "rgba(225,29,72,0.36)", dashed: true },
  upstream: { color: "rgba(220,38,38,0.32)", dashed: true },
  downstream: { color: "rgba(14,165,233,0.32)", dashed: true },
  search_match: { color: "rgba(249,115,22,0.34)" },
};

let repositories: RepositoryPayload[] = [];
let activeRepositoryId: string | null = null;
let activeRepository: RepositoryPayload | null = null;

let repositoryGraphState: GraphCanvasState = {
  emptyMessage: "Select a repository to render its graph.",
  nodes: [],
  edges: [],
  selectedNodeId: null,
};
let searchGraphState: GraphCanvasState = {
  emptyMessage: "Search results will render here.",
  nodes: [],
  edges: [],
  selectedNodeId: null,
};
let impactGraphState: GraphCanvasState = {
  emptyMessage: "Impact graph will render here.",
  nodes: [],
  edges: [],
  selectedNodeId: null,
};

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setText(element: Element | null, value: string): void {
  if (element) {
    element.textContent = value;
  }
}

function metadataString(
  metadata: Record<string, unknown>,
  key: string,
): string | null {
  const value = metadata[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function colorForNodeType(nodeType: string): string {
  return NODE_TYPE_COLORS[nodeType] ?? "#57534e";
}

function radiusForNodeType(nodeType: string): number {
  return NODE_TYPE_SIZES[nodeType] ?? 6;
}

function normalizeLabel(label: string, limit = 30): string {
  return label.length <= limit ? label : `${label.slice(0, limit - 1)}…`;
}

function splitCsv(value: string | null | undefined): string[] {
  return (value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function lastSyncLabel(summary: RepositoryGraphSummaryPayload): string {
  const lastSync = summary.last_sync;
  if (!lastSync || typeof lastSync.accepted_at !== "string") {
    return summary.graph_available ? "Graph Ready" : "No Sync";
  }
  const acceptedAt = new Date(lastSync.accepted_at);
  if (Number.isNaN(acceptedAt.getTime())) {
    return "Graph Ready";
  }
  return `Synced ${acceptedAt.toLocaleString()}`;
}

function renderEmptyCollection(element: Element | null, message: string): void {
  if (!element) {
    return;
  }
  element.innerHTML = `<div class="rounded-2xl border border-dashed border-stone-300 bg-white px-4 py-4 text-sm text-stone-500">${escapeHtml(message)}</div>`;
}

function renderNodeCollection(
  element: Element | null,
  nodes: RepositoryGraphNodePayload[],
  emptyMessage: string,
): void {
  if (!element) {
    return;
  }
  if (!nodes.length) {
    renderEmptyCollection(element, emptyMessage);
    return;
  }
  element.innerHTML = nodes
    .map((node) => {
      const path = metadataString(node.metadata, "path");
      const language = metadataString(node.metadata, "language");
      return `
        <article class="rounded-2xl border border-stone-200 bg-white px-4 py-3">
          <p class="text-xs font-semibold uppercase tracking-[0.2em] text-stone-500">${escapeHtml(node.node_type)}</p>
          <p class="mt-2 text-sm font-semibold text-stone-900">${escapeHtml(node.name)}</p>
          <p class="mt-2 text-xs text-stone-600">${escapeHtml(path ?? language ?? "No extra metadata")}</p>
        </article>
      `;
    })
    .join("");
}

function renderDependencies(summary: RepositoryGraphSummaryPayload): void {
  if (!dependenciesRegion) {
    return;
  }
  if (!summary.dependencies.length) {
    renderEmptyCollection(
      dependenciesRegion,
      "No service dependency edges in the current graph snapshot.",
    );
    return;
  }
  dependenciesRegion.innerHTML = summary.dependencies
    .map((dependency) => {
      const targets = dependency.depends_on
        .map((target) => escapeHtml(target.name))
        .join(", ");
      return `
        <article class="rounded-2xl border border-stone-200 bg-white px-4 py-3">
          <p class="text-xs font-semibold uppercase tracking-[0.2em] text-stone-500">Service</p>
          <p class="mt-2 text-sm font-semibold text-stone-900">${escapeHtml(dependency.service)}</p>
          <p class="mt-2 text-xs text-stone-600">${targets || "No dependency targets"}</p>
        </article>
      `;
    })
    .join("");
}

function renderSummary(summary: RepositoryGraphSummaryPayload): void {
  setText(summaryTitle, summary.repository.name);
  setText(
    summaryMeta,
    `${summary.repository.remote_url ?? "No remote configured"} · ${summary.repository.default_branch ?? "No default branch"}`,
  );
  setText(summarySync, lastSyncLabel(summary));

  if (summaryCards) {
    const items = [
      ["Nodes", String(summary.node_count)],
      ["Types", String(Object.keys(summary.counts_by_type).length)],
      ["Routes", String(summary.routes.length)],
      ["TODOs", String(summary.todos.length)],
    ];
    summaryCards.innerHTML = items
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

  renderNodeCollection(
    routesRegion,
    summary.routes,
    "No route nodes found in the current snapshot.",
  );
  renderNodeCollection(
    todosRegion,
    summary.todos,
    "No TODO nodes found in the current snapshot.",
  );
  renderNodeCollection(
    servicesRegion,
    summary.external_services,
    "No external service nodes found in the current snapshot.",
  );
  renderDependencies(summary);
}

function layerForNodeType(nodeType: string): number {
  switch (nodeType) {
    case "repository":
      return 0;
    case "folder":
      return 1;
    case "file":
      return 2;
    case "module":
    case "service":
    case "controller":
    case "class":
    case "interface":
      return 3;
    default:
      return 4;
  }
}

function folderAncestors(paths: string[]): string[] {
  const folders = new Set<string>();
  for (const path of paths) {
    const segments = path.split("/").filter(Boolean);
    for (let index = 1; index < segments.length; index += 1) {
      folders.add(segments.slice(0, index).join("/"));
    }
  }
  return [...folders].sort((left, right) => left.localeCompare(right));
}

function buildStructuredCanvasState(
  repoName: string,
  nodes: Array<
    RepositoryGraphNodePayload & {
      score?: number;
      direction?: string;
      distance?: number;
      emphasis?: "seed" | "result";
    }
  >,
  edges: RepositoryGraphEdgePayload[] | GraphCanvasEdge[],
  emptyMessage: string,
): GraphCanvasState {
  const graphNodes = new Map<string, GraphCanvasNode>();
  const graphEdges = new Map<string, GraphCanvasEdge>();

  graphNodes.set("repository-root", {
    id: "repository-root",
    label: repoName,
    type: "repository",
    x: 0,
    y: 0,
    radius: radiusForNodeType("repository"),
    metadata: {},
    emphasis: "hub",
  });

  const paths = nodes
    .map((node) => metadataString(node.metadata, "path"))
    .filter((value): value is string => Boolean(value));

  for (const folderPath of folderAncestors(paths)) {
    const segments = folderPath.split("/").filter(Boolean);
    const folderId = `folder:${folderPath}`;
    const parentId =
      segments.length > 1
        ? `folder:${segments.slice(0, -1).join("/")}`
        : "repository-root";
    graphNodes.set(folderId, {
      id: folderId,
      label: segments[segments.length - 1] ?? folderPath,
      type: "folder",
      x: 0,
      y: 0,
      radius: radiusForNodeType("folder"),
      metadata: { path: folderPath },
    });
    graphEdges.set(`contains:${parentId}:${folderId}`, {
      id: `contains:${parentId}:${folderId}`,
      from: parentId,
      to: folderId,
      relation: "contains",
    });
  }

  const fileNodeIdsByPath = new Map<string, string>();
  for (const node of nodes) {
    const path = metadataString(node.metadata, "path");
    if (node.node_type === "file" && path) {
      fileNodeIdsByPath.set(path, node.id);
    }
  }

  for (const path of paths) {
    if (fileNodeIdsByPath.has(path)) {
      continue;
    }
    const segments = path.split("/").filter(Boolean);
    const fileId = `file:${path}`;
    const parentId =
      segments.length > 1
        ? `folder:${segments.slice(0, -1).join("/")}`
        : "repository-root";
    graphNodes.set(fileId, {
      id: fileId,
      label: segments[segments.length - 1] ?? path,
      type: "file",
      x: 0,
      y: 0,
      radius: radiusForNodeType("file"),
      metadata: { path },
    });
    graphEdges.set(`contains:${parentId}:${fileId}`, {
      id: `contains:${parentId}:${fileId}`,
      from: parentId,
      to: fileId,
      relation: "contains",
    });
  }

  for (const node of nodes) {
    graphNodes.set(node.id, {
      id: node.id,
      label: node.name,
      type: node.node_type,
      x: 0,
      y: 0,
      radius: radiusForNodeType(node.node_type),
      metadata: node.metadata,
      emphasis: node.emphasis,
      score: node.score,
      direction: node.direction,
      distance: node.distance,
    });

    const path = metadataString(node.metadata, "path");
    if (!path) {
      continue;
    }
    const parentId =
      node.node_type === "file"
        ? path.includes("/")
          ? `folder:${path.split("/").slice(0, -1).join("/")}`
          : "repository-root"
        : (fileNodeIdsByPath.get(path) ?? `file:${path}`);
    if (graphNodes.has(parentId)) {
      graphEdges.set(`contains:${parentId}:${node.id}`, {
        id: `contains:${parentId}:${node.id}`,
        from: parentId,
        to: node.id,
        relation: "contains",
      });
    }
  }

  for (const edge of edges) {
    const normalized =
      "source_id" in edge
        ? {
            id: edge.id,
            from: edge.source_id,
            to: edge.target_id,
            relation: edge.relation,
          }
        : edge;
    if (!graphNodes.has(normalized.from) || !graphNodes.has(normalized.to)) {
      continue;
    }
    graphEdges.set(normalized.id, normalized);
  }

  const layers = new Map<number, GraphCanvasNode[]>();
  for (const node of graphNodes.values()) {
    const layer = layerForNodeType(node.type);
    const bucket = layers.get(layer) ?? [];
    bucket.push(node);
    layers.set(layer, bucket);
  }
  for (const [layer, bucket] of layers) {
    bucket.sort((left, right) => left.label.localeCompare(right.label));
    const x = 140 + layer * 190;
    const gap = 84;
    const totalHeight = Math.max(1, bucket.length - 1) * gap;
    const startY = 120 + Math.max(0, 420 - totalHeight / 2);
    bucket.forEach((node, index) => {
      node.x = x;
      node.y = startY + index * gap;
    });
  }

  return {
    emptyMessage,
    nodes: [...graphNodes.values()],
    edges: [...graphEdges.values()],
    selectedNodeId: null,
  };
}

function renderLegend(element: Element | null, state: GraphCanvasState): void {
  if (!element) {
    return;
  }
  const counts = new Map<string, number>();
  for (const node of state.nodes) {
    counts.set(node.type, (counts.get(node.type) ?? 0) + 1);
  }
  if (!counts.size) {
    element.innerHTML = `<p class="text-sm text-stone-500">No graph loaded.</p>`;
    return;
  }
  element.innerHTML = [...counts.entries()]
    .sort((left, right) => left[0].localeCompare(right[0]))
    .map(
      ([type, count]) => `
        <div class="flex items-center justify-between gap-3 py-1 text-sm text-stone-700">
          <span class="inline-flex items-center gap-2">
            <span class="h-2.5 w-2.5 rounded-full" style="background:${escapeHtml(colorForNodeType(type))}"></span>
            ${escapeHtml(type)}
          </span>
          <span class="font-semibold text-stone-900">${count}</span>
        </div>
      `,
    )
    .join("");
}

function renderNodeDetails(
  element: Element | null,
  state: GraphCanvasState,
): void {
  if (!element) {
    return;
  }
  const selected =
    state.nodes.find((node) => node.id === state.selectedNodeId) ?? null;
  if (!selected) {
    element.innerHTML = `<p class="text-sm text-stone-500">Click a node to inspect its metadata.</p>`;
    return;
  }
  const metadataRows = Object.entries(selected.metadata)
    .filter(
      ([, value]) => value !== null && value !== undefined && value !== "",
    )
    .slice(0, 12)
    .map(
      ([key, value]) => `
        <div class="grid gap-1 border-t border-stone-100 py-2 first:border-t-0 first:pt-0">
          <span class="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500">${escapeHtml(key)}</span>
          <span class="text-sm text-stone-800">${escapeHtml(String(value))}</span>
        </div>
      `,
    )
    .join("");
  element.innerHTML = `
    <div>
      <p class="text-xs font-semibold uppercase tracking-[0.2em] text-stone-500">${escapeHtml(selected.type)}</p>
      <h3 class="mt-2 text-lg font-semibold text-stone-950">${escapeHtml(selected.label)}</h3>
      ${selected.score ? `<p class="mt-2 text-sm text-stone-600">Score ${selected.score}</p>` : ""}
      ${selected.direction ? `<p class="mt-1 text-sm text-stone-600">${escapeHtml(selected.direction)} · distance ${escapeHtml(String(selected.distance ?? 1))}</p>` : ""}
    </div>
    <div class="mt-4">${metadataRows || '<p class="text-sm text-stone-500">No metadata available.</p>'}</div>
  `;
}

function drawGraphCanvas(
  canvas: HTMLCanvasElement | null,
  state: GraphCanvasState,
): void {
  if (!canvas) {
    return;
  }
  const context = canvas.getContext("2d");
  if (!context) {
    return;
  }

  const width = canvas.clientWidth || 900;
  const height = canvas.clientHeight || 420;
  const scale = window.devicePixelRatio || 1;
  canvas.width = Math.floor(width * scale);
  canvas.height = Math.floor(height * scale);
  context.setTransform(scale, 0, 0, scale, 0, 0);
  context.clearRect(0, 0, width, height);

  if (!state.nodes.length) {
    context.fillStyle = "#78716c";
    context.font = "16px ui-sans-serif, system-ui, sans-serif";
    context.textAlign = "center";
    context.fillText(state.emptyMessage, width / 2, height / 2);
    return;
  }

  for (const edge of state.edges) {
    const source = state.nodes.find((node) => node.id === edge.from);
    const target = state.nodes.find((node) => node.id === edge.to);
    if (!source || !target) {
      continue;
    }
    const style = EDGE_RELATION_STYLES[edge.relation ?? ""];
    context.save();
    context.strokeStyle =
      edge.color ?? style?.color ?? "rgba(120,113,108,0.25)";
    context.lineWidth = 1.2;
    context.setLineDash((edge.dashed ?? style?.dashed) ? [6, 6] : []);
    context.beginPath();
    context.moveTo(source.x, source.y);
    context.lineTo(target.x, target.y);
    context.stroke();
    context.restore();
  }

  for (const node of state.nodes) {
    context.save();
    const selected = node.id === state.selectedNodeId;
    context.fillStyle = colorForNodeType(node.type);
    context.shadowColor = selected
      ? "rgba(15,23,42,0.25)"
      : "rgba(15,23,42,0.12)";
    context.shadowBlur = selected ? 18 : 10;
    context.beginPath();
    context.arc(
      node.x,
      node.y,
      selected ? node.radius + 2 : node.radius,
      0,
      Math.PI * 2,
    );
    context.fill();
    context.restore();

    context.save();
    context.fillStyle = "#1c1917";
    context.font =
      node.type === "repository"
        ? "600 13px ui-sans-serif, system-ui, sans-serif"
        : "12px ui-sans-serif, system-ui, sans-serif";
    context.textAlign = "center";
    context.fillText(
      normalizeLabel(node.label),
      node.x,
      node.y + node.radius + 16,
    );
    context.restore();
  }
}

function bindCanvasInteraction(
  canvas: HTMLCanvasElement | null,
  getState: () => GraphCanvasState,
  onChange: () => void,
): void {
  if (!canvas) {
    return;
  }
  canvas.addEventListener("click", (event) => {
    const state = getState();
    if (!state.nodes.length) {
      return;
    }
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    let nextSelected: string | null = null;
    for (const node of state.nodes) {
      const distance = Math.hypot(node.x - x, node.y - y);
      if (distance <= node.radius + 6) {
        nextSelected = node.id;
        break;
      }
    }
    state.selectedNodeId = nextSelected;
    onChange();
  });
}

function renderRepositoryGraph(): void {
  renderLegend(repoGraphLegend, repositoryGraphState);
  renderNodeDetails(repoGraphDetails, repositoryGraphState);
  drawGraphCanvas(repoGraphCanvas, repositoryGraphState);
}

function renderSearchGraph(): void {
  renderLegend(searchLegend, searchGraphState);
  renderNodeDetails(searchDetails, searchGraphState);
  drawGraphCanvas(searchCanvas, searchGraphState);
}

function renderImpactGraph(): void {
  renderLegend(impactLegend, impactGraphState);
  renderNodeDetails(impactDetails, impactGraphState);
  drawGraphCanvas(impactCanvas, impactGraphState);
}

function renderRepositoryGraphSummary(
  payload: RepositoryGraphMapPayload,
): void {
  if (!repoGraphSummary) {
    return;
  }
  const items = [
    ["Visible Nodes", String(payload.summary.node_count)],
    ["Visible Edges", String(payload.summary.edge_count)],
    ["Node Types", String(Object.keys(payload.summary.counts_by_type).length)],
    [
      "Relations",
      String(Object.keys(payload.summary.counts_by_relation).length),
    ],
  ];
  repoGraphSummary.innerHTML = items
    .map(
      ([label, value]) => `
        <article class="rounded-2xl border border-stone-200 bg-stone-50 px-4 py-3">
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">${escapeHtml(label)}</p>
          <p class="mt-2 text-2xl font-semibold text-stone-950">${escapeHtml(value)}</p>
        </article>
      `,
    )
    .join("");
}

function renderRepositories(): void {
  if (!repositoriesList) {
    return;
  }
  if (!repositories.length) {
    repositoriesList.innerHTML = `<article class="rounded-3xl border border-stone-200 bg-stone-50 px-4 py-4 text-sm text-stone-600">No repositories found.</article>`;
    return;
  }
  repositoriesList.innerHTML = repositories
    .map((repository) => {
      const isActive = repository.id === activeRepositoryId;
      return `
        <button
          type="button"
          data-repository-id="${escapeHtml(repository.id)}"
          class="rounded-3xl border px-4 py-4 text-left transition ${isActive ? "border-stone-950 bg-stone-950 text-white shadow-lg" : "border-stone-200 bg-white text-stone-800 hover:border-stone-400"}"
        >
          <p class="text-xs font-semibold uppercase tracking-[0.2em] ${isActive ? "text-stone-300" : "text-stone-500"}">Repository</p>
          <p class="mt-3 text-base font-semibold">${escapeHtml(repository.name)}</p>
          <p class="mt-2 text-xs ${isActive ? "text-stone-300" : "text-stone-500"}">${escapeHtml(repository.default_branch ?? "No branch")}</p>
          <p class="mt-2 text-xs ${isActive ? "text-stone-300" : "text-stone-500"}">${escapeHtml(repository.remote_url ?? repository.path)}</p>
        </button>
      `;
    })
    .join("");

  repositoriesList
    .querySelectorAll("[data-repository-id]")
    .forEach((element) => {
      element.addEventListener("click", () => {
        const repoId = element.getAttribute("data-repository-id");
        if (repoId) {
          void selectRepository(repoId);
        }
      });
    });
}

function populateRepositorySettings(
  repository: RepositoryPayload | null,
): void {
  if (
    !repoSettingsName ||
    !repoSettingsRemote ||
    !repoSettingsBranch ||
    !repoSettingsPath
  ) {
    return;
  }
  repoSettingsName.value = repository?.name ?? "";
  repoSettingsRemote.value = repository?.remote_url ?? "";
  repoSettingsBranch.value = repository?.default_branch ?? "";
  repoSettingsPath.value = repository?.path ?? "";
}

function resetRepositoryPanels(message: string): void {
  setText(summaryTitle, "Select a repository");
  setText(summaryMeta, message);
  setText(summarySync, "Waiting");
  if (summaryCards) {
    summaryCards.innerHTML = `<article class="rounded-3xl border border-stone-200 bg-stone-50 px-5 py-4 text-sm text-stone-600">${escapeHtml(message)}</article>`;
  }
  renderEmptyCollection(routesRegion, message);
  renderEmptyCollection(todosRegion, message);
  renderEmptyCollection(servicesRegion, message);
  renderEmptyCollection(dependenciesRegion, message);
  if (repoGraphSummary) {
    repoGraphSummary.innerHTML = "";
  }
  repositoryGraphState = {
    emptyMessage: message,
    nodes: [],
    edges: [],
    selectedNodeId: null,
  };
  searchGraphState = {
    emptyMessage: "Search results will render here.",
    nodes: [],
    edges: [],
    selectedNodeId: null,
  };
  impactGraphState = {
    emptyMessage: "Impact graph will render here.",
    nodes: [],
    edges: [],
    selectedNodeId: null,
  };
  renderRepositoryGraph();
  renderSearchGraph();
  renderImpactGraph();
  populateRepositorySettings(null);
}

async function loadRepositories(): Promise<void> {
  setText(repositoriesStatus, "Loading repositories...");
  try {
    const response = await listRepositories();
    repositories = response.repositories;
    if (!repositories.length) {
      activeRepositoryId = null;
      activeRepository = null;
      renderRepositories();
      resetRepositoryPanels("No repositories are registered yet.");
      setText(repositoriesStatus, "No repositories found.");
      return;
    }

    if (
      !activeRepositoryId ||
      !repositories.some((repo) => repo.id === activeRepositoryId)
    ) {
      activeRepositoryId = repositories[0]?.id ?? null;
    }
    activeRepository =
      repositories.find((repo) => repo.id === activeRepositoryId) ?? null;
    renderRepositories();
    setText(repositoriesStatus, `${repositories.length} repositories loaded.`);
    if (activeRepositoryId) {
      await selectRepository(activeRepositoryId);
    }
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to load repositories";
    setText(repositoriesStatus, message);
    resetRepositoryPanels(message);
  }
}

async function selectRepository(repoId: string): Promise<void> {
  activeRepositoryId = repoId;
  activeRepository = repositories.find((repo) => repo.id === repoId) ?? null;
  renderRepositories();
  populateRepositorySettings(activeRepository);
  setText(repoSettingsStatus, "");
  setText(searchStatus, "");
  setText(impactStatus, "");
  setText(repoGraphStatus, "Loading graph...");

  try {
    const [summary, graphMap] = await Promise.all([
      getRepositoryGraphSummary(repoId),
      getRepositoryGraphMap(repoId),
    ]);
    activeRepository = summary.repository;
    repositories = repositories.map((repository) =>
      repository.id === summary.repository.id ? summary.repository : repository,
    );
    renderRepositories();
    populateRepositorySettings(summary.repository);
    renderSummary(summary);
    renderRepositoryGraphSummary(graphMap);
    repositoryGraphState = buildStructuredCanvasState(
      summary.repository.name,
      graphMap.nodes,
      graphMap.edges,
      graphMap.graph_available
        ? "Graph loaded."
        : "This repository has no synced nodes yet.",
    );
    renderRepositoryGraph();
    setText(
      repoGraphStatus,
      graphMap.graph_available
        ? `${graphMap.summary.node_count} nodes and ${graphMap.summary.edge_count} edges loaded.`
        : "No synced graph snapshot for this repository yet.",
    );
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to load repository";
    resetRepositoryPanels(message);
    setText(repoGraphStatus, message);
  }
}

async function refreshActiveGraph(): Promise<void> {
  if (!activeRepositoryId) {
    return;
  }
  await selectRepository(activeRepositoryId);
}

function buildSearchState(
  repository: RepositoryPayload,
  nodes: Array<RepositoryGraphNodePayload & { score?: number }>,
): GraphCanvasState {
  return buildStructuredCanvasState(
    repository.name,
    nodes,
    [],
    "No graph search results yet.",
  );
}

function buildImpactState(
  repository: RepositoryPayload,
  payload: RepositoryGraphImpactPayload,
): GraphCanvasState {
  const matchNodes = payload.matches.map((node) => ({
    ...node,
    emphasis: "seed" as const,
  }));
  const impactedNodes = payload.impacted.map((node) => ({
    ...node,
    emphasis: "result" as const,
  }));
  const allNodes = [...matchNodes, ...impactedNodes];
  const edges: GraphCanvasEdge[] = [];
  const seeds = payload.matches.map((node) => node.id);
  for (const impacted of payload.impacted) {
    const seedId = seeds[0];
    if (!seedId) {
      continue;
    }
    edges.push({
      id: `${seedId}:${impacted.id}:${impacted.direction ?? "impact"}`,
      from: impacted.direction === "upstream" ? impacted.id : seedId,
      to: impacted.direction === "upstream" ? seedId : impacted.id,
      relation: impacted.direction === "upstream" ? "upstream" : "downstream",
      dashed: true,
    });
  }
  return buildStructuredCanvasState(
    repository.name,
    allNodes,
    edges,
    "No impact nodes yet.",
  );
}

async function handleSearchSubmit(event: SubmitEvent): Promise<void> {
  event.preventDefault();
  if (!activeRepositoryId || !searchQueryInput) {
    setText(searchStatus, "Select a repository first.");
    return;
  }
  const query = searchQueryInput.value.trim();
  if (!query) {
    setText(searchStatus, "Enter a search query.");
    return;
  }
  setText(searchStatus, "Searching graph...");
  try {
    const payload = await searchRepositoryGraph(activeRepositoryId, {
      query,
      nodeTypes: splitCsv(searchTypesInput?.value),
      languages: splitCsv(searchLanguagesInput?.value),
      lastStates: splitCsv(searchStatesInput?.value),
      limit: 18,
    });
    searchGraphState = buildSearchState(payload.repository, payload.results);
    renderSearchGraph();
    setText(searchStatus, `${payload.count} matching nodes.`);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Search failed";
    setText(searchStatus, message);
  }
}

async function handleImpactSubmit(event: SubmitEvent): Promise<void> {
  event.preventDefault();
  if (!activeRepositoryId || !impactTargetInput) {
    setText(impactStatus, "Select a repository first.");
    return;
  }
  const target = impactTargetInput.value.trim();
  if (!target) {
    setText(impactStatus, "Enter a target symbol or route.");
    return;
  }
  const depth = Math.max(
    1,
    Math.min(Number(impactDepthInput?.value ?? "2") || 2, 6),
  );
  const limit = Math.max(
    1,
    Math.min(Number(impactLimitInput?.value ?? "25") || 25, 100),
  );
  setText(impactStatus, "Analyzing impact...");
  try {
    const payload = await getRepositoryGraphImpact(
      activeRepositoryId,
      target,
      depth,
      limit,
    );
    impactGraphState = buildImpactState(payload.repository, payload);
    renderImpactGraph();
    if (impactSummary) {
      const summaryEntries = Object.entries(payload.summary)
        .map(
          ([key, value]) => `
          <article class="rounded-2xl border border-stone-200 bg-stone-50 px-4 py-3">
            <p class="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">${escapeHtml(key)}</p>
            <p class="mt-2 text-xl font-semibold text-stone-950">${escapeHtml(typeof value === "object" ? JSON.stringify(value) : String(value))}</p>
          </article>
        `,
        )
        .join("");
      impactSummary.innerHTML = summaryEntries;
    }
    setText(impactStatus, `${payload.impacted.length} impacted nodes loaded.`);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Impact scan failed";
    setText(impactStatus, message);
  }
}

async function handleRepositorySave(event: SubmitEvent): Promise<void> {
  event.preventDefault();
  if (
    !activeRepositoryId ||
    !repoSettingsName ||
    !repoSettingsRemote ||
    !repoSettingsBranch ||
    !repoSettingsPath
  ) {
    setText(repoSettingsStatus, "Select a repository first.");
    return;
  }
  setText(repoSettingsStatus, "Saving repository settings...");
  try {
    const response = await updateRepository(activeRepositoryId, {
      name: repoSettingsName.value.trim(),
      remote_url: repoSettingsRemote.value.trim(),
      default_branch: repoSettingsBranch.value.trim(),
      path: repoSettingsPath.value.trim(),
    });
    activeRepository = response.repository;
    repositories = repositories.map((repository) =>
      repository.id === response.repository.id
        ? response.repository
        : repository,
    );
    renderRepositories();
    populateRepositorySettings(response.repository);
    setText(repoSettingsStatus, "Repository updated.");
    await refreshActiveGraph();
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to update repository";
    setText(repoSettingsStatus, message);
  }
}

async function handleRepositoryDelete(): Promise<void> {
  if (!activeRepositoryId || !activeRepository) {
    setText(repoSettingsStatus, "Select a repository first.");
    return;
  }
  if (!window.confirm(`Delete repository ${activeRepository.name}?`)) {
    return;
  }
  setText(repoSettingsStatus, "Deleting repository...");
  try {
    await deleteRepository(activeRepositoryId);
    repositories = repositories.filter(
      (repository) => repository.id !== activeRepositoryId,
    );
    activeRepositoryId = repositories[0]?.id ?? null;
    activeRepository =
      repositories.find((repository) => repository.id === activeRepositoryId) ??
      null;
    renderRepositories();
    setText(repoSettingsStatus, "Repository deleted.");
    if (activeRepositoryId) {
      await selectRepository(activeRepositoryId);
    } else {
      resetRepositoryPanels("No repositories are registered yet.");
    }
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to delete repository";
    setText(repoSettingsStatus, message);
  }
}

bindCanvasInteraction(
  repoGraphCanvas,
  () => repositoryGraphState,
  renderRepositoryGraph,
);
bindCanvasInteraction(searchCanvas, () => searchGraphState, renderSearchGraph);
bindCanvasInteraction(impactCanvas, () => impactGraphState, renderImpactGraph);

refreshButton?.addEventListener("click", () => {
  void loadRepositories();
});

repoGraphRefreshButton?.addEventListener("click", () => {
  void refreshActiveGraph();
});

searchForm?.addEventListener("submit", (event) => {
  void handleSearchSubmit(event);
});

impactForm?.addEventListener("submit", (event) => {
  void handleImpactSubmit(event);
});

repoSettingsForm?.addEventListener("submit", (event) => {
  void handleRepositorySave(event);
});

repoSettingsDeleteButton?.addEventListener("click", () => {
  void handleRepositoryDelete();
});

window.addEventListener("resize", () => {
  renderRepositoryGraph();
  renderSearchGraph();
  renderImpactGraph();
});

void loadRepositories();
