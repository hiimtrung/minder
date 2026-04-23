import {
  createPrompt,
  deletePrompt,
  listPrompts,
  polishPromptDraft,
  searchAdminCatalog,
  updatePrompt,
  type PromptPayload,
} from "../lib/api/admin";
import {
  createDebouncedHandler,
  paginateItems,
  setPagerStatus,
  updatePagerButtons,
} from "./catalog-controls";
import { showDangerConfirm } from "./modal-controller";

const registryEl = document.querySelector("#prompt-registry");
const formEl = document.querySelector("#prompt-form") as HTMLFormElement | null;
const promptIdEl = document.querySelector(
  "#prompt-id",
) as HTMLInputElement | null;
const nameEl = document.querySelector(
  "#prompt-name",
) as HTMLInputElement | null;
const titleEl = document.querySelector(
  "#prompt-title",
) as HTMLInputElement | null;
const descriptionEl = document.querySelector(
  "#prompt-description",
) as HTMLTextAreaElement | null;
const argumentsEl = document.querySelector(
  "#prompt-arguments",
) as HTMLInputElement | null;
const argumentHintsEl = document.querySelector("#prompt-argument-hints");
const templateEl = document.querySelector(
  "#prompt-template",
) as HTMLTextAreaElement | null;
const statusEl = document.querySelector("#prompt-editor-status");
const llmStatusEl = document.querySelector("#prompt-editor-llm");
const previewVarsEl = document.querySelector(
  "#prompt-preview-variables",
) as HTMLTextAreaElement | null;
const previewOutputEl = document.querySelector("#prompt-preview-output");
const previewStatusEl = document.querySelector("#prompt-preview-status");
const quickSearchEl = document.querySelector(
  "#prompt-quick-search",
) as HTMLInputElement | null;
const paginationStatusEl = document.querySelector("#prompt-pagination-status");
const pagePrevButton = document.querySelector("#prompt-page-prev");
const pageNextButton = document.querySelector("#prompt-page-next");
const quickSearchLoadingEl = document.querySelector("#prompt-quick-search-loading");
const toastRegion = document.querySelector("#dashboard-toast-region");

const PAGE_SIZE = 20;

let visiblePrompts: PromptPayload[] = [];
let totalCount = 0;
let selectedPromptKey: string | null = null;
let currentQuery = "";
let currentPage = 1;

const BUILTIN_ID_PREFIX = "builtin:";

const isBuiltinId = (value: string | null): boolean =>
  Boolean(value && value.startsWith(BUILTIN_ID_PREFIX));

const promptKey = (prompt: PromptPayload): string => prompt.id;

const escapeHtml = (value: string): string =>
  value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

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

const setStatus = (
  element: Element | null,
  message: string,
  tone: "default" | "success" | "danger" = "default",
) => {
  if (!(element instanceof HTMLElement)) return;
  element.textContent = message;
  element.className = "min-h-6 text-sm";
  if (tone === "success") element.classList.add("text-emerald-700");
  else if (tone === "danger") element.classList.add("text-red-700");
  else element.classList.add("text-stone-600");
};

const setLlmStatus = (message: string) => {
  if (!(llmStatusEl instanceof HTMLElement)) return;
  llmStatusEl.textContent = message;
};

