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

const breakdownToolOutcomes = document.querySelector("#breakdown-tool-outcomes");
const breakdownAuthTypes = document.querySelector("#breakdown-auth-types");
const breakdownHttpStatus = document.querySelector("#breakdown-http-status");
const breakdownAdminOps = document.querySelector("#breakdown-admin-ops");

const auditLogBody = document.querySelector("#audit-log-body");
const auditActorFilter = document.querySelector(
  "#audit-actor-filter",
) as HTMLInputElement | null;
const auditFilterApply = document.querySelector("#audit-filter-apply");
const auditFilterClear = document.querySelector("#audit-filter-clear");
const refreshButton = document.querySelector("#refresh-observability");
const paginationInfo = document.querySelector("#audit-pagination-info");
const paginationPrev = document.querySelector("#audit-prev") as HTMLButtonElement | null;
const paginationNext = document.querySelector("#audit-next") as HTMLButtonElement | null;
const pageSizeSelect = document.querySelector(
  "#audit-page-size",
) as HTMLSelectElement | null;

// ---------------------------------------------------------------------------
// Pagination state
// ---------------------------------------------------------------------------

const PAGE_SIZE_DEFAULT = 25;
let currentOffset = 0;
let currentTotal = 0;
let currentLimit = PAGE_SIZE_DEFAULT;
let currentActorFilter: string | undefined;

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
// Render breakdown rows
// ---------------------------------------------------------------------------

const renderBreakdown = (
  container: Element | null,
  data: Record<string, number>,
  emptyMessage = "No data yet.",
): void => {
  if (!container) return;
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  if (!entries.length) {
    container.innerHTML = `<p class="text-sm text-stone-400">${emptyMessage}</p>`;
    return;
  }
  const max = Math.max(...entries.map(([, v]) => v), 1);
  container.innerHTML = entries
    .map(
      ([label, value]) => `
    <div class="grid gap-1">
      <div class="flex items-center justify-between gap-2 text-xs">
        <span class="font-medium text-stone-700 truncate">${escapeHtml(label)}</span>
        <span class="shrink-0 tabular-nums text-stone-500">${fmt(value)}</span>
      </div>
      <div class="h-1.5 rounded-full bg-stone-100 overflow-hidden">
        <div
          class="h-full rounded-full bg-amber-400"
          style="width:${Math.round((value / max) * 100)}%"
        ></div>
      </div>
    </div>
  `,
    )
    .join("");
};

// ---------------------------------------------------------------------------
// Render metrics summary
// ---------------------------------------------------------------------------

