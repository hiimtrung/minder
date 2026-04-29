import {
  getSessionDetail,
  updateSession,
  deleteSession,
  type SessionPayload,
} from "../lib/api/admin";
import { showDangerConfirm } from "./modal-controller";
import { getEl, escapeHtml, showToast } from "./ui-utils";

const titleEl = getEl("detail-title");
const sessionIdVal = getEl("session-id-val");
const sessionNameVal = getEl("session-name-val");
const userIdVal = getEl("session-user-id");
const clientIdVal = getEl("session-client-id");
const createdAtVal = getEl("session-created-at");
const lastActiveVal = getEl("session-last-active");

const projectContextBody = getEl("project-context-body");
const stateReadView = getEl("state-read-view");
const activeSkillsBody = getEl("active-skills-body");

const deleteBtn = getEl("delete-session");
const refreshBtn = getEl("refresh-session");
const toggleStateEdit = getEl("toggle-state-edit");
const stateEditForm = getEl("state-edit-form") as HTMLFormElement | null;
const cancelStateEdit = getEl("cancel-state-edit");
const stateSaveStatus = getEl("state-save-status");

const stateTaskInput = getEl("state-task") as HTMLInputElement | null;
const stateNextStepsInput = getEl("state-next-steps") as HTMLTextAreaElement | null;
const stateBlockersInput = getEl("state-blockers") as HTMLTextAreaElement | null;
const stateExtraJsonInput = getEl("state-extra-json") as HTMLTextAreaElement | null;

const sessionId = window.location.pathname.split("/").filter(Boolean).pop() ?? "";

let currentSession: SessionPayload | null = null;

// ---------------------------------------------------------------------------
// Renderers
// ---------------------------------------------------------------------------

function emptyBadge(message: string): string {
  return `<p class="text-sm text-stone-400 italic">${escapeHtml(message)}</p>`;
}

function renderProjectContext(ctx: Record<string, any>): void {
  if (!projectContextBody) return;
  const keys = Object.keys(ctx);
  if (!keys.length) {
    projectContextBody.innerHTML = emptyBadge("No project context saved yet.");
    return;
  }

  const branch = ctx.branch as string | undefined;
  const openFiles = Array.isArray(ctx.open_files) ? (ctx.open_files as string[]) : [];
  const repoPath = ctx.repo_path as string | undefined;
  const rest = Object.fromEntries(
    Object.entries(ctx).filter(([k]) => !["branch", "open_files", "repo_path"].includes(k))
  );

  let html = `<dl class="space-y-4 text-sm">`;
  if (branch) {
    html += `<div>
      <dt class="font-medium text-stone-900">Branch</dt>
      <dd class="mt-1 font-mono text-stone-600">${escapeHtml(branch)}</dd>
    </div>`;
  }
  if (repoPath) {
    html += `<div>
      <dt class="font-medium text-stone-900">Repo Path</dt>
      <dd class="mt-1 font-mono text-stone-600 break-all">${escapeHtml(repoPath)}</dd>
    </div>`;
  }
  if (openFiles.length) {
    html += `<div>
      <dt class="font-medium text-stone-900">Open Files</dt>
      <dd class="mt-1">
        <ul class="space-y-1">
          ${openFiles.map(f => `<li class="font-mono text-xs text-stone-600 bg-stone-50 rounded-lg px-3 py-1.5">${escapeHtml(f)}</li>`).join("")}
        </ul>
      </dd>
    </div>`;
  }
  if (Object.keys(rest).length) {
    html += `<div>
      <dt class="font-medium text-stone-900">Other</dt>
      <dd class="mt-1"><pre class="rounded-xl bg-stone-50 p-3 text-xs text-stone-700 overflow-auto">${escapeHtml(JSON.stringify(rest, null, 2))}</pre></dd>
    </div>`;
  }
  html += `</dl>`;
  projectContextBody.innerHTML = html;
}

