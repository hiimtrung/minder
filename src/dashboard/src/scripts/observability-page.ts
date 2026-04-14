import {
  getMetricsSummary,
  listAudit,
  type AuditEventPayload,
  type MetricsSummaryPayload,
} from "../lib/api/admin";

// ---------------------------------------------------------------------------
// Element refs
// ---------------------------------------------------------------------------

const statSessions = document.querySelector("#stat-sessions");
const statToolCalls = document.querySelector("#stat-tool-calls");
const statToolCallsSub = document.querySelector("#stat-tool-calls-sub");
const statAuthEvents = document.querySelector("#stat-auth-events");
const statAuthEventsSub = document.querySelector("#stat-auth-events-sub");
const statHttpRequests = document.querySelector("#stat-http-requests");
const statHttpSub = document.querySelector("#stat-http-sub");

const chartToolOutcomes = document.querySelector("#chart-tool-outcomes");
const chartAuthTypes = document.querySelector("#chart-auth-types");
const chartHttpStatus = document.querySelector("#chart-http-status");
const chartAdminOps = document.querySelector("#chart-admin-ops");

const auditLogBody = document.querySelector("#audit-log-body");
const auditActorFilter = document.querySelector(
  "#audit-actor-filter",
) as HTMLInputElement | null;
const auditEventTypeFilter = document.querySelector(
  "#audit-event-type-filter",
) as HTMLSelectElement | null;
const auditOutcomeFilter = document.querySelector(
  "#audit-outcome-filter",
) as HTMLSelectElement | null;
const auditFilterApply = document.querySelector("#audit-filter-apply");
const auditFilterClear = document.querySelector("#audit-filter-clear");
const refreshButton = document.querySelector("#refresh-observability");
const autoRefreshToggle = document.querySelector(
  "#auto-refresh-toggle",
) as HTMLInputElement | null;
const paginationInfo = document.querySelector("#audit-pagination-info");
const paginationPrev = document.querySelector(
  "#audit-prev",
) as HTMLButtonElement | null;
const paginationNext = document.querySelector(
  "#audit-next",
) as HTMLButtonElement | null;
const pageSizeSelect = document.querySelector(
  "#audit-page-size",
) as HTMLSelectElement | null;
const activeFilterPills = document.querySelector("#active-filter-pills");

// ---------------------------------------------------------------------------
// Pagination / filter state
// ---------------------------------------------------------------------------

const PAGE_SIZE_DEFAULT = 25;
let currentOffset = 0;
let currentTotal = 0;
let currentLimit = PAGE_SIZE_DEFAULT;
let currentActorFilter: string | undefined;
let currentEventTypeFilter: string | undefined;
let currentOutcomeFilter: string | undefined;

let autoRefreshInterval: ReturnType<typeof setInterval> | null = null;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const escapeHtml = (value: string): string =>
  value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

const fmt = (n: number): string =>
  Number.isFinite(n) ? Math.round(n).toLocaleString() : "0";

const relativeTime = (iso: string | null): string => {
  if (!iso) return "—";
  try {
    const delta = Date.now() - new Date(iso).getTime();
    const secs = Math.floor(delta / 1000);
    if (secs < 60) return `${secs}s ago`;
    const mins = Math.floor(secs / 60);
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return new Date(iso).toLocaleDateString();
  } catch {
    return iso ?? "—";
  }
};

const outcomeClass = (outcome: string): string => {
  if (outcome === "success" || outcome === "ok") {
    return "border-emerald-200 bg-emerald-50 text-emerald-800";
  }
  if (outcome === "error" || outcome === "failure" || outcome === "denied") {
    return "border-red-200 bg-red-50 text-red-800";
  }
  return "border-stone-200 bg-stone-50 text-stone-700";
};

// ---------------------------------------------------------------------------
// Donut SVG chart
// ---------------------------------------------------------------------------

// Colour palette: green, amber, blue, red, violet, cyan, orange, rose
const DONUT_COLORS = [
  "#22c55e",
  "#f59e0b",
  "#3b82f6",
  "#ef4444",
  "#8b5cf6",
  "#06b6d4",
  "#f97316",
  "#f43f5e",
];

