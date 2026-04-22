import {
  createMemory,
  deleteMemory,
  listMemories,
  searchAdminCatalog,
  updateMemory,
  type MemoryPayload,
} from "../lib/api/admin";
import {
  createDebouncedHandler,
  paginateItems,
  setPagerStatus,
  updatePagerButtons,
} from "./catalog-controls";

const registryEl = document.querySelector("#memory-registry");
const formEl = document.querySelector("#memory-form") as HTMLFormElement | null;
const memoryIdEl = document.querySelector(
  "#memory-id",
) as HTMLInputElement | null;
const titleEl = document.querySelector(
  "#memory-title",
) as HTMLInputElement | null;
const contentEl = document.querySelector(
  "#memory-content",
) as HTMLTextAreaElement | null;
const languageEl = document.querySelector(
  "#memory-language",
) as HTMLInputElement | null;
const tagsEl = document.querySelector(
  "#memory-tags",
) as HTMLInputElement | null;
const statusEl = document.querySelector("#memory-editor-status");
const quickSearchEl = document.querySelector(
  "#memory-quick-search",
) as HTMLInputElement | null;
const paginationStatusEl = document.querySelector("#memory-pagination-status");
const pagePrevButton = document.querySelector("#memory-page-prev");
const pageNextButton = document.querySelector("#memory-page-next");
const quickSearchLoadingEl = document.querySelector(
  "#memory-quick-search-loading",
);
const toastRegion = document.querySelector("#dashboard-toast-region");

const PAGE_SIZE = 20;

let visibleMemories: MemoryPayload[] = [];
let totalCount = 0;
let selectedMemoryId: string | null = null;
let currentQuery = "";
let currentPage = 1;

const escapeHtml = (value: string): string =>
  value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

const splitCsv = (value: string): string[] =>
  value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

const setStatus = (
  message: string,
  tone: "default" | "success" | "danger" = "default",
) => {
  if (!(statusEl instanceof HTMLElement)) return;
  statusEl.textContent = message;
  statusEl.className = "min-h-6 text-sm";
  if (tone === "success") statusEl.classList.add("text-emerald-700");
  else if (tone === "danger") statusEl.classList.add("text-red-700");
  else statusEl.classList.add("text-stone-600");
};

const showToast = (
  message: string,
  tone: "success" | "danger" | "default" = "default",
) => {
  if (!(toastRegion instanceof HTMLElement)) return;
  const toast = document.createElement("div");
  toast.className =
    "pointer-events-auto rounded-2xl border px-4 py-3 text-sm shadow-[0_18px_40px_rgba(28,25,23,0.12)] backdrop-blur transition";
  if (tone === "success") {
    toast.classList.add(
      "border-emerald-200",
      "bg-emerald-50/95",
      "text-emerald-900",
    );
  } else if (tone === "danger") {
    toast.classList.add("border-red-200", "bg-red-50/95", "text-red-900");
  } else {
    toast.classList.add("border-stone-300", "bg-white/95", "text-stone-900");
  }
  toast.textContent = message;
  toastRegion.appendChild(toast);
  window.setTimeout(() => {
    toast.classList.add("opacity-0", "translate-y-2");
    window.setTimeout(() => toast.remove(), 220);
  }, 2600);
};

const currentDraft = () => ({
  title: titleEl?.value.trim() ?? "",
  content: contentEl?.value ?? "",
  language: languageEl?.value.trim() ?? "markdown",
  tags: splitCsv(tagsEl?.value ?? ""),
});

const fillForm = (memory?: MemoryPayload) => {
  selectedMemoryId = memory?.id ?? null;
  if (memoryIdEl) memoryIdEl.value = memory?.id ?? "";
  if (titleEl) titleEl.value = memory?.title ?? "";
  if (contentEl) contentEl.value = memory?.content ?? "";
  if (languageEl) languageEl.value = memory?.language ?? "markdown";
  if (tagsEl) tagsEl.value = (memory?.tags ?? []).join(", ");
  setStatus("");
};

