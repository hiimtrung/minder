import {
  getAdminSession,
  getDashboardBootstrapState,
  getMetricsSummary,
  getServiceHealth,
  listAudit,
  listClients,
  listRepositories,
  listSkills,
  listUsers,
  listWorkflows,
  type AdminSessionPayload,
  type AuditEventPayload,
  type HealthStatus,
  type MetricsSummaryPayload,
} from "../lib/api/admin";

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------

function $<T extends HTMLElement>(id: string): T | null {
  return document.getElementById(id) as T | null;
}

function setText(id: string, text: string): void {
  const el = $(id);
  if (el) el.textContent = text;
}

function formatNumber(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString();
}

function formatPercent(
  numerator: number | undefined,
  denominator: number | undefined,
): string {
  if (!denominator) return "—";
  const pct = ((numerator ?? 0) / denominator) * 100;
  return `${pct.toFixed(1)}%`;
}

function formatRelativeTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const diffMs = Date.now() - d.getTime();
  const diffSec = Math.round(diffMs / 1000);
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.round(diffHr / 24);
  if (diffDay < 7) return `${diffDay}d ago`;
  return d.toLocaleDateString();
}

function escapeHtml(s: unknown): string {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ---------------------------------------------------------------------------
// Bootstrap — verify admin session or redirect
// ---------------------------------------------------------------------------

async function resolveSessionOrRedirect(): Promise<AdminSessionPayload | null> {
  try {
    const bootstrap = await getDashboardBootstrapState();
    if (!bootstrap.has_admin_users) {
      window.location.replace("/dashboard/setup");
      return null;
    }
    if (!bootstrap.has_admin_session) {
      window.location.replace("/dashboard/login");
      return null;
    }
    const { admin } = await getAdminSession();
    return admin;
  } catch {
    window.location.replace("/dashboard/login");
    return null;
  }
}

// ---------------------------------------------------------------------------
// Renderers
// ---------------------------------------------------------------------------

function renderHealth(health: HealthStatus): void {
  const dot = $("home-health-dot");
  const label = $("home-health-label");
  if (!dot || !label) return;
  dot.classList.remove("bg-emerald-500", "bg-red-500", "bg-stone-300");
  if (health.ok) {
    dot.classList.add("bg-emerald-500");
    label.textContent = `Healthy · ${health.latencyMs}ms`;
    label.className = "text-sm font-medium text-emerald-800";
  } else {
    dot.classList.add("bg-red-500");
    label.textContent =
      health.status === 0
        ? "Unreachable"
        : `Degraded · HTTP ${health.status}`;
    label.className = "text-sm font-medium text-red-700";
  }
}

function renderAdminLabel(admin: AdminSessionPayload): void {
  const name =
    admin.display_name?.trim() || admin.username || admin.email || "admin";
  setText("home-admin-label", `${name} · ${admin.role}`);
}

function renderInventory(counts: {
  clients: number;
  repositories: number;
  workflows: number;
  skills: number;
  users: number;
  activeUsers: number;
}): void {
  setText("home-count-clients", formatNumber(counts.clients));
  setText("home-count-repos", formatNumber(counts.repositories));
  setText("home-count-workflows", formatNumber(counts.workflows));
  setText("home-count-skills", formatNumber(counts.skills));
  setText("home-count-users", formatNumber(counts.users));
  setText(
    "home-count-users-sub",
    `${formatNumber(counts.activeUsers)} active`,
  );
}

function renderUsage(metrics: MetricsSummaryPayload): void {
  // Active sessions
  setText("home-sessions", formatNumber(metrics.active_client_sessions));

  // Tool calls + success %
  const tcTotal = metrics.tool_calls?.total ?? 0;
  const tcSuccess = metrics.tool_calls?.by_outcome?.success ?? 0;
  setText("home-tool-calls", formatNumber(tcTotal));
  setText(
    "home-tool-calls-sub",
    tcTotal > 0
      ? `${formatPercent(tcSuccess, tcTotal)} success`
      : "No tool calls yet",
  );

  // HTTP + error %
  const httpTotal = metrics.http_requests?.total ?? 0;
  const byStatus = metrics.http_requests?.by_status ?? {};
  const errorCount = Object.entries(byStatus).reduce((acc, [code, count]) => {
    const numeric = Number(code);
    return numeric >= 400 ? acc + count : acc;
  }, 0);
  setText("home-http", formatNumber(httpTotal));
  setText(
    "home-http-sub",
    httpTotal > 0
      ? `${formatPercent(errorCount, httpTotal)} errors (≥400)`
      : "No traffic yet",
  );

  // Auth events — show breakdown briefly
  const authTotal = metrics.auth_events?.total ?? 0;
  const byType = metrics.auth_events?.by_type ?? {};
  const topType = Object.entries(byType).sort(
    ([, a], [, b]) => (b as number) - (a as number),
  )[0];
  setText("home-auth", formatNumber(authTotal));
  setText(
    "home-auth-sub",
    topType
      ? `Top: ${topType[0]} (${formatNumber(topType[1] as number)})`
      : "No auth activity",
  );
}

function renderRecent(events: AuditEventPayload[]): void {
  const body = $("home-recent-body");
  if (!body) return;
  if (!events.length) {
    body.innerHTML = `<tr><td colspan="5" class="px-5 py-8 text-center text-sm text-stone-400">No audit events yet.</td></tr>`;
    return;
  }
  body.innerHTML = events
    .map((e) => {
      const outcomeClass =
        e.outcome === "success"
          ? "bg-emerald-50 text-emerald-800 border-emerald-200"
          : e.outcome === "failure" || e.outcome === "error"
            ? "bg-red-50 text-red-800 border-red-200"
            : e.outcome === "denied"
              ? "bg-amber-50 text-amber-800 border-amber-200"
              : "bg-stone-50 text-stone-700 border-stone-200";
      const actorName =
        e.actor_name?.trim() || e.actor_id || e.actor_type || "—";
      const resource =
        [e.resource_type, e.resource_name || e.resource_id]
          .filter(Boolean)
          .join(" · ") || "—";
      return `
        <tr class="border-b border-stone-100 last:border-b-0">
          <td class="px-5 py-3 font-medium text-stone-900">${escapeHtml(e.event_type)}</td>
          <td class="px-5 py-3 text-stone-700">
            <span class="block">${escapeHtml(actorName)}</span>
            <span class="text-xs text-stone-400">${escapeHtml(e.actor_type)}</span>
          </td>
          <td class="px-5 py-3 text-stone-600">${escapeHtml(resource)}</td>
          <td class="px-5 py-3">
            <span class="inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider ${outcomeClass}">${escapeHtml(e.outcome)}</span>
          </td>
          <td class="px-5 py-3 whitespace-nowrap text-stone-500" title="${escapeHtml(e.created_at ?? "")}">${escapeHtml(formatRelativeTime(e.created_at))}</td>
        </tr>
      `;
    })
    .join("");
}

function setError(message: string | null): void {
  const el = $("home-error");
  if (!el) return;
  if (!message) {
    el.classList.add("hidden");
    el.textContent = "";
  } else {
    el.classList.remove("hidden");
    el.textContent = message;
  }
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

async function loadHomeData(): Promise<void> {
  setError(null);

  const [
    healthResult,
    clientsResult,
    reposResult,
    workflowsResult,
    skillsResult,
    usersAllResult,
    usersActiveResult,
    metricsResult,
    auditResult,
  ] = await Promise.allSettled([
    getServiceHealth(),
    listClients(),
    listRepositories(),
    listWorkflows(),
    listSkills(),
    listUsers(false),
    listUsers(true),
    getMetricsSummary(),
    listAudit(undefined, 8, 0),
  ]);

  // Health (independent — doesn't need auth)
  if (healthResult.status === "fulfilled") {
    renderHealth(healthResult.value);
  } else {
    renderHealth({ ok: false, status: 0, latencyMs: 0 });
  }

  // Inventory
  const counts = {
    clients:
      clientsResult.status === "fulfilled"
        ? clientsResult.value.clients.length
        : 0,
    repositories:
      reposResult.status === "fulfilled"
        ? reposResult.value.repositories.length
        : 0,
    workflows:
      workflowsResult.status === "fulfilled"
        ? workflowsResult.value.workflows.length
        : 0,
    skills:
      skillsResult.status === "fulfilled" ? skillsResult.value.length : 0,
    users:
      usersAllResult.status === "fulfilled"
        ? usersAllResult.value.users.length
        : 0,
    activeUsers:
      usersActiveResult.status === "fulfilled"
        ? usersActiveResult.value.users.length
        : 0,
  };
  renderInventory(counts);

  // Usage metrics
  if (metricsResult.status === "fulfilled") {
    renderUsage(metricsResult.value);
  } else {
    setError(
      metricsResult.reason instanceof Error
        ? `Metrics unavailable: ${metricsResult.reason.message}`
        : "Metrics unavailable.",
    );
  }

  // Recent activity
  if (auditResult.status === "fulfilled") {
    renderRecent(auditResult.value.events);
  } else {
    const body = $("home-recent-body");
    if (body) {
      body.innerHTML = `<tr><td colspan="5" class="px-5 py-8 text-center text-sm text-red-600">Failed to load audit events.</td></tr>`;
    }
  }

  // Last refreshed timestamp
  setText("home-last-updated", new Date().toLocaleTimeString());
}

// ---------------------------------------------------------------------------
// Entry + auto-refresh
// ---------------------------------------------------------------------------

let refreshTimer: number | null = null;

function setAutoRefresh(enabled: boolean): void {
  if (refreshTimer !== null) {
    window.clearInterval(refreshTimer);
    refreshTimer = null;
  }
  if (enabled) {
    refreshTimer = window.setInterval(() => {
      void loadHomeData();
    }, 30_000);
  }
}

async function bootstrap(): Promise<void> {
  const statusEl = $("home-bootstrap-status");
  if (statusEl) statusEl.textContent = "Checking admin session…";

  const admin = await resolveSessionOrRedirect();
  if (!admin) return; // redirect already triggered

  // Swap loading card for the dashboard content
  $("home-bootstrap")?.classList.add("hidden");
  $("home-content")?.classList.remove("hidden");

  renderAdminLabel(admin);

  // Wire controls
  $("home-refresh")?.addEventListener("click", () => {
    void loadHomeData();
  });
  const autoRefresh = $<HTMLInputElement>("home-auto-refresh");
  autoRefresh?.addEventListener("change", () => {
    setAutoRefresh(autoRefresh.checked);
  });

  // Initial load
  await loadHomeData();
}

void bootstrap();
