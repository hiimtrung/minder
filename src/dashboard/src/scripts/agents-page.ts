import {
  createAgent,
  deleteAgent,
  getAgentDetail,
  listAgents,
  listTools,
  updateAgent,
  type AgentPayload,
  type ToolInfo,
} from "../lib/api/admin";
import {
  createDebouncedHandler,
  paginateItems,
  setPagerStatus,
  updatePagerButtons,
} from "./catalog-controls";
import { showDangerConfirm } from "./modal-controller";
import { escapeHtml, getEl, showToast } from "./ui-utils";

// ---------------------------------------------------------------------------
// Route detection
// ---------------------------------------------------------------------------

const currentPath = window.location.pathname.replace(/\/$/, "");
const pathSegments = currentPath.split("/").filter(Boolean);
const selectedAgentId =
  pathSegments.length > 2 &&
  pathSegments[0] === "dashboard" &&
  pathSegments[1] === "agents"
    ? decodeURIComponent(pathSegments.at(-1) ?? "") || null
    : null;

// ---------------------------------------------------------------------------
// Shared tool list cache
// ---------------------------------------------------------------------------

let cachedTools: ToolInfo[] = [];

const loadTools = async (): Promise<ToolInfo[]> => {
  if (!cachedTools.length) {
    const payload = await listTools();
    cachedTools = payload.tools;
  }
  return cachedTools;
};

// ---------------------------------------------------------------------------
// Tool checkbox helpers
// ---------------------------------------------------------------------------

const renderToolCheckboxes = (
  containerId: string,
  inputPrefix: string,
  tools: ToolInfo[],
  selected: string[],
) => {
  const container = getEl(containerId);
  if (!container) return;
  if (!tools.length) {
    container.innerHTML = `<p class="px-1 text-sm text-stone-400">No tools available.</p>`;
    return;
  }
  container.innerHTML = tools
    .map((tool) => {
      const checked = selected.includes(tool.name) ? "checked" : "";
      const id = `${inputPrefix}-${tool.name}`;
      return `
        <label for="${id}" class="flex cursor-pointer items-start gap-3 rounded-xl px-2 py-2 hover:bg-stone-50">
          <input
            type="checkbox"
            id="${id}"
            name="${inputPrefix}"
            value="${escapeHtml(tool.name)}"
            ${checked}
            class="mt-0.5 h-4 w-4 shrink-0 rounded border-stone-300 accent-amber-600"
          />
          <span class="grid gap-0.5">
            <code class="text-xs font-semibold text-stone-900">${escapeHtml(tool.name)}</code>
            <span class="text-xs leading-5 text-stone-500">${escapeHtml(tool.description)}</span>
          </span>
        </label>
      `;
    })
    .join("");
};

const getCheckedTools = (containerId: string, inputPrefix: string): string[] => {
  const container = getEl(containerId);
  if (!container) return [];
  return Array.from(
    container.querySelectorAll<HTMLInputElement>(
      `input[name="${inputPrefix}"]:checked`,
    ),
  ).map((cb) => cb.value);
};