const renderRegistry = () => {
  if (!(registryEl instanceof HTMLElement)) return;

  const pageCount = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
  const start = totalCount === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1;
  const end = Math.min(currentPage * PAGE_SIZE, totalCount);

  setPagerStatus(paginationStatusEl, {
    slice: {
      items: visibleMemories,
      page: currentPage,
      pageCount,
      total: totalCount,
      start,
      end,
    },
    label: "memories",
    query: currentQuery,
  });
  updatePagerButtons(pagePrevButton, pageNextButton, currentPage, pageCount);

  if (!visibleMemories.length) {
    registryEl.innerHTML = `
      <article class="shell-card p-6 text-sm text-stone-600">
        ${currentQuery ? `No memories matched \"${escapeHtml(currentQuery)}\".` : "No memories yet. Capture the first continuity memory from the editor."}
      </article>
    `;
    return;
  }

  registryEl.innerHTML = visibleMemories
    .map((memory) => {
      const activeClass =
        memory.id === selectedMemoryId
          ? "border-amber-400 bg-amber-50/70"
          : "border-stone-200 bg-white";
      return `
        <article class="shell-card border ${activeClass} p-5">
          <div class="flex items-start justify-between gap-3">
            <button
              type="button"
              class="min-w-0 flex-1 text-left"
              data-memory-select="${escapeHtml(memory.id)}"
            >
              <p class="eyebrow">${escapeHtml(memory.language)}</p>
              <h2 class="mt-2 wrap-break-word text-xl font-semibold tracking-tight text-stone-950">
                ${escapeHtml(memory.title)}
              </h2>
              <p class="mt-3 line-clamp-3 text-sm leading-6 text-stone-600">
                ${escapeHtml(memory.content)}
              </p>
              <div class="mt-4 flex flex-wrap gap-2">
                ${(memory.tags ?? []).map((tag) => `<span class="rounded-full border border-stone-200 bg-stone-50 px-2.5 py-1 text-[11px] text-stone-600">${escapeHtml(tag)}</span>`).join("")}
              </div>
            </button>
            <button
              type="button"
              class="rounded-xl border border-red-200 px-3 py-1.5 text-xs text-red-700 transition hover:bg-red-50"
              data-memory-delete="${escapeHtml(memory.id)}"
            >
              Delete
            </button>
          </div>
        </article>
      `;
    })
    .join("");

  registryEl
    .querySelectorAll<HTMLButtonElement>("[data-memory-select]")
    .forEach((button) => {
      button.addEventListener("click", () => {
        const memory = visibleMemories.find(
          (item) => item.id === button.dataset.memorySelect,
        );
        if (!memory) return;
        fillForm(memory);
        renderRegistry();
      });
    });

  registryEl
    .querySelectorAll<HTMLButtonElement>("[data-memory-delete]")
    .forEach((button) => {
      button.addEventListener("click", async () => {
        const memoryId = button.dataset.memoryDelete;
        const memory = visibleMemories.find((item) => item.id === memoryId);
        if (!memoryId || !memory) return;
        if (!window.confirm(`Delete memory ${memory.title}?`)) return;
        try {
          await deleteMemory(memoryId);
          if (selectedMemoryId === memoryId) fillForm();
          await syncVisibleMemories();
          showToast(`Deleted ${memory.title}.`, "success");
        } catch (error) {
          showToast(
            error instanceof Error ? error.message : "Unable to delete memory.",
            "danger",
          );
        }
      });
    });
};

const syncVisibleMemories = async () => {
  if (registryEl instanceof HTMLElement) {
    registryEl.innerHTML = `<article class="shell-card p-6 text-sm text-stone-600">Loading memories...</article>`;
  }
  try {
    const result = await searchAdminCatalog<MemoryPayload>(
      "memories",
      currentQuery,
      PAGE_SIZE,
      (currentPage - 1) * PAGE_SIZE,
    );
    visibleMemories = result.items;
    totalCount = result.total;
    renderRegistry();
  } catch (error) {
    if (registryEl instanceof HTMLElement) {
      registryEl.innerHTML = `<article class="shell-card p-6 text-sm text-red-700">${escapeHtml(error instanceof Error ? error.message : "Unable to load memories.")}</article>`;
    }
  }
};

document
  .querySelector("#memory-refresh-button")
  ?.addEventListener("click", () => {
    void syncVisibleMemories();
  });

document
  .querySelector("#memory-reset-button")
  ?.addEventListener("click", () => {
    fillForm();
    renderRegistry();
  });

pagePrevButton?.addEventListener("click", () => {
  currentPage = Math.max(1, currentPage - 1);
  void syncVisibleMemories();
});

pageNextButton?.addEventListener("click", () => {
  currentPage += 1;
  void syncVisibleMemories();
});

const debouncedSearch = createDebouncedHandler(async () => {
  currentQuery = quickSearchEl?.value.trim() ?? "";
  currentPage = 1;
  await syncVisibleMemories();
  quickSearchLoadingEl?.classList.add("hidden");
});

quickSearchEl?.addEventListener("input", () => {
  quickSearchLoadingEl?.classList.remove("hidden");
  debouncedSearch();
});

formEl?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const draft = currentDraft();
  const currentMemoryId = memoryIdEl?.value.trim() ?? "";
  const isUpdate = Boolean(currentMemoryId);
  if (!draft.title.trim()) {
    setStatus("Title is required.", "danger");
    return;
  }
  if (!draft.content.trim()) {
    setStatus("Memory content is required.", "danger");
    return;
  }
  setStatus(isUpdate ? "Saving memory changes..." : "Saving memory...");
  try {
    const saved = isUpdate
      ? await updateMemory(currentMemoryId, draft)
      : await createMemory(draft);
    fillForm(saved);
    await syncVisibleMemories();
    showToast(
      `${isUpdate ? "Saved" : "Created"} memory ${saved.title}.`,
      "success",
    );
    setStatus("Memory saved.", "success");
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unable to save memory.";
    setStatus(message, "danger");
    showToast(message, "danger");
  }
});

fillForm();
void syncVisibleMemories();
