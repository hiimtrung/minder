import {
  listRepositories,
  searchAdminCatalog,
  deleteRepository,
  type RepositoryPayload,
} from "../lib/api/admin";
import { showDangerConfirm } from "./modal-controller";
import {
  createDebouncedHandler,
  paginateItems,
  setPagerStatus,
  updatePagerButtons,
} from "./catalog-controls";

const registryEl = document.querySelector("#repo-list-registry");
const quickSearchEl = document.querySelector(
  "#repo-list-quick-search",
) as HTMLInputElement | null;
const paginationStatusEl = document.querySelector(
  "#repo-list-pagination-status",
);
const pagePrevButton = document.querySelector("#repo-list-page-prev");
const pageNextButton = document.querySelector("#repo-list-page-next");
const quickSearchLoadingEl = document.querySelector(
  "#repo-list-quick-search-loading",
);

const PAGE_SIZE = 8;

let allRepositories: RepositoryPayload[] = [];
let visibleRepositories: RepositoryPayload[] = [];
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
  const slice = paginateItems(visibleRepositories, currentPage, PAGE_SIZE);
  currentPage = slice.page;
  setPagerStatus(paginationStatusEl, {
    slice,
    label: "repositories",
    query: currentQuery,
  });
  updatePagerButtons(
    pagePrevButton,
    pageNextButton,
    slice.page,
    slice.pageCount,
  );

  if (!visibleRepositories.length) {
    registryEl.innerHTML = `
      <article class="shell-card p-6 text-sm text-stone-600">
        ${currentQuery ? `No repositories matched \"${escapeHtml(currentQuery)}\".` : "No repositories found yet."}
      </article>
    `;
    return;
  }

  registryEl.innerHTML = slice.items
    .map(
      (repo) => `
        <div class="relative">
          <a href="/dashboard/repositories/${encodeURIComponent(repo.id)}" class="shell-card block p-6 transition hover:-translate-y-0.5">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0 flex-1">
                <p class="eyebrow">${escapeHtml(repo.workflow_name ?? "Repository")}</p>
                <h2 class="mt-3 wrap-break-word text-2xl font-semibold tracking-tight text-stone-950">${escapeHtml(repo.name)}</h2>
              </div>
              <span class="rounded-full border border-stone-200 bg-stone-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-stone-500">
                ${escapeHtml(repo.default_branch ?? "no-branch")}
              </span>
            </div>
            <p class="mt-3 text-sm leading-6 text-stone-700">${escapeHtml(repo.remote_url ?? repo.path)}</p>
            <div class="mt-5 flex flex-wrap gap-2 text-xs text-stone-500">
              <span class="rounded-full border border-stone-200 bg-white px-3 py-1">Workflow: ${escapeHtml(repo.workflow_state ?? repo.workflow_name ?? "Unassigned")}</span>
              <span class="rounded-full border border-stone-200 bg-white px-3 py-1">Step: ${escapeHtml(repo.current_step ?? "n/a")}</span>
              <span class="rounded-full border border-stone-200 bg-white px-3 py-1">Branches: ${escapeHtml(String(repo.tracked_branches.length || 0))}</span>
            </div>
          </a>
          <button 
            class="repo-delete-btn absolute bottom-5 right-5 rounded-full border border-stone-200 bg-white p-2 text-stone-400 transition hover:border-red-200 hover:bg-red-50 hover:text-red-600 focus:outline-none"
            data-repo-id="${repo.id}"
            data-repo-name="${escapeHtml(repo.name)}"
            title="Delete repository"
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

async function syncVisibleRepositories(): Promise<void> {
  if (!currentQuery) {
    visibleRepositories = allRepositories;
    renderRegistry();
    return;
  }
  const result = await searchAdminCatalog<RepositoryPayload>(
    "repositories",
    currentQuery,
    200,
    0,
  );
  visibleRepositories = result.items;
  renderRegistry();
}

async function refreshRepositories(): Promise<void> {
  if (registryEl instanceof HTMLElement) {
    registryEl.innerHTML = `<article class="shell-card p-6 text-sm text-stone-600">Loading repositories...</article>`;
  }
  try {
    const payload = await listRepositories();
    allRepositories = payload.repositories;
    await syncVisibleRepositories();
  } catch (error) {
    if (registryEl instanceof HTMLElement) {
      registryEl.innerHTML = `<article class="shell-card p-6 text-sm text-red-700">${escapeHtml(error instanceof Error ? error.message : "Unable to load repositories.")}</article>`;
    }
  }
}

document.querySelector("#repo-list-refresh")?.addEventListener("click", () => {
  void refreshRepositories();
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
  await syncVisibleRepositories();
  quickSearchLoadingEl?.classList.add("hidden");
});

quickSearchEl?.addEventListener("input", () => {
  quickSearchLoadingEl?.classList.remove("hidden");
  debouncedSearch();
});

registryEl?.addEventListener("click", async (e) => {
  const target = e.target as HTMLElement;
  const btn = target.closest(".repo-delete-btn") as HTMLElement | null;
  if (!btn) return;

  const repoId = btn.dataset.repoId;
  const repoName = btn.dataset.repoName;
  if (!repoId) return;

  const confirmed = await showDangerConfirm(
    `Are you sure you want to delete repository "${repoName}"? This action cannot be undone.`,
  );
  if (!confirmed) {
    return;
  }

  void (async () => {
    btn.setAttribute("disabled", "true");
    btn.innerHTML = `<svg class="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" /></svg>`;
    try {
      await deleteRepository(repoId);
      await refreshRepositories();
    } catch (err) {
      alert(
        err instanceof Error ? err.message : "Failed to delete repository.",
      );
      await refreshRepositories();
    }
  })();
});

void refreshRepositories();
