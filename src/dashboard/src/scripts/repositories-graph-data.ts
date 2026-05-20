import {
  type RepositoryGraphResultNodePayload,
  type RepositoryGraphScopePayload,
  type RepositoryGraphEdgePayload,
} from "../lib/api/admin";
import {
  type SimNode,
  type SimEdge,
  colorForType,
  radiusForType,
} from "./graph-renderer";

export interface ExtendedNodePayload extends RepositoryGraphResultNodePayload {
  direction?: string;
  distance?: number;
  emphasis?: "seed" | "result" | "hub";
}

interface BuildResult {
  nodes: SimNode[];
  edges: SimEdge[];
}

export function meta(m: Record<string, unknown>, key: string): string | null {
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

function scopeNodeId(scope: RepositoryGraphScopePayload): string {
  return `scope:${scope.repo_id}:${scope.branch ?? "default"}`;
}

function scopeLabel(scope: RepositoryGraphScopePayload): string {
  return scope.branch
    ? `${scope.repo_name} · ${scope.branch}`
    : scope.repo_name;
}

export function isLinkedResultNode(node: ExtendedNodePayload): boolean {
  return Number(node.landscape_distance ?? 0) > 0;
}

const EDGE_STYLES: Record<string, { color: string }> = {
  depends_on: { color: "#f59e0b" },
  calls: { color: "#60a5fa" },
  imports: { color: "#34d399" },
  shares_contracts: { color: "#a78bfa" },
};

export function buildScopedResultGraphData(
  primaryRepoName: string,
  apiNodes: ExtendedNodePayload[],
  scopes: RepositoryGraphScopePayload[],
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
  > = [],
): BuildResult {
  const normalizedScopes =
    scopes.length > 0
      ? scopes
      : [
          {
            repo_id: primaryRepoName,
            repo_name: primaryRepoName,
            repo_path: null,
            branch: null,
            distance: 0,
            via_link: null,
          },
        ];
  const primaryScope = normalizedScopes[0];
  const primaryScopeId = scopeNodeId(primaryScope);
  const nodeMap = new Map<string, SimNode>();
  const edgeMap = new Map<string, SimEdge>();
  const scopeLookup = new Map(
    normalizedScopes.map((scope) => [
      `${scope.repo_name}::${scope.branch ?? ""}`,
      scope,
    ]),
  );
  const nodeIdLookup = new Map<string, string>();

  for (const scope of normalizedScopes) {
    const currentScopeId = scopeNodeId(scope);
    const viaLink =
      scope.via_link && typeof scope.via_link === "object"
        ? scope.via_link
        : null;
    nodeMap.set(currentScopeId, {
      id: currentScopeId,
      label: scopeLabel(scope),
      type: "repository",
      radius: radiusForType("repository"),
      color: colorForType("repository"),
      metadata: {
        repo_name: scope.repo_name,
        branch: scope.branch ?? "",
        landscape_distance: scope.distance,
        relation: viaLink?.relation ?? null,
        direction: viaLink?.direction ?? null,
      },
      emphasis: scope.distance === 0 ? "hub" : undefined,
    });
    if (scope.distance > 0) {
      const relation =
        typeof viaLink?.relation === "string" ? viaLink.relation : "depends_on";
      const direction =
        typeof viaLink?.direction === "string" ? viaLink.direction : "outbound";
      const edgeFrom =
        direction === "inbound" ? currentScopeId : primaryScopeId;
      const edgeTo = direction === "inbound" ? primaryScopeId : currentScopeId;
      edgeMap.set(`scope-link:${edgeFrom}:${edgeTo}:${relation}`, {
        id: `scope-link:${edgeFrom}:${edgeTo}:${relation}`,
        source: edgeFrom,
        target: edgeTo,
        relation,
        dashed: true,
        edgeColor: EDGE_STYLES[relation]?.color ?? "#f59e0b",
      });
    }
  }

  for (const node of apiNodes) {
    const resolvedScope =
      scopeLookup.get(
        `${node.repo_name ?? primaryRepoName}::${node.branch ?? ""}`,
      ) ?? primaryScope;
    const resolvedScopeId = scopeNodeId(resolvedScope);
    const scopedNodeId = `${resolvedScopeId}:${node.id}`;
    nodeIdLookup.set(node.id, scopedNodeId);
    nodeMap.set(scopedNodeId, {
      id: scopedNodeId,
      label: isLinkedResultNode(node)
        ? `${node.repo_name ?? resolvedScope.repo_name} · ${node.name}`
        : node.name,
      type: node.node_type,
      radius: radiusForType(node.node_type),
      color: colorForType(node.node_type),
      metadata: {
        ...node.metadata,
        repo_name: node.repo_name ?? resolvedScope.repo_name,
        branch: node.branch ?? resolvedScope.branch ?? "",
        landscape_distance: node.landscape_distance ?? resolvedScope.distance,
        via_link: node.via_link ?? resolvedScope.via_link ?? null,
      },
      emphasis: node.emphasis,
      score: node.score,
      direction: node.direction,
      distance: node.distance,
    });
    edgeMap.set(`scope-contains:${resolvedScopeId}:${scopedNodeId}`, {
      id: `scope-contains:${resolvedScopeId}:${scopedNodeId}`,
      source: resolvedScopeId,
      target: scopedNodeId,
      relation: "contains",
    });
  }

  for (const edge of apiEdges) {
    let id: string;
    let from: string;
    let to: string;
    let relation: string | undefined;
    let dashed: boolean | undefined;
    let edgeColor: string | undefined;

    if ("source_id" in edge) {
      id = edge.id;
      from = edge.source_id;
      to = edge.target_id;
      relation = edge.relation;
    } else {
      id = edge.id;
      from = edge.from;
      to = edge.to;
      relation = edge.relation;
      dashed = edge.dashed;
      edgeColor = edge.color;
    }

    const scopedFrom = nodeIdLookup.get(from);
    const scopedTo = nodeIdLookup.get(to);
    if (scopedFrom && scopedTo) {
      edgeMap.set(id, {
        id,
        source: scopedFrom,
        target: scopedTo,
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

export function buildGraphData(
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