function renderState(state: Record<string, any>): void {
  if (!stateReadView) return;
  const keys = Object.keys(state);
  if (!keys.length) {
    stateReadView.innerHTML = emptyBadge("No state saved yet. Use the Edit button or call minder_session_save from the agent.");
    return;
  }

  const task = state.task ?? state.checkpoint ?? state.phase ?? null;
  const nextSteps = Array.isArray(state.next_steps) ? (state.next_steps as string[]) : [];
  const blockers = Array.isArray(state.blockers) ? (state.blockers as string[]) :
    (Array.isArray(state.blocked_by) ? (state.blocked_by as string[]) : []);
  const rest = Object.fromEntries(
    Object.entries(state).filter(([k]) => !["task", "checkpoint", "phase", "next_steps", "blockers", "blocked_by"].includes(k))
  );

  let html = `<dl class="space-y-4 text-sm">`;
  if (task) {
    html += `<div>
      <dt class="font-medium text-stone-900">Task / Phase</dt>
      <dd class="mt-1 text-stone-700">${escapeHtml(String(task))}</dd>
    </div>`;
  }
  if (nextSteps.length) {
    html += `<div>
      <dt class="font-medium text-stone-900">Next Steps</dt>
      <dd class="mt-1">
        <ul class="space-y-1 list-disc list-inside text-stone-600">
          ${nextSteps.map(s => `<li>${escapeHtml(String(s))}</li>`).join("")}
        </ul>
      </dd>
    </div>`;
  }
  if (blockers.length) {
    html += `<div>
      <dt class="font-medium text-stone-900">Blockers</dt>
      <dd class="mt-1">
        <ul class="space-y-1 list-disc list-inside text-red-700">
          ${blockers.map(b => `<li>${escapeHtml(String(b))}</li>`).join("")}
        </ul>
      </dd>
    </div>`;
  }
  if (Object.keys(rest).length) {
    html += `<div>
      <dt class="font-medium text-stone-900">Other</dt>
      <dd class="mt-1"><pre class="rounded-xl bg-stone-50 p-3 text-xs text-stone-700 overflow-auto">${escapeHtml(JSON.stringify(rest, null, 2))}</pre></dd>
    </div>`;
  }
  html += `</dl>`;
  stateReadView.innerHTML = html;
}

function renderActiveSkills(skills: Record<string, any>): void {
  if (!activeSkillsBody) return;
  const entries = Object.entries(skills);
  if (!entries.length) {
    activeSkillsBody.innerHTML = emptyBadge("No active skills saved yet. Skills are tracked when the agent calls minder_session_save with active_skills.");
    return;
  }
  activeSkillsBody.innerHTML = `<ul class="space-y-3">` +
    entries.map(([key, val]) => `
      <li class="rounded-xl bg-stone-50 p-4">
        <p class="text-xs font-semibold text-stone-900 font-mono">${escapeHtml(key)}</p>
        <pre class="mt-1 text-xs text-stone-600 overflow-auto whitespace-pre-wrap">${escapeHtml(typeof val === "string" ? val : JSON.stringify(val, null, 2))}</pre>
      </li>`).join("") +
    `</ul>`;
}

