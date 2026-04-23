import {
  createWorkflow,
  deleteWorkflow,
  getWorkflowDetail,
  listWorkflows,
  searchAdminCatalog,
  updateWorkflow,
  type WorkflowPayload,
  type WorkflowStepPayload,
} from "../lib/api/admin";
import {
  createDebouncedHandler,
  paginateItems,
  setPagerStatus,
  updatePagerButtons,
} from "./catalog-controls";

// ---------------------------------------------------------------------------
// Shared element refs
// ---------------------------------------------------------------------------

const toastRegion = document.querySelector("#dashboard-toast-region");

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

const escapeHtml = (value: string): string =>
  value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

// ---------------------------------------------------------------------------
// Current URL path parsing — detect registry vs detail route
// ---------------------------------------------------------------------------

const currentPath = window.location.pathname.replace(/\/$/, "");
const pathSegments = currentPath.split("/").filter(Boolean);
const selectedWorkflowId =
  pathSegments.length > 2 &&
  pathSegments[0] === "dashboard" &&
  pathSegments[1] === "workflows"
    ? decodeURIComponent(pathSegments.at(-1) ?? "") || null
    : null;

// ---------------------------------------------------------------------------
// In-memory step state for create / detail forms
// ---------------------------------------------------------------------------

let createSteps: WorkflowStepPayload[] = [];
let detailSteps: WorkflowStepPayload[] = [];

const renderStepList = (
  container: Element | null,
  steps: WorkflowStepPayload[],
  onRemove: (index: number) => void,
) => {
  if (!container) return;
  if (!steps.length) {
    container.innerHTML = `<p class="px-1 text-xs text-stone-400">No steps yet — add the first one above.</p>`;
    return;
  }
  container.innerHTML = steps
    .map(
      (step, i) => `
    <div class="flex items-start gap-3 rounded-2xl border border-stone-200 bg-stone-50/80 p-3">
      <div class="flex-1 grid gap-1 min-w-0">
        <div class="flex items-center gap-2">
          <span class="text-xs font-semibold uppercase tracking-[0.12em] text-amber-700">${i + 1}</span>
          <span class="text-sm font-semibold text-stone-900 truncate">${escapeHtml(step.name)}</span>
          ${step.gate ? `<span class="rounded-full border border-stone-300 bg-white px-2 py-0.5 text-[10px] text-stone-500">gate: ${escapeHtml(step.gate)}</span>` : ""}
        </div>
        ${step.description ? `<p class="text-xs text-stone-500 leading-5">${escapeHtml(step.description)}</p>` : ""}
      </div>
      <button
        type="button"
        data-remove-step="${i}"
        class="shrink-0 rounded-lg px-2 py-1 text-xs text-stone-400 hover:text-red-600 transition"
        aria-label="Remove step ${i + 1}"
      >✕</button>
    </div>
  `,
    )
    .join("");

  container
    .querySelectorAll<HTMLButtonElement>("[data-remove-step]")
    .forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = parseInt(btn.dataset.removeStep ?? "-1", 10);
        if (idx >= 0) onRemove(idx);
      });
    });
};

const promptAddStep = (onConfirm: (step: WorkflowStepPayload) => void) => {
  const name = window.prompt("Step name (e.g. write_test):", "")?.trim() ?? "";
  if (!name) return;
  const description = window.prompt("Step description:", "")?.trim() ?? "";
  const gate =
    window.prompt("Gate condition (leave blank for none):", "")?.trim() || null;
  onConfirm({ name, description, gate });
};

// ---------------------------------------------------------------------------
// Registry page — workflow list + create form
// ---------------------------------------------------------------------------

const workflowRegistry = document.querySelector("#workflow-registry");
const createWorkflowForm = document.querySelector("#create-workflow-form");
const createStatusEl = document.querySelector("#create-workflow-status");
const stepsListEl = document.querySelector("#workflow-steps-list");
const addStepButton = document.querySelector("#add-step-button");
const quickSearchEl = document.querySelector(
  "#workflow-quick-search",
) as HTMLInputElement | null;
const paginationStatusEl = document.querySelector(
  "#workflow-pagination-status",
);
const pagePrevButton = document.querySelector("#workflow-page-prev");
const pageNextButton = document.querySelector("#workflow-page-next");
const quickSearchLoadingEl = document.querySelector("#workflow-quick-search-loading");

const PAGE_SIZE = 6;
let allWorkflows: WorkflowPayload[] = [];
let visibleWorkflows: WorkflowPayload[] = [];
let currentQuery = "";
let currentPage = 1;

const setCreateStatus = (
  message: string,
  tone: "default" | "success" | "danger" = "default",
) => {
  if (!createStatusEl) return;
  createStatusEl.textContent = message;
  createStatusEl.className = "min-h-6 text-sm";
  if (tone === "success") createStatusEl.classList.add("text-emerald-700");
  else if (tone === "danger") createStatusEl.classList.add("text-red-700");
  else createStatusEl.classList.add("text-stone-600");
};