function renderDonut(
  container: Element | null,
  data: Record<string, number>,
): void {
  if (!container) return;

  const entries = Object.entries(data)
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1]);

  if (!entries.length) {
    container.innerHTML =
      '<p class="text-sm text-stone-400 text-center py-4">No data yet.</p>';
    return;
  }

  const total = entries.reduce((s, [, v]) => s + v, 0);
  const SIZE = 120;
  const cx = SIZE / 2;
  const cy = SIZE / 2;
  const RADIUS = 42;
  const STROKE_W = 22;
  const circumference = 2 * Math.PI * RADIUS;

  let cumPct = 0;
  const segments = entries
    .map(([, value], i) => {
      const pct = value / total;
      const dash = (pct * circumference).toFixed(3);
      const gap = (circumference * (1 - pct)).toFixed(3);
      const rotation = (cumPct * 360 - 90).toFixed(3);
      cumPct += pct;
      const color = DONUT_COLORS[i % DONUT_COLORS.length];
      return `<circle cx="${cx}" cy="${cy}" r="${RADIUS}" fill="none" stroke="${color}" stroke-width="${STROKE_W}" stroke-dasharray="${dash} ${gap}" transform="rotate(${rotation} ${cx} ${cy})" />`;
    })
    .join("");

  const legend = entries
    .map(([label, value], i) => {
      const pct = Math.round((value / total) * 100);
      const color = DONUT_COLORS[i % DONUT_COLORS.length];
      return `
        <div class="flex items-center gap-2 text-xs">
          <span class="h-2.5 w-2.5 rounded-full shrink-0" style="background:${color}"></span>
          <span class="truncate text-stone-700 flex-1">${escapeHtml(label)}</span>
          <span class="tabular-nums text-stone-500 shrink-0">${pct}%</span>
        </div>`;
    })
    .join("");

  const totalLabel =
    total >= 1000
      ? (total / 1000).toFixed(1) + "k"
      : String(Math.round(total));

  container.innerHTML = `
    <div class="flex flex-col items-center gap-3 w-full">
      <svg width="${SIZE}" height="${SIZE}" viewBox="0 0 ${SIZE} ${SIZE}" style="overflow:visible">
        <circle cx="${cx}" cy="${cy}" r="${RADIUS}" fill="none" stroke="#e7e5e4" stroke-width="${STROKE_W}"/>
        ${segments}
        <text x="${cx}" y="${cy - 6}" text-anchor="middle" font-size="16" font-weight="700" fill="#1c1917">${totalLabel}</text>
        <text x="${cx}" y="${cy + 10}" text-anchor="middle" font-size="10" fill="#78716c">total</text>
      </svg>
      <div class="w-full grid gap-1.5">${legend}</div>
    </div>`;
}

// ---------------------------------------------------------------------------
// Render metrics summary
// ---------------------------------------------------------------------------

const renderMetrics = (data: MetricsSummaryPayload): void => {
  if (statSessions) statSessions.textContent = fmt(data.active_client_sessions);

  if (statToolCalls) statToolCalls.textContent = fmt(data.tool_calls.total);
  if (statToolCallsSub) {
    const success = data.tool_calls.by_outcome["success"] ?? 0;
    const total = data.tool_calls.total;
    const rate = total > 0 ? Math.round((success / total) * 100) : 0;
    statToolCallsSub.textContent =
      total > 0 ? `${rate}% success rate` : "No calls yet";
  }

  if (statAuthEvents) statAuthEvents.textContent = fmt(data.auth_events.total);
  if (statAuthEventsSub) {
    const logins = data.auth_events.by_type["login"] ?? 0;
    const exchanges = data.auth_events.by_type["token_exchange"] ?? 0;
    statAuthEventsSub.textContent = `${fmt(logins)} login${logins !== 1 ? "s" : ""}, ${fmt(exchanges)} exchange${exchanges !== 1 ? "s" : ""}`;
  }

  if (statHttpRequests)
    statHttpRequests.textContent = fmt(data.http_requests.total);
  if (statHttpSub) {
    const s4xx = Object.entries(data.http_requests.by_status)
      .filter(([k]) => k.startsWith("4"))
      .reduce((acc, [, v]) => acc + v, 0);
    const s5xx = Object.entries(data.http_requests.by_status)
      .filter(([k]) => k.startsWith("5"))
      .reduce((acc, [, v]) => acc + v, 0);
    const errorCount = s4xx + s5xx;
    statHttpSub.textContent =
      errorCount > 0
        ? `${fmt(errorCount)} error${errorCount !== 1 ? "s" : ""}`
        : "No errors";
  }

  renderDonut(chartToolOutcomes, data.tool_calls.by_outcome);
  renderDonut(chartAuthTypes, data.auth_events.by_type);
  renderDonut(chartHttpStatus, data.http_requests.by_status);
  renderDonut(chartAdminOps, data.admin_operations.by_outcome);
};

// ---------------------------------------------------------------------------
// Active filter pills
// ---------------------------------------------------------------------------