function populateEditForm(state: Record<string, any>): void {
  const task = state.task ?? state.checkpoint ?? state.phase ?? "";
  const nextSteps = Array.isArray(state.next_steps) ? (state.next_steps as string[]).join("\n") : "";
  const blockers = Array.isArray(state.blockers) ? (state.blockers as string[]).join("\n") :
    (Array.isArray(state.blocked_by) ? (state.blocked_by as string[]).join("\n") : "");
  const rest = Object.fromEntries(
    Object.entries(state).filter(([k]) => !["task", "checkpoint", "phase", "next_steps", "blockers", "blocked_by"].includes(k))
  );
  if (stateTaskInput) stateTaskInput.value = String(task);
  if (stateNextStepsInput) stateNextStepsInput.value = nextSteps;
  if (stateBlockersInput) stateBlockersInput.value = blockers;
  if (stateExtraJsonInput) stateExtraJsonInput.value = Object.keys(rest).length ? JSON.stringify(rest, null, 2) : "";
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

async function refreshDetail(): Promise<void> {
  if (!sessionId) return;
  try {
    const { session } = await getSessionDetail(sessionId);
    currentSession = session;

    if (titleEl) titleEl.textContent = session.name || session.id.slice(0, 8);
    if (sessionIdVal) sessionIdVal.textContent = session.id;
    if (sessionNameVal) sessionNameVal.textContent = session.name || "—";
    if (userIdVal) userIdVal.textContent = session.user_id || "—";
    if (clientIdVal) clientIdVal.textContent = session.client_id || "—";
    if (createdAtVal) createdAtVal.textContent = session.created_at ? new Date(session.created_at).toLocaleString() : "n/a";
    if (lastActiveVal) lastActiveVal.textContent = session.last_active ? new Date(session.last_active).toLocaleString() : "n/a";

    renderProjectContext(session.project_context ?? {});
    renderState(session.state ?? {});
    renderActiveSkills(session.active_skills ?? {});
  } catch (err) {
    console.error("Failed to load session detail:", err);
    if (titleEl) titleEl.textContent = "Error loading session";
    showToast(err instanceof Error ? err.message : "Failed to load session.", "danger");
  }
}

// ---------------------------------------------------------------------------
// Edit state form
// ---------------------------------------------------------------------------

toggleStateEdit?.addEventListener("click", () => {
  const isHidden = stateEditForm?.classList.contains("hidden");
  if (isHidden) {
    populateEditForm(currentSession?.state ?? {});
    stateEditForm?.classList.remove("hidden");
    stateReadView?.classList.add("hidden");
    if (toggleStateEdit instanceof HTMLButtonElement) toggleStateEdit.textContent = "Cancel";
  } else {
    stateEditForm?.classList.add("hidden");
    stateReadView?.classList.remove("hidden");
    if (toggleStateEdit instanceof HTMLButtonElement) toggleStateEdit.textContent = "Edit";
  }
});

cancelStateEdit?.addEventListener("click", () => {
  stateEditForm?.classList.add("hidden");
  stateReadView?.classList.remove("hidden");
  if (toggleStateEdit instanceof HTMLButtonElement) toggleStateEdit.textContent = "Edit";
});

stateEditForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!sessionId) return;

  const task = stateTaskInput?.value.trim() ?? "";
  const nextSteps = (stateNextStepsInput?.value ?? "").split("\n").map(s => s.trim()).filter(Boolean);
  const blockers = (stateBlockersInput?.value ?? "").split("\n").map(s => s.trim()).filter(Boolean);

  let extra: Record<string, any> = {};
  const extraRaw = stateExtraJsonInput?.value.trim();
  if (extraRaw && extraRaw !== "{}") {
    try {
      extra = JSON.parse(extraRaw) as Record<string, any>;
    } catch {
      if (stateSaveStatus) stateSaveStatus.textContent = "Invalid JSON in Additional Fields.";
      return;
    }
  }

  const newState: Record<string, any> = { ...extra };
  if (task) newState.task = task;
  if (nextSteps.length) newState.next_steps = nextSteps;
  if (blockers.length) newState.blockers = blockers;

  if (stateSaveStatus) stateSaveStatus.textContent = "Saving…";
  try {
    const { session } = await updateSession(sessionId, { state: newState });
    currentSession = session;
    renderState(session.state ?? {});
    stateEditForm?.classList.add("hidden");
    stateReadView?.classList.remove("hidden");
    if (toggleStateEdit instanceof HTMLButtonElement) toggleStateEdit.textContent = "Edit";
    if (stateSaveStatus) stateSaveStatus.textContent = "";
    showToast("Session state saved.", "success");
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to save state.";
    if (stateSaveStatus) stateSaveStatus.textContent = msg;
    showToast(msg, "danger");
  }
});

// ---------------------------------------------------------------------------
// Delete / refresh
// ---------------------------------------------------------------------------

deleteBtn?.addEventListener("click", async () => {
  const confirmed = await showDangerConfirm(
    "Are you sure you want to delete this session? This will clear all runtime memory associated with it."
  );
  if (confirmed && sessionId) {
    try {
      await deleteSession(sessionId);
      window.location.href = "/dashboard/sessions";
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to delete session.", "danger");
    }
  }
});

refreshBtn?.addEventListener("click", () => void refreshDetail());

void refreshDetail();