const toggleAllTools = (containerId: string, inputPrefix: string, state: boolean) => {
  const container = getEl(containerId);
  if (!container) return;
  container
    .querySelectorAll<HTMLInputElement>(`input[name="${inputPrefix}"]`)
    .forEach((cb) => { cb.checked = state; });
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const parseList = (raw: string): string[] =>
  raw.split(/[\n,]+/).map((s) => s.trim()).filter(Boolean);

// ---------------------------------------------------------------------------
// Registry page
// ---------------------------------------------------------------------------

const agentRegistryEl = document.querySelector("#agent-registry");
const agentFormDialogEl = document.querySelector("#agent-form-dialog") as HTMLDialogElement | null;
const createAgentForm = getEl<HTMLFormElement>("create-agent-form");
const createStatusEl = getEl("create-agent-status");

const quickSearchEl = getEl<HTMLInputElement>("agent-quick-search");
const paginationStatusEl = getEl("agent-pagination-status");
const pagePrevButton = getEl("agent-page-prev");
const pageNextButton = getEl("agent-page-next");
const quickSearchLoadingEl = getEl("agent-quick-search-loading");

const PAGE_SIZE = 6;
let allAgents: AgentPayload[] = [];
let visibleAgents: AgentPayload[] = [];
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

const renderAgents = () => {
  if (!agentRegistryEl) return;
  const slice = paginateItems(visibleAgents, currentPage, PAGE_SIZE);
  currentPage = slice.page;
  setPagerStatus(paginationStatusEl, { slice, label: "agents", query: currentQuery });
  updatePagerButtons(pagePrevButton, pageNextButton, slice.page, slice.pageCount);

  agentRegistryEl.innerHTML = visibleAgents.length
    ? slice.items
        .map(
          (a) => `
          <a href="/dashboard/agents/${encodeURIComponent(a.id)}" class="shell-card block p-6 transition hover:-translate-y-0.5">
            <div class="flex flex-wrap items-center gap-2">
              <p class="eyebrow">${escapeHtml(a.is_default ? "default" : "custom")}</p>
              ${a.workflow_steps.length ? `<span class="rounded-full border border-stone-300 bg-white px-2 py-0.5 text-[10px] text-stone-500">${a.workflow_steps.map(escapeHtml).join(", ")}</span>` : ""}
            </div>
            <h2 class="font-display mt-3 text-xl font-semibold tracking-tight text-stone-950">${escapeHtml(a.title || a.name)}</h2>
            <p class="mt-1 font-mono text-xs text-stone-500">${escapeHtml(a.name)}</p>
            <p class="mt-3 text-sm leading-6 text-stone-700">${escapeHtml(a.description || "No description.")}</p>
            <div class="mt-4 flex flex-wrap gap-1">
              ${a.tags.map((t) => `<span class="rounded-full bg-stone-100 px-2 py-0.5 text-[10px] text-stone-600">${escapeHtml(t)}</span>`).join("")}
            </div>
            <p class="mt-4 text-xs text-stone-400">${a.tools.length} tool${a.tools.length !== 1 ? "s" : ""}</p>
          </a>
        `,
        )
        .join("")
    : `<article class="shell-card p-6 text-sm text-stone-600">${
        currentQuery
          ? `No agents matched "${escapeHtml(currentQuery)}".`
          : "No agents yet. Create the first one from this page."
      }</article>`;
};

const filterAgents = (query: string): AgentPayload[] => {
  if (!query) return allAgents;
  const q = query.toLowerCase();
  return allAgents.filter(
    (a) =>
      a.name.toLowerCase().includes(q) ||
      a.title.toLowerCase().includes(q) ||
      a.description.toLowerCase().includes(q) ||
      a.tags.some((t) => t.toLowerCase().includes(q)) ||
      a.workflow_steps.some((s) => s.toLowerCase().includes(q)),
  );
};

const syncVisibleAgents = () => {
  visibleAgents = filterAgents(currentQuery);
  renderAgents();
};

const refreshAgents = async () => {
  if (!agentRegistryEl) return;
  agentRegistryEl.innerHTML = `<article class="shell-card p-6 text-sm text-stone-600">Loading agents...</article>`;
  try {
    const payload = await listAgents();
    allAgents = payload.agents;
    syncVisibleAgents();
  } catch (error) {
    agentRegistryEl.innerHTML = `<article class="shell-card p-6 text-sm text-red-700">${
      error instanceof Error ? error.message : "Unable to load agents."
    }</article>`;
  }
};

const loadCreateTools = async () => {
  const container = getEl("create-agent-tools");
  if (!container) return;
  container.innerHTML = `<p class="px-1 text-sm text-stone-400">Loading tools...</p>`;
  try {
    const tools = await loadTools();
    renderToolCheckboxes("create-agent-tools", "create_agent_tool", tools, []);
  } catch {
    container.innerHTML = `<p class="px-1 text-sm text-red-600">Failed to load tools.</p>`;
  }
};

getEl("agent-new-button")?.addEventListener("click", () => {
  agentFormDialogEl?.showModal();
  void loadCreateTools();
});

getEl("agent-close-dialog")?.addEventListener("click", () => {
  agentFormDialogEl?.close();
});

agentFormDialogEl?.addEventListener("click", (event) => {
  if (event.target === agentFormDialogEl) agentFormDialogEl.close();
});

getEl("create-agent-tools-all")?.addEventListener("click", () =>
  toggleAllTools("create-agent-tools", "create_agent_tool", true),
);
getEl("create-agent-tools-none")?.addEventListener("click", () =>
  toggleAllTools("create-agent-tools", "create_agent_tool", false),
);

createAgentForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = getEl<HTMLInputElement>("agent-name")?.value.trim() ?? "";
  const title = getEl<HTMLInputElement>("agent-title")?.value.trim() ?? "";
  const description = getEl<HTMLTextAreaElement>("agent-description")?.value.trim() ?? "";
  const systemPrompt = getEl<HTMLTextAreaElement>("agent-system-prompt")?.value.trim() ?? "";
  const workflowStepsRaw = getEl<HTMLInputElement>("agent-workflow-steps")?.value ?? "";
  const tagsRaw = getEl<HTMLInputElement>("agent-tags")?.value ?? "";
  const tools = getCheckedTools("create-agent-tools", "create_agent_tool");

  if (!name) {
    setCreateStatus("Name is required.", "danger");
    return;
  }

  setCreateStatus("Creating agent...");
  try {
    const result = await createAgent({
      name,
      title,
      description,
      system_prompt: systemPrompt,
      tools,
      workflow_steps: parseList(workflowStepsRaw),
      tags: parseList(tagsRaw),
    });
    setCreateStatus(`Created ${result.agent.title || result.agent.name}.`, "success");
    showToast(`Created agent ${result.agent.title || result.agent.name}.`, "success");
    agentFormDialogEl?.close();
    createAgentForm.reset();
    await loadCreateTools();
    await refreshAgents();
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to create agent.";
    setCreateStatus(message, "danger");
    showToast(message, "danger");
  }
});