const renderFilterPills = (): void => {
  if (!activeFilterPills) return;
  const pills: string[] = [];
  if (currentEventTypeFilter) {
    pills.push(
      `<span class="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-800">
        type: ${escapeHtml(currentEventTypeFilter)}
        <button data-clear="event_type" class="ml-1 text-amber-500 hover:text-amber-900">✕</button>
      </span>`,
    );
  }
  if (currentOutcomeFilter) {
    pills.push(
      `<span class="inline-flex items-center gap-1 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-800">
        outcome: ${escapeHtml(currentOutcomeFilter)}
        <button data-clear="outcome" class="ml-1 text-blue-500 hover:text-blue-900">✕</button>
      </span>`,
    );
  }
  if (currentActorFilter) {
    pills.push(
      `<span class="inline-flex items-center gap-1 rounded-full border border-stone-200 bg-stone-100 px-3 py-1 text-xs font-medium text-stone-700">
        actor: ${escapeHtml(currentActorFilter.slice(0, 12))}…
        <button data-clear="actor" class="ml-1 text-stone-400 hover:text-stone-900">✕</button>
      </span>`,
    );
  }
  activeFilterPills.innerHTML = pills.join("");
  // Wire pill clear buttons
  activeFilterPills
    .querySelectorAll<HTMLButtonElement>("[data-clear]")
    .forEach((btn) => {
      btn.addEventListener("click", () => {
        const field = btn.dataset.clear;
        if (field === "event_type") {
          currentEventTypeFilter = undefined;
          if (auditEventTypeFilter) auditEventTypeFilter.value = "";
        } else if (field === "outcome") {
          currentOutcomeFilter = undefined;
          if (auditOutcomeFilter) auditOutcomeFilter.value = "";
        } else if (field === "actor") {
          currentActorFilter = undefined;
          if (auditActorFilter) auditActorFilter.value = "";
        }
        currentOffset = 0;
        renderFilterPills();
        void loadAuditLog();
      });
    });
};

// ---------------------------------------------------------------------------
// Render audit log
// ---------------------------------------------------------------------------

const renderAuditLog = (events: AuditEventPayload[], total: number): void => {
  if (!auditLogBody) return;

  // Pagination info
  if (paginationInfo) {
    const from = total === 0 ? 0 : currentOffset + 1;
    const to = Math.min(currentOffset + currentLimit, total);
    paginationInfo.textContent = `${from}–${to} of ${total.toLocaleString()}`;
  }
  if (paginationPrev) paginationPrev.disabled = currentOffset === 0;
  if (paginationNext)
    paginationNext.disabled = currentOffset + currentLimit >= total;

  if (!events.length) {
    auditLogBody.innerHTML = `
      <tr>
        <td colspan="5" class="px-4 py-8 text-center text-sm text-stone-400">
          No audit events found matching the current filters.
        </td>
      </tr>`;
    return;
  }

  auditLogBody.innerHTML = events
    .map((evt) => {
      const actorLabel = evt.actor_name
        ? escapeHtml(evt.actor_name)
        : evt.actor_id
          ? `<span class="font-mono text-[10px]">${escapeHtml(evt.actor_id.slice(0, 8))}…</span>`
          : "—";

      const resourceLabel = evt.resource_name
        ? escapeHtml(evt.resource_name)
        : evt.resource_id
          ? `<span class="font-mono text-[10px]">${escapeHtml(evt.resource_id.slice(0, 8))}…</span>`
          : "—";

      return `
    <tr class="border-t border-stone-100 hover:bg-stone-50/60 transition-colors">
      <td class="px-4 py-3">
        <span class="font-medium text-stone-900 text-xs">${escapeHtml(evt.event_type)}</span>
      </td>
      <td class="px-4 py-3">
        <div class="flex flex-col gap-0.5">
          <span class="text-[10px] font-semibold uppercase tracking-wide text-stone-400">${escapeHtml(evt.actor_type)}</span>
          <span class="text-xs text-stone-700 truncate max-w-36" title="${escapeHtml(evt.actor_id)}">${actorLabel}</span>
        </div>
      </td>
      <td class="px-4 py-3">
        <div class="flex flex-col gap-0.5">
          <span class="text-[10px] font-semibold uppercase tracking-wide text-stone-400">${escapeHtml(evt.resource_type)}</span>
          <span class="text-xs text-stone-700 truncate max-w-36" title="${escapeHtml(evt.resource_id ?? "")}">${resourceLabel}</span>
        </div>
      </td>
      <td class="px-4 py-3">
        <span class="inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold ${outcomeClass(evt.outcome)}">
          ${escapeHtml(evt.outcome)}
        </span>
      </td>
      <td class="px-4 py-3 text-xs text-stone-500 whitespace-nowrap" title="${evt.created_at ?? ""}">${escapeHtml(relativeTime(evt.created_at))}</td>
    </tr>
  `;
    })
    .join("");
};

