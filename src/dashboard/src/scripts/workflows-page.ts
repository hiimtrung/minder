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
import { showConfirm, showPrompt, showDangerConfirm } from "./modal-controller";

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
  onEdit: (index: number) => void,
) => {
  if (!container) return;
  if (!steps.length) {
    container.innerHTML = `<p class="px-1 text-xs text-stone-400">No steps yet — add the first one above.</p>`;
    return;
  }
  container.innerHTML = steps
    .map(
      (step, i) => `
    <div class="flex min-w-0 items-start gap-3 overflow-hidden rounded-2xl border border-stone-200 bg-stone-50/80 p-3">
      <div class="flex-1 grid gap-1 min-w-0">
        <div class="flex min-w-0 items-center gap-2">
          <span class="shrink-0 text-xs font-semibold uppercase tracking-[0.12em] text-amber-700">${i + 1}</span>
          <span class="min-w-0 truncate text-sm font-semibold text-stone-900">${escapeHtml(step.name)}</span>
          ${step.gate ? `<span class="shrink-0 rounded-full border border-stone-300 bg-white px-2 py-0.5 text-[10px] text-stone-500">gate: ${escapeHtml(step.gate)}</span>` : ""}
        </div>
        ${step.description ? `<p class="break-words text-xs leading-5 text-stone-500">${escapeHtml(step.description)}</p>` : ""}
      </div>
      <div class="flex items-center gap-1 shrink-0">
        <button
          type="button"
          data-edit-step="${i}"
          class="rounded-lg px-2 py-1 text-xs text-stone-400 hover:text-stone-900 hover:bg-stone-200/50 transition"
          aria-label="Edit step ${i + 1}"
        >Edit</button>
        <button
          type="button"
          data-remove-step="${i}"
          class="rounded-lg px-2 py-1 text-xs text-stone-400 hover:text-red-600 hover:bg-red-50 transition"
          aria-label="Remove step ${i + 1}"
        >✕</button>
      </div>
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

  container
    .querySelectorAll<HTMLButtonElement>("[data-edit-step]")
    .forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = parseInt(btn.dataset.editStep ?? "-1", 10);
        if (idx >= 0) onEdit(idx);
      });
    });
};

const openStepModal = (
  mode: "add" | "edit",
  initialData?: WorkflowStepPayload,
): Promise<WorkflowStepPayload | null> => {
  return new Promise((resolve) => {
    const backdrop = document.getElementById("step-modal-backdrop");
    const container = document.getElementById("step-modal-container");
    const title = document.getElementById("step-modal-title");
    const form = document.getElementById("step-modal-form") as HTMLFormElement | null;
    const nameInput = document.getElementById("step-name") as HTMLTextAreaElement | null;
    const descInput = document.getElementById("step-description") as HTMLTextAreaElement | null;
    const gateInput = document.getElementById("step-gate") as HTMLTextAreaElement | null;
    const cancelBtn = document.getElementById("step-modal-cancel");

    if (!backdrop || !container || !title || !form || !nameInput || !descInput || !gateInput || !cancelBtn) {
      resolve(null);
      return;
    }

    title.textContent = mode === "add" ? "Add Step" : "Edit Step";
    nameInput.value = initialData?.name ?? "";
    descInput.value = initialData?.description ?? "";
    gateInput.value = initialData?.gate ?? "";

    const close = (result: WorkflowStepPayload | null) => {
      backdrop.classList.remove("flex", "opacity-100");
      backdrop.classList.add("hidden", "opacity-0");
      container.classList.remove("scale-100", "opacity-100");
      container.classList.add("scale-95", "opacity-0");
      form.onsubmit = null;
      cancelBtn.onclick = null;
      resolve(result);
    };

    cancelBtn.onclick = () => close(null);
    form.onsubmit = (e) => {
      e.preventDefault();
      close({
        name: nameInput.value.trim(),
        description: descInput.value.trim(),
        gate: gateInput.value.trim() || null,
      });
    };

    backdrop.classList.remove("hidden");
    backdrop.classList.add("flex");
    void backdrop.offsetWidth;
    backdrop.classList.add("opacity-100");
    container.classList.add("scale-100", "opacity-100");
    nameInput.focus();
  });
};

const promptAddStep = async (onConfirm: (step: WorkflowStepPayload) => void) => {
  const result = await openStepModal("add");
  if (result && result.name) {
    onConfirm(result);
  }
};

const promptEditStep = async (
  initialData: WorkflowStepPayload,
  onConfirm: (step: WorkflowStepPayload) => void,
) => {
  const result = await openStepModal("edit", initialData);
  if (result && result.name) {
    onConfirm(result);
  }
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
  renderStepList(
    stepsListEl,
    createSteps,
    (idx) => {
      createSteps.splice(idx, 1);
      refreshCreateStepList();
    },
    async (idx) => {
      await promptEditStep(createSteps[idx], (updated) => {
        createSteps[idx] = updated;
        refreshCreateStepList();
      });
    },
  );
};

addStepButton?.addEventListener("click", async () => {
  await promptAddStep((step) => {
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
  renderStepList(
    stepEditorList,
    detailSteps,
    (idx) => {
      detailSteps.splice(idx, 1);
      refreshDetailStepList();
    },
    async (idx) => {
      await promptEditStep(detailSteps[idx], (updated) => {
        detailSteps[idx] = updated;
        refreshDetailStepList();
      });
    },
  );
};

addStepDetailButton?.addEventListener("click", async () => {
  await promptAddStep((step) => {
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
  const confirmed = await showDangerConfirm(
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