pagePrevButton?.addEventListener("click", () => {
  currentPage = Math.max(1, currentPage - 1);
  renderAgents();
});
pageNextButton?.addEventListener("click", () => {
  currentPage += 1;
  renderAgents();
});

const debouncedSearch = createDebouncedHandler(async () => {
  currentQuery = quickSearchEl?.value.trim() ?? "";
  currentPage = 1;
  syncVisibleAgents();
  quickSearchLoadingEl?.classList.add("hidden");
});
quickSearchEl?.addEventListener("input", () => {
  quickSearchLoadingEl?.classList.remove("hidden");
  debouncedSearch();
});

// ---------------------------------------------------------------------------
// Detail page
// ---------------------------------------------------------------------------

const detailTitleEl = document.querySelector("#agent-detail-title");
const editAgentForm = getEl<HTMLFormElement>("edit-agent-form");
const editNameEl = getEl<HTMLInputElement>("edit-agent-name");
const editTitleEl = getEl<HTMLInputElement>("edit-agent-title");
const editDescEl = getEl<HTMLTextAreaElement>("edit-agent-description");
const editSystemPromptEl = getEl<HTMLTextAreaElement>("edit-agent-system-prompt");
const editWorkflowStepsEl = getEl<HTMLInputElement>("edit-agent-workflow-steps");
const editArtifactTypesEl = getEl<HTMLInputElement>("edit-agent-artifact-types");
const editTagsEl = getEl<HTMLInputElement>("edit-agent-tags");
const editIsDefaultEl = getEl<HTMLInputElement>("edit-agent-is-default");
const editStatusEl = getEl("edit-agent-status");
const deleteAgentButton = getEl("delete-agent-button");
const deleteStatusEl = getEl("delete-agent-status");