// ---------------------------------------------------------------------------
// Load functions
// ---------------------------------------------------------------------------

const loadMetrics = async (): Promise<void> => {
  try {
    const data = await getMetricsSummary(
      currentActorFilter,
      currentEventTypeFilter,
      currentOutcomeFilter,
    );
    renderMetrics(data);
  } catch (error) {
    const msg =
      error instanceof Error ? error.message : "Unable to load metrics.";
    [statSessions, statToolCalls, statAuthEvents, statHttpRequests].forEach(
      (el) => {
        if (el) el.textContent = "—";
      },
    );
    [chartToolOutcomes, chartAuthTypes, chartHttpStatus, chartAdminOps].forEach(
      (el) => {
        if (el)
          el.innerHTML = `<p class="text-sm text-red-600">${escapeHtml(msg)}</p>`;
      },
    );
  }
};

const loadAuditLog = async (): Promise<void> => {
  if (auditLogBody) {
    auditLogBody.innerHTML = `
      <tr>
        <td colspan="5" class="px-4 py-6 text-center text-sm text-stone-400">Loading…</td>
      </tr>`;
  }
  try {
    const payload = await listAudit(
      currentActorFilter,
      currentLimit,
      currentOffset,
      currentEventTypeFilter,
      currentOutcomeFilter,
    );
    currentTotal = payload.total;
    renderAuditLog(payload.events, payload.total);
  } catch (error) {
    const msg =
      error instanceof Error ? error.message : "Unable to load audit log.";
    if (auditLogBody) {
      auditLogBody.innerHTML = `
        <tr>
          <td colspan="5" class="px-4 py-6 text-center text-sm text-red-600">${escapeHtml(msg)}</td>
        </tr>`;
    }
  }
};

const applyFilters = () => {
  currentActorFilter = auditActorFilter?.value.trim() || undefined;
  currentEventTypeFilter = auditEventTypeFilter?.value || undefined;
  currentOutcomeFilter = auditOutcomeFilter?.value || undefined;
  currentOffset = 0;
  renderFilterPills();
  void loadMetrics();
  void loadAuditLog();
};

const clearFilters = () => {
  if (auditActorFilter) auditActorFilter.value = "";
  if (auditEventTypeFilter) auditEventTypeFilter.value = "";
  if (auditOutcomeFilter) auditOutcomeFilter.value = "";
  currentActorFilter = undefined;
  currentEventTypeFilter = undefined;
  currentOutcomeFilter = undefined;
  currentOffset = 0;
  renderFilterPills();
  void loadMetrics();
  void loadAuditLog();
};

const refresh = (): void => {
  void loadMetrics();
  currentOffset = 0;
  void loadAuditLog();
};

// ---------------------------------------------------------------------------
// Auto-refresh
// ---------------------------------------------------------------------------

const startAutoRefresh = () => {
  if (autoRefreshInterval) return;
  autoRefreshInterval = setInterval(refresh, 30_000);
};

const stopAutoRefresh = () => {
  if (autoRefreshInterval) {
    clearInterval(autoRefreshInterval);
    autoRefreshInterval = null;
  }
};

// ---------------------------------------------------------------------------
// Event wiring
// ---------------------------------------------------------------------------

auditFilterApply?.addEventListener("click", applyFilters);
auditFilterClear?.addEventListener("click", clearFilters);

auditActorFilter?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") applyFilters();
});

auditEventTypeFilter?.addEventListener("change", applyFilters);
auditOutcomeFilter?.addEventListener("change", applyFilters);

paginationPrev?.addEventListener("click", () => {
  currentOffset = Math.max(0, currentOffset - currentLimit);
  void loadAuditLog();
});

paginationNext?.addEventListener("click", () => {
  if (currentOffset + currentLimit < currentTotal) {
    currentOffset += currentLimit;
    void loadAuditLog();
  }
});

pageSizeSelect?.addEventListener("change", () => {
  currentLimit = parseInt(pageSizeSelect.value, 10) || PAGE_SIZE_DEFAULT;
  currentOffset = 0;
  void loadAuditLog();
});

refreshButton?.addEventListener("click", refresh);

autoRefreshToggle?.addEventListener("change", () => {
  if (autoRefreshToggle.checked) {
    startAutoRefresh();
  } else {
    stopAutoRefresh();
  }
});

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

void loadMetrics();
void loadAuditLog();