const parseArguments = (): string[] =>
  (argumentsEl?.value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

const extractTemplateArguments = (template: string): string[] => {
  const matches = template.matchAll(/\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g);
  const seen = new Set<string>();
  const argumentsFromTemplate: string[] = [];
  for (const match of matches) {
    const argumentName = match[1]?.trim();
    if (!argumentName || seen.has(argumentName)) continue;
    seen.add(argumentName);
    argumentsFromTemplate.push(argumentName);
  }
  return argumentsFromTemplate;
};

const safeParsePreviewVariables = (): Record<string, unknown> | null => {
  try {
    const parsed = JSON.parse(previewVarsEl?.value ?? "{}");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : {};
  } catch {
    return null;
  }
};

const sampleValueForArgument = (argumentName: string): string => {
  const normalized = argumentName.toLowerCase();
  if (normalized.includes("language")) return "python";
  if (normalized.includes("step")) return "Test Writing";
  if (normalized.includes("diff")) return "diff --git a/app.py b/app.py";
  if (normalized.includes("error")) return "Traceback: Example failure";
  if (normalized.includes("code")) return "def example():\n    return 42";
  if (normalized.includes("context")) return "Relevant repo context";
  if (normalized.includes("test")) return "FAILED test_example";
  return `sample_${argumentName}`;
};

const setArgumentHints = (argumentNames: string[]) => {
  if (!(argumentHintsEl instanceof HTMLElement)) return;
  if (!argumentNames.length) {
    argumentHintsEl.textContent = "No parameters detected in this prompt.";
    return;
  }
  argumentHintsEl.textContent = `Detected params: ${argumentNames.map((name) => `{${name}}`).join(", ")}`;
};

const synchronizeArgumentState = (options?: { forcePreview?: boolean }) => {
  const templateArguments = extractTemplateArguments(templateEl?.value ?? "");
  const manualArguments = parseArguments();
  const previewVariables = safeParsePreviewVariables();
  const previewArgumentNames = previewVariables
    ? Object.keys(previewVariables)
    : [];
  const nextArguments = Array.from(
    new Set([
      ...templateArguments,
      ...manualArguments,
      ...previewArgumentNames,
    ]),
  );

  if (argumentsEl) {
    argumentsEl.value = nextArguments.join(", ");
  }

  const nextPreviewVariables: Record<string, unknown> = {};
  for (const argumentName of nextArguments) {
    if (previewVariables && argumentName in previewVariables) {
      nextPreviewVariables[argumentName] = previewVariables[argumentName];
    } else {
      nextPreviewVariables[argumentName] = sampleValueForArgument(argumentName);
    }
  }

  if (previewVarsEl && (options?.forcePreview || previewVariables !== null)) {
    previewVarsEl.value = JSON.stringify(nextPreviewVariables, null, 2);
  }

  setArgumentHints(nextArguments);
  return nextArguments;
};

const currentDraft = () => ({
  name: nameEl?.value.trim() ?? "",
  title: titleEl?.value.trim() ?? "",
  description: descriptionEl?.value.trim() ?? "",
  content_template: templateEl?.value ?? "",
  arguments: synchronizeArgumentState(),
});

const fillForm = (prompt?: PromptPayload) => {
  selectedPromptKey = prompt ? promptKey(prompt) : null;
  if (promptIdEl) promptIdEl.value = prompt?.id ?? "";
  if (nameEl) nameEl.value = prompt?.name ?? "";
  if (titleEl) titleEl.value = prompt?.title ?? "";
  if (descriptionEl) descriptionEl.value = prompt?.description ?? "";
  if (argumentsEl) argumentsEl.value = (prompt?.arguments ?? []).join(", ");
  if (templateEl) templateEl.value = prompt?.content_template ?? "";
  synchronizeArgumentState({ forcePreview: true });
  setLlmStatus(
    prompt
      ? prompt.is_builtin
        ? "Loaded built-in prompt. Saving creates a database override with the same name."
        : "Loaded prompt draft."
      : "New draft. Use AI polish before saving if needed.",
  );
  setStatus(statusEl, "", "default");
};

const renderPreview = () => {
  const template = templateEl?.value ?? "";
  if (!template.trim()) {
    setStatus(previewStatusEl, "Prompt template is empty.", "default");
    if (previewOutputEl instanceof HTMLElement) {
      previewOutputEl.textContent =
        "Choose a prompt to preview its rendered output.";
    }
    return;
  }

  let variables: Record<string, unknown> = {};
  try {
    variables = JSON.parse(previewVarsEl?.value ?? "{}");
  } catch {
    setStatus(
      previewStatusEl,
      "Sample variables must be valid JSON.",
      "danger",
    );
    return;
  }

  let output = template;
  for (const [key, value] of Object.entries(variables)) {
    output = output.replaceAll(`{${key}}`, String(value));
  }
  if (previewOutputEl instanceof HTMLElement) {
    previewOutputEl.textContent = output;
  }
  setStatus(previewStatusEl, "Preview updated.", "success");
};

const renderRegistry = () => {
  if (!(registryEl instanceof HTMLElement)) return;

  const pageCount = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
  const start = totalCount === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1;
  const end = Math.min(currentPage * PAGE_SIZE, totalCount);

  setPagerStatus(paginationStatusEl, {
    slice: {
      items: visiblePrompts,
      page: currentPage,
      pageCount,
      total: totalCount,
      start,
      end,
    },
    label: "prompts",
    query: currentQuery,
  });
  updatePagerButtons(
    pagePrevButton,
    pageNextButton,
    currentPage,
    pageCount,
  );

  if (!visiblePrompts.length) {
    registryEl.innerHTML = `
      <article class="shell-card p-6 text-sm text-stone-600">
        ${currentQuery ? `No prompts matched \"${escapeHtml(currentQuery)}\".` : "No prompts yet. Create the first prompt from the editor."}
      </article>
    `;
    return;
  }

  registryEl.innerHTML = visiblePrompts
    .map((prompt) => {
      const activeClass =
        promptKey(prompt) === selectedPromptKey
          ? "border-amber-400 bg-amber-50/70"
          : "border-stone-200 bg-white";
      return `
        <article class="shell-card border ${activeClass} p-5">
          <div class="flex items-start justify-between gap-3">
            <button
              type="button"
              class="min-w-0 flex-1 text-left"
              data-prompt-select="${escapeHtml(prompt.id)}"
            >
              <p class="eyebrow">${escapeHtml(prompt.name)}</p>
              <h2 class="mt-2 text-xl font-semibold tracking-tight text-stone-950">
                ${escapeHtml(prompt.title || prompt.name)}
              </h2>
              <div class="mt-2 flex flex-wrap gap-2">
                ${prompt.is_builtin ? '<span class="rounded-full border border-amber-200 bg-amber-100 px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.18em] text-amber-800">Built-in</span>' : '<span class="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.18em] text-emerald-800">Custom</span>'}
              </div>
              <p class="mt-2 text-sm leading-6 text-stone-600">
                ${escapeHtml(prompt.description || "No description.")}
              </p>
              <div class="mt-4 flex flex-wrap gap-2">
                ${(prompt.arguments ?? []).map((argument) => `<span class="rounded-full border border-stone-200 bg-stone-50 px-2.5 py-1 text-[11px] text-stone-500">{${escapeHtml(argument)}}</span>`).join("") || '<span class="text-xs text-stone-400">No arguments</span>'}
              </div>
            </button>
            ${
              prompt.is_builtin
                ? '<span class="rounded-xl border border-stone-200 px-3 py-1.5 text-xs text-stone-500">Runtime default</span>'
                : `<button
              type="button"
              class="rounded-xl border border-red-200 px-3 py-1.5 text-xs text-red-700 transition hover:bg-red-50"
              data-prompt-delete="${escapeHtml(prompt.id)}"
            >
              Delete
            </button>`
            }
          </div>
        </article>
      `;
    })
    .join("");

  registryEl
    .querySelectorAll<HTMLButtonElement>("[data-prompt-select]")
    .forEach((button) => {
      button.addEventListener("click", () => {
        const prompt = visiblePrompts.find(
          (item) => item.id === button.dataset.promptSelect,
        );
        if (!prompt) return;
        fillForm(prompt);
        renderRegistry();
        renderPreview();
      });
    });

  registryEl
    .querySelectorAll<HTMLButtonElement>("[data-prompt-delete]")
    .forEach((button) => {
      button.addEventListener("click", async () => {
        const promptId = button.dataset.promptDelete;
        const prompt = visiblePrompts.find((item) => item.id === promptId);
        if (!promptId || !prompt) return;
        const confirmed = await showDangerConfirm(`Delete prompt ${prompt.name}?`);
        if (!confirmed) return;
        try {
          await deletePrompt(promptId);
          if (selectedPromptKey === promptId) {
            fillForm();
          }
          await syncVisiblePrompts();
          showToast(`Deleted ${prompt.name}.`, "success");
        } catch (error) {
          showToast(
            error instanceof Error ? error.message : "Unable to delete prompt.",
            "danger",
          );
        }
      });
    });
};

const syncVisiblePrompts = async () => {
  if (registryEl instanceof HTMLElement) {
    registryEl.innerHTML = `<article class="shell-card p-6 text-sm text-stone-600">Loading prompts...</article>`;
  }
  try {
    const result = await searchAdminCatalog<PromptPayload>(
      "prompts",
      currentQuery,
      PAGE_SIZE,
      (currentPage - 1) * PAGE_SIZE,
    );
    visiblePrompts = result.items;
    totalCount = result.total;
    renderRegistry();
  } catch (error) {
    if (registryEl instanceof HTMLElement) {
      registryEl.innerHTML = `<article class="shell-card p-6 text-sm text-red-700">${escapeHtml(error instanceof Error ? error.message : "Unable to load prompts.")}</article>`;
    }
  }
};

document
  .querySelector("#prompt-refresh-button")
  ?.addEventListener("click", () => {
    void syncVisiblePrompts();
  });

document
  .querySelector("#prompt-reset-button")
  ?.addEventListener("click", () => {
    fillForm();
    renderRegistry();
    renderPreview();
  });

pagePrevButton?.addEventListener("click", () => {
  currentPage = Math.max(1, currentPage - 1);
  void syncVisiblePrompts();
});

pageNextButton?.addEventListener("click", () => {
  currentPage += 1;
  void syncVisiblePrompts();
});

const debouncedSearch = createDebouncedHandler(async () => {
  currentQuery = quickSearchEl?.value.trim() ?? "";
  currentPage = 1;
  await syncVisiblePrompts();
  quickSearchLoadingEl?.classList.add("hidden");
});

quickSearchEl?.addEventListener("input", () => {
  quickSearchLoadingEl?.classList.remove("hidden");
  debouncedSearch();
});

document
  .querySelector("#prompt-preview-button")
  ?.addEventListener("click", renderPreview);

templateEl?.addEventListener("input", () => {
  synchronizeArgumentState({ forcePreview: true });
});

argumentsEl?.addEventListener("input", () => {
  synchronizeArgumentState({ forcePreview: true });
});

previewVarsEl?.addEventListener("input", () => {
  const previewVariables = safeParsePreviewVariables();
  if (previewVariables !== null) {
    synchronizeArgumentState();
  }
});

document
  .querySelector("#prompt-polish-button")
  ?.addEventListener("click", async () => {
    const draft = currentDraft();
    if (!draft.name.trim()) {
      setStatus(statusEl, "Name is required before polishing.", "danger");
      return;
    }
    setStatus(statusEl, "Polishing prompt with minder AI...", "default");
    try {
      const result = await polishPromptDraft(draft);
      if (titleEl) titleEl.value = result.title;
      if (descriptionEl) descriptionEl.value = result.description;
      if (templateEl) templateEl.value = result.content_template;
      if (argumentsEl) argumentsEl.value = result.arguments.join(", ");
      setLlmStatus(
        `Polished via ${result.llm.provider} · ${result.llm.model} (${result.llm.runtime})`,
      );
      setStatus(statusEl, "Prompt polished.", "success");
      renderPreview();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to polish prompt.";
      setStatus(statusEl, message, "danger");
      showToast(message, "danger");
    }
  });

formEl?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const draft = currentDraft();
  const currentPromptId = promptIdEl?.value.trim() ?? "";
  const isUpdate = Boolean(currentPromptId && !isBuiltinId(currentPromptId));
  if (!draft.name.trim()) {
    setStatus(statusEl, "Name is required.", "danger");
    return;
  }
  if (!draft.content_template.trim()) {
    setStatus(statusEl, "Content template is required.", "danger");
    return;
  }

  setStatus(
    statusEl,
    isUpdate ? "Saving prompt changes..." : "Creating prompt...",
    "default",
  );
  try {
    const saved = isUpdate
      ? await updatePrompt(currentPromptId, draft)
      : await createPrompt(draft);
    selectedPromptKey = saved.id;
    fillForm(saved);
    await syncVisiblePrompts();
    renderPreview();
    showToast(
      `${isUpdate ? "Saved" : "Created"} prompt ${saved.name}.`,
      "success",
    );
    setStatus(statusEl, "Prompt saved and synced.", "success");
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unable to save prompt.";
    setStatus(statusEl, message, "danger");
    showToast(message, "danger");
  }
});

fillForm();
void syncVisiblePrompts();
renderPreview();
