import {
  listSessions,
  deleteSession,
  type SessionPayload,
} from "../lib/api/admin";
import { showDangerConfirm } from "./modal-controller";
import {
  createDebouncedHandler,
  paginateItems,
  setPagerStatus,
  updatePagerButtons,
} from "./catalog-controls";

const registryEl = document.querySelector("#session-list-registry");
const quickSearchEl = document.querySelector(
  "#session-list-quick-search",
) as HTMLInputElement | null;
const paginationStatusEl = document.querySelector(
  "#session-list-pagination-status",
);
const pagePrevButton = document.querySelector("#session-list-page-prev");
const pageNextButton = document.querySelector("#session-list-page-next");
const quickSearchLoadingEl = document.querySelector(
  "#session-list-quick-search-loading",
);

const PAGE_SIZE = 8;

let allSessions: SessionPayload[] = [];
let visibleSessions: SessionPayload[] = [];
let currentQuery = "";
let currentPage = 1;

const escapeHtml = (value: string): string =>
  value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

function renderRegistry(): void {
  if (!(registryEl instanceof HTMLElement)) return;
  const slice = paginateItems(visibleSessions, currentPage, PAGE_SIZE);
  currentPage = slice.page;
  setPagerStatus(paginationStatusEl, {
    slice,
    label: "sessions",
    query: currentQuery,
  });
  updatePagerButtons(
    pagePrevButton,
    pageNextButton,
    slice.page,
    slice.pageCount,
  );

  if (!visibleSessions.length) {
    registryEl.innerHTML = `
      <article class="shell-card p-6 text-sm text-stone-600">
        ${currentQuery ? `No sessions matched "${escapeHtml(currentQuery)}".` : "No sessions found yet."}
      </article>
    `;
    return;
  }

  registryEl.innerHTML = slice.items
    .map(
      (session) => `
        <div class="relative">
          <a href="/dashboard/sessions/${encodeURIComponent(session.id)}" class="shell-card block p-6 transition hover:-translate-y-0.5">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0 flex-1">
                <p class="eyebrow">${escapeHtml(session.client_id ? "Client Session" : "Direct Session")}</p>
                <h2 class="mt-3 wrap-break-word text-xl font-semibold tracking-tight text-stone-950">${escapeHtml(session.name || session.id.slice(0, 8))}</h2>
              </div>
              <span class="rounded-full border border-stone-200 bg-stone-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-stone-500">
                ${session.last_active ? new Date(session.last_active).toLocaleDateString() : "Never"}
              </span>
            </div>
            <p class="mt-3 text-xs leading-6 text-stone-700 font-mono">${escapeHtml(session.id)}</p>
            <div class="mt-5 flex flex-wrap gap-2 text-xs text-stone-500">
              <span class="rounded-full border border-stone-200 bg-white px-3 py-1">User: ${escapeHtml(session.user_id || "Anonymous")}</span>
              <span class="rounded-full border border-stone-200 bg-white px-3 py-1">Skills: ${Object.keys(session.active_skills || {}).length}</span>
              <span class="rounded-full border border-stone-200 bg-white px-3 py-1">TTL: ${session.ttl}s</span>
            </div>
          </a>
          <button 
            class="session-delete-btn absolute bottom-5 right-5 rounded-full border border-stone-200 bg-white p-2 text-stone-400 transition hover:border-red-200 hover:bg-red-50 hover:text-red-600 focus:outline-none"
            data-session-id="${session.id}"
            data-session-name="${escapeHtml(session.name || session.id.slice(0, 8))}"
            title="Delete session"
          >
            <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2M10 11v6M14 11v6" />
            </svg>
          </button>
        </div>
      `,
    )
    .join("");
}

async function syncVisibleSessions(): Promise<void> {
  if (!currentQuery) {
    visibleSessions = allSessions;
    renderRegistry();
    return;
  }
  
  const query = currentQuery.toLowerCase();
  visibleSessions = allSessions.filter(s => 
    (s.name?.toLowerCase().includes(query)) ||
    (s.id.toLowerCase().includes(query)) ||
    (s.user_id?.toLowerCase().includes(query)) ||
    (s.client_id?.toLowerCase().includes(query))
  );
  renderRegistry();
}

async function refreshSessions(): Promise<void> {
  if (registryEl instanceof HTMLElement) {
    registryEl.innerHTML = `<article class="shell-card p-6 text-sm text-stone-600">Loading sessions...</article>`;
  }
  try {
    const payload = await listSessions();
    allSessions = payload.sessions;
    await syncVisibleSessions();
  } catch (error) {
    if (registryEl instanceof HTMLElement) {
      registryEl.innerHTML = `<article class="shell-card p-6 text-sm text-red-700">${escapeHtml(error instanceof Error ? error.message : "Unable to load sessions.")}</article>`;
    }
  }
}

document.querySelector("#session-list-refresh")?.addEventListener("click", () => {
  void refreshSessions();
});

pagePrevButton?.addEventListener("click", () => {
  currentPage = Math.max(1, currentPage - 1);
  renderRegistry();
});

pageNextButton?.addEventListener("click", () => {
  currentPage += 1;
  renderRegistry();
});

const debouncedSearch = createDebouncedHandler(async () => {
  currentQuery = quickSearchEl?.value.trim() ?? "";
  currentPage = 1;
  await syncVisibleSessions();
  quickSearchLoadingEl?.classList.add("hidden");
});

quickSearchEl?.addEventListener("input", () => {
  quickSearchLoadingEl?.classList.remove("hidden");
  debouncedSearch();
});

registryEl?.addEventListener("click", async (e) => {
  const target = e.target as HTMLElement;
  const btn = target.closest(".session-delete-btn") as HTMLElement | null;
  if (!btn) return;

  const sessionId = btn.dataset.sessionId;
  const sessionName = btn.dataset.sessionName;
  if (!sessionId) return;

  const confirmed = await showDangerConfirm(
    `Are you sure you want to delete session "${sessionName}"? This will clear all runtime memory associated with this session.`,
  );
  if (!confirmed) {
    return;
  }

  void (async () => {
    btn.setAttribute("disabled", "true");
    btn.innerHTML = `<svg class="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" /></svg>`;
    try {
      await deleteSession(sessionId);
      await refreshSessions();
    } catch (err) {
      alert(
        err instanceof Error ? err.message : "Failed to delete session.",
      );
      await refreshSessions();
    }
  })();
});

void refreshSessions();