const refreshCreateStepList = () => {
  renderStepList(stepsListEl, createSteps, (idx) => {
    createSteps.splice(idx, 1);
    refreshCreateStepList();
  });
};

addStepButton?.addEventListener("click", () => {
  promptAddStep((step) => {
    createSteps.push(step);
    refreshCreateStepList();
  });
});

const renderWorkflows = () => {
  if (!workflowRegistry) return;
  const slice = paginateItems(visibleWorkflows, currentPage, PAGE_SIZE);
  currentPage = slice.page;
  setPagerStatus(paginationStatusEl, {
    slice,
    label: "workflows",
    query: currentQuery,
  });
  updatePagerButtons(
    pagePrevButton,
    pageNextButton,
    slice.page,
    slice.pageCount,
  );

  workflowRegistry.innerHTML = visibleWorkflows.length
    ? slice.items
        .map(
          (w) => `
          <a href="/dashboard/workflows/${encodeURIComponent(w.id)}" class="shell-card block p-6 transition hover:-translate-y-0.5">
            <p class="eyebrow">${escapeHtml(w.enforcement)}</p>
            <h2 class="mt-3 text-2xl font-semibold tracking-tight text-stone-950">${escapeHtml(w.name)}</h2>
            <p class="mt-3 text-sm leading-6 text-stone-700">${escapeHtml(w.description || "No description.")}</p>
            <p class="mt-5 text-sm text-stone-500">${w.steps.length} step${w.steps.length !== 1 ? "s" : ""}</p>
          </a>
        `,
        )
        .join("")
    : `<article class="shell-card p-6 text-sm text-stone-600">${currentQuery ? `No workflows matched \"${escapeHtml(currentQuery)}\".` : "No workflows yet. Create the first one from this page."}</article>`;
};

const syncVisibleWorkflows = async () => {
  if (!currentQuery) {
    visibleWorkflows = allWorkflows;
    renderWorkflows();
    return;
  }
  const result = await searchAdminCatalog<WorkflowPayload>(
    "workflows",
    currentQuery,
    200,
    0,
  );
  visibleWorkflows = result.items;
  renderWorkflows();
};

const refreshWorkflows = async () => {
  if (!workflowRegistry) return;
  workflowRegistry.innerHTML = `<article class="shell-card p-6 text-sm text-stone-600">Loading workflows...</article>`;
  try {
    const payload = await listWorkflows();
    allWorkflows = payload.workflows;
    await syncVisibleWorkflows();
  } catch (error) {
    workflowRegistry.innerHTML = `<article class="shell-card p-6 text-sm text-red-700">${
      error instanceof Error ? error.message : "Unable to load workflows."
    }</article>`;
  }
};

createWorkflowForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const name =
    (
      document.querySelector("#workflow-name") as HTMLInputElement | null
    )?.value.trim() ?? "";
  const description =
    (
      document.querySelector(
        "#workflow-description",
      ) as HTMLTextAreaElement | null
    )?.value.trim() ?? "";
  const enforcement =
    (
      document.querySelector(
        "#workflow-enforcement",
      ) as HTMLSelectElement | null
    )?.value ?? "strict";

  if (!name) {
    setCreateStatus("Name is required.", "danger");
    return;
  }

  setCreateStatus("Creating workflow...");
  try {
    const result = await createWorkflow({
      name,
      description,
      enforcement,
      steps: createSteps,
    });
    setCreateStatus(`Created ${result.workflow.name}.`, "success");
    showToast(`Created workflow ${result.workflow.name}.`, "success");
    createSteps = [];
    refreshCreateStepList();
    (document.querySelector("#workflow-name") as HTMLInputElement | null) &&
      ((document.querySelector("#workflow-name") as HTMLInputElement).value =
        "");
    (document.querySelector(
      "#workflow-description",
    ) as HTMLTextAreaElement | null) &&
      ((
        document.querySelector("#workflow-description") as HTMLTextAreaElement
      ).value = "");
    await refreshWorkflows();
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unable to create workflow.";
    setCreateStatus(message, "danger");
    showToast(message, "danger");
  }
});

pagePrevButton?.addEventListener("click", () => {
  currentPage = Math.max(1, currentPage - 1);
  renderWorkflows();
});

pageNextButton?.addEventListener("click", () => {
  currentPage += 1;
  renderWorkflows();
});

const debouncedSearch = createDebouncedHandler(async () => {
  currentQuery = quickSearchEl?.value.trim() ?? "";
  currentPage = 1;
  await syncVisibleWorkflows();
  quickSearchLoadingEl?.classList.add("hidden");
});

quickSearchEl?.addEventListener("input", () => {
  quickSearchLoadingEl?.classList.remove("hidden");
  debouncedSearch();
});

// ---------------------------------------------------------------------------
// Detail page — workflow editor
// ---------------------------------------------------------------------------