const renderMetrics = (data: MetricsSummaryPayload): void => {
  if (statSessions) statSessions.textContent = fmt(data.active_client_sessions);

  if (statToolCalls) statToolCalls.textContent = fmt(data.tool_calls.total);
  if (statToolCallsSub) {
    const success = data.tool_calls.by_outcome["success"] ?? 0;
    const total = data.tool_calls.total || 1;
    const rate = Math.round((success / total) * 100);
    statToolCallsSub.textContent = total > 0 ? `${rate}% success rate` : "No calls yet";
  }

  if (statAuthEvents) statAuthEvents.textContent = fmt(data.auth_events.total);
  if (statAuthEventsSub) {
    const logins = data.auth_events.by_type["login"] ?? 0;
    const exchanges = data.auth_events.by_type["token_exchange"] ?? 0;
    statAuthEventsSub.textContent = `${fmt(logins)} login${logins !== 1 ? "s" : ""}, ${fmt(exchanges)} exchange${exchanges !== 1 ? "s" : ""}`;
  }

  if (statHttpRequests) statHttpRequests.textContent = fmt(data.http_requests.total);
  if (statHttpSub) {
    const s4xx = Object.entries(data.http_requests.by_status)
      .filter(([k]) => k.startsWith("4"))
      .reduce((acc, [, v]) => acc + v, 0);
    const s5xx = Object.entries(data.http_requests.by_status)
      .filter(([k]) => k.startsWith("5"))
      .reduce((acc, [, v]) => acc + v, 0);
    const errorCount = s4xx + s5xx;
    statHttpSub.textContent =
      errorCount > 0 ? `${fmt(errorCount)} error${errorCount !== 1 ? "s" : ""}` : "No errors";
  }

  renderBreakdown(breakdownToolOutcomes, data.tool_calls.by_outcome);
  renderBreakdown(breakdownAuthTypes, data.auth_events.by_type);
  renderBreakdown(breakdownHttpStatus, data.http_requests.by_status);
  renderBreakdown(breakdownAdminOps, data.admin_operations.by_outcome);
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
  if (paginationNext) paginationNext.disabled = currentOffset + currentLimit >= total;

  if (!events.length) {
    auditLogBody.innerHTML = `
      <tr>
        <td colspan="5" class="px-4 py-6 text-center text-sm text-stone-400">
          No audit events found.
        </td>
      </tr>`;
    return;
  }

  auditLogBody.innerHTML = events
    .map(
      (evt) => {
        // Actor display: prefer name, fall back to truncated ID
        const actorLabel = evt.actor_name
          ? escapeHtml(evt.actor_name)
          : escapeHtml(evt.actor_id.slice(0, 10)) + "…";

        // Resource display: prefer name, fall back to truncated ID
        const resourceLabel = evt.resource_name
          ? escapeHtml(evt.resource_name)
          : escapeHtml(evt.resource_id.slice(0, 10)) + "…";

        return `
    <tr class="border-t border-stone-100 hover:bg-stone-50/60 transition-colors">
      <td class="px-4 py-3">
        <span class="font-medium text-stone-900">${escapeHtml(evt.event_type)}</span>
      </td>
      <td class="px-4 py-3">
        <div class="grid">
          <span class="text-xs font-medium uppercase tracking-wide text-stone-500">${escapeHtml(evt.actor_type)}</span>
          <span class="mt-0.5 truncate text-xs text-stone-700 max-w-[160px]" title="${escapeHtml(evt.actor_id)}">${actorLabel}</span>
        </div>
      </td>
      <td class="px-4 py-3">
        <div class="grid">
          <span class="text-xs text-stone-500 uppercase">${escapeHtml(evt.resource_type)}</span>
          <span class="mt-0.5 truncate text-xs text-stone-700 max-w-[160px]" title="${escapeHtml(evt.resource_id)}">
            ${resourceLabel}
          </span>
        </div>
      </td>
      <td class="px-4 py-3">
        <span class="inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold ${outcomeClass(evt.outcome)}">
          ${escapeHtml(evt.outcome)}
        </span>
      </td>
      <td class="px-4 py-3 text-xs text-stone-500 whitespace-nowrap">${escapeHtml(relativeTime(evt.created_at))}</td>
    </tr>
  `;
      }
    )
    .join("");
};

// ---------------------------------------------------------------------------
// Load functions
// ---------------------------------------------------------------------------

const loadMetrics = async (): Promise<void> => {
  try {
    const data = await getMetricsSummary();
    renderMetrics(data);
  } catch (error) {
    const msg = error instanceof Error ? error.message : "Unable to load metrics.";
    [statSessions, statToolCalls, statAuthEvents, statHttpRequests].forEach((el) => {
      if (el) el.textContent = "—";
    });
    [breakdownToolOutcomes, breakdownAuthTypes, breakdownHttpStatus, breakdownAdminOps].forEach(
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
    const payload = await listAudit(currentActorFilter, currentLimit, currentOffset);
    currentTotal = payload.total;
    renderAuditLog(payload.events, payload.total);
  } catch (error) {
    const msg = error instanceof Error ? error.message : "Unable to load audit log.";
    if (auditLogBody) {
      auditLogBody.innerHTML = `
        <tr>
          <td colspan="5" class="px-4 py-6 text-center text-sm text-red-600">${escapeHtml(msg)}</td>
        </tr>`;
    }
  }
};

const refresh = (): void => {
  void loadMetrics();
  currentOffset = 0;
  void loadAuditLog();
};

// ---------------------------------------------------------------------------
// Event wiring
// ---------------------------------------------------------------------------

auditFilterApply?.addEventListener("click", () => {
  currentActorFilter = auditActorFilter?.value.trim() || undefined;
  currentOffset = 0;
  void loadAuditLog();
});

auditFilterClear?.addEventListener("click", () => {
  if (auditActorFilter) auditActorFilter.value = "";
  currentActorFilter = undefined;
  currentOffset = 0;
  void loadAuditLog();
});

auditActorFilter?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    currentActorFilter = auditActorFilter.value.trim() || undefined;
    currentOffset = 0;
    void loadAuditLog();
  }
});

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

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

void loadMetrics();
void loadAuditLog();
