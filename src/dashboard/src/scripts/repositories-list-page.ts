import {
  listRepositories,
  searchAdminCatalog,
  type RepositoryPayload,
} from "../lib/api/admin";
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
        <a href="/dashboard/repositories/${encodeURIComponent(repo.id)}" class="shell-card block p-6 transition hover:-translate-y-0.5">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0 flex-1">
              <p class="eyebrow">${escapeHtml(repo.workflow_name ?? "Repository")}</p>
              <h2 class="mt-3 break-words text-2xl font-semibold tracking-tight text-stone-950">${escapeHtml(repo.name)}</h2>
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

quickSearchEl?.addEventListener(
  "input",
  createDebouncedHandler(async () => {
    currentQuery = quickSearchEl.value.trim();
    currentPage = 1;
    await syncVisibleRepositories();
  }),
);

void refreshRepositories();