const detailTitleEl = document.querySelector("#workflow-detail-title");
const editWorkflowForm = document.querySelector("#edit-workflow-form");
const editWorkflowName = document.querySelector(
  "#edit-workflow-name",
) as HTMLInputElement | null;
const editWorkflowDesc = document.querySelector(
  "#edit-workflow-description",
) as HTMLTextAreaElement | null;
const editWorkflowEnforcement = document.querySelector(
  "#edit-workflow-enforcement",
) as HTMLSelectElement | null;
const editWorkflowStatus = document.querySelector("#edit-workflow-status");
const stepEditorList = document.querySelector("#step-editor-list");
const addStepDetailButton = document.querySelector("#add-step-detail-button");
const saveStepsButton = document.querySelector("#save-steps-button");
const stepsStatusEl = document.querySelector("#steps-status");
const deleteWorkflowButton = document.querySelector("#delete-workflow-button");
const deleteStatusEl = document.querySelector("#delete-workflow-status");

const setEditStatus = (
  message: string,
  tone: "default" | "success" | "danger" = "default",
) => {
  if (!editWorkflowStatus) return;
  editWorkflowStatus.textContent = message;
  editWorkflowStatus.className = "min-h-6 text-sm";
  if (tone === "success") editWorkflowStatus.classList.add("text-emerald-700");
  else if (tone === "danger") editWorkflowStatus.classList.add("text-red-700");
  else editWorkflowStatus.classList.add("text-stone-600");
};

const setStepsStatus = (
  message: string,
  tone: "default" | "success" | "danger" = "default",
) => {
  if (!stepsStatusEl) return;
  stepsStatusEl.textContent = message;
  stepsStatusEl.className = "mt-3 min-h-6 text-sm";
  if (tone === "success") stepsStatusEl.classList.add("text-emerald-700");
  else if (tone === "danger") stepsStatusEl.classList.add("text-red-700");
  else stepsStatusEl.classList.add("text-stone-600");
};

const refreshDetailStepList = () => {
  renderStepList(stepEditorList, detailSteps, (idx) => {
    detailSteps.splice(idx, 1);
    refreshDetailStepList();
  });
};

addStepDetailButton?.addEventListener("click", () => {
  promptAddStep((step) => {
    detailSteps.push(step);
    refreshDetailStepList();
  });
});

saveStepsButton?.addEventListener("click", async () => {
  if (!selectedWorkflowId) return;
  setStepsStatus("Saving steps...");
  try {
    await updateWorkflow(selectedWorkflowId, { steps: detailSteps });
    setStepsStatus("Steps saved.", "success");
    showToast("Steps saved.", "success");
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unable to save steps.";
    setStepsStatus(message, "danger");
    showToast(message, "danger");
  }
});

const renderDetail = async () => {
  if (!selectedWorkflowId || !detailTitleEl) return;
  try {
    const { workflow } = await getWorkflowDetail(selectedWorkflowId);
    document.title = `${workflow.name} · Minder`;
    detailTitleEl.textContent = workflow.name;
    if (editWorkflowName) editWorkflowName.value = workflow.name;
    if (editWorkflowDesc) editWorkflowDesc.value = workflow.description;
    if (editWorkflowEnforcement)
      editWorkflowEnforcement.value = workflow.enforcement;
    detailSteps = workflow.steps.map((s) => ({ ...s }));
    refreshDetailStepList();
  } catch (error) {
    if (detailTitleEl) {
      detailTitleEl.textContent = "Workflow not found";
    }
    setEditStatus(
      error instanceof Error ? error.message : "Unable to load workflow.",
      "danger",
    );
  }
};

editWorkflowForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedWorkflowId) return;
  const name = editWorkflowName?.value.trim() ?? "";
  const description = editWorkflowDesc?.value.trim() ?? "";
  const enforcement = editWorkflowEnforcement?.value ?? "strict";

  if (!name) {
    setEditStatus("Name is required.", "danger");
    return;
  }

  setEditStatus("Saving changes...");
  try {
    const result = await updateWorkflow(selectedWorkflowId, {
      name,
      description,
      enforcement,
    });
    document.title = `${result.workflow.name} · Minder`;
    if (detailTitleEl) detailTitleEl.textContent = result.workflow.name;
    setEditStatus("Changes saved.", "success");
    showToast(`Saved ${result.workflow.name}.`, "success");
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unable to save changes.";
    setEditStatus(message, "danger");
    showToast(message, "danger");
  }
});

deleteWorkflowButton?.addEventListener("click", async () => {
  if (!selectedWorkflowId) return;
  const confirmed = window.confirm(
    "Delete this workflow? This cannot be undone and will remove the workflow assignment from all repositories using it.",
  );
  if (!confirmed) return;
  if (deleteStatusEl) deleteStatusEl.textContent = "Deleting...";
  try {
    await deleteWorkflow(selectedWorkflowId);
    showToast("Workflow deleted.", "success");
    window.location.href = "/dashboard/workflows";
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unable to delete workflow.";
    if (deleteStatusEl) deleteStatusEl.textContent = message;
    showToast(message, "danger");
  }
});

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

void refreshWorkflows();
void renderDetail();