const setEditStatus = (
  message: string,
  tone: "default" | "success" | "danger" = "default",
) => {
  if (!editStatusEl) return;
  editStatusEl.textContent = message;
  editStatusEl.className = "min-h-6 text-sm";
  if (tone === "success") editStatusEl.classList.add("text-emerald-700");
  else if (tone === "danger") editStatusEl.classList.add("text-red-700");
  else editStatusEl.classList.add("text-stone-600");
};

const renderDetail = async () => {
  if (!selectedAgentId || !detailTitleEl) return;
  try {
    const tools = await loadTools();
    const { agent } = await getAgentDetail(selectedAgentId);
    document.title = `${agent.title || agent.name} · Minder`;
    detailTitleEl.textContent = agent.title || agent.name;
    if (editNameEl) editNameEl.value = agent.name;
    if (editTitleEl) editTitleEl.value = agent.title;
    if (editDescEl) editDescEl.value = agent.description;
    if (editSystemPromptEl) editSystemPromptEl.value = agent.system_prompt;
    if (editWorkflowStepsEl) editWorkflowStepsEl.value = agent.workflow_steps.join(", ");
    if (editArtifactTypesEl) editArtifactTypesEl.value = agent.artifact_types.join(", ");
    if (editTagsEl) editTagsEl.value = agent.tags.join(", ");
    if (editIsDefaultEl) editIsDefaultEl.checked = agent.is_default;
    renderToolCheckboxes("edit-agent-tools", "edit_agent_tool", tools, agent.tools);
  } catch (error) {
    if (detailTitleEl) detailTitleEl.textContent = "Agent not found";
    setEditStatus(
      error instanceof Error ? error.message : "Unable to load agent.",
      "danger",
    );
  }
};

getEl("edit-agent-tools-all")?.addEventListener("click", () =>
  toggleAllTools("edit-agent-tools", "edit_agent_tool", true),
);
getEl("edit-agent-tools-none")?.addEventListener("click", () =>
  toggleAllTools("edit-agent-tools", "edit_agent_tool", false),
);

editAgentForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedAgentId) return;
  setEditStatus("Saving changes...");
  try {
    const result = await updateAgent(selectedAgentId, {
      name: editNameEl?.value.trim(),
      title: editTitleEl?.value.trim(),
      description: editDescEl?.value.trim(),
      system_prompt: editSystemPromptEl?.value.trim(),
      tools: getCheckedTools("edit-agent-tools", "edit_agent_tool"),
      workflow_steps: parseList(editWorkflowStepsEl?.value ?? ""),
      artifact_types: parseList(editArtifactTypesEl?.value ?? ""),
      tags: parseList(editTagsEl?.value ?? ""),
      is_default: editIsDefaultEl?.checked,
    });
    document.title = `${result.agent.title || result.agent.name} · Minder`;
    if (detailTitleEl) detailTitleEl.textContent = result.agent.title || result.agent.name;
    setEditStatus("Changes saved.", "success");
    showToast(`Saved ${result.agent.title || result.agent.name}.`, "success");
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to save changes.";
    setEditStatus(message, "danger");
    showToast(message, "danger");
  }
});

deleteAgentButton?.addEventListener("click", async () => {
  if (!selectedAgentId) return;
  const confirmed = await showDangerConfirm("Delete this agent? This cannot be undone.");
  if (!confirmed) return;
  if (deleteStatusEl) deleteStatusEl.textContent = "Deleting...";
  try {
    await deleteAgent(selectedAgentId);
    showToast("Agent deleted.", "success");
    window.location.href = "/dashboard/agents";
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to delete agent.";
    if (deleteStatusEl) deleteStatusEl.textContent = message;
    showToast(message, "danger");
  }
});

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

void refreshAgents();
void renderDetail();
