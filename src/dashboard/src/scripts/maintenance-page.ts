import {
  getMaintenanceStatus,
  getMaintenanceRuns,
  triggerMaintenanceJob,
  updateMaintenanceJobConfig,
  updateMaintenanceGlobalConfig,
  type MaintenanceJobPayload,
  type MaintenanceRunPayload,
  type MaintenanceStatusPayload,
} from "../lib/api/admin";
import { escapeHtml, showToast } from "./ui-utils";

// Elements
const refreshBtn = document.querySelector("#maint-refresh-button");
const jobsContainer = document.querySelector("#maint-jobs-container");
const runsTbody = document.querySelector("#maint-runs-tbody");

// Pager
const pagerPrevBtn = document.querySelector("#maint-logs-prev") as HTMLButtonElement | null;
const pagerNextBtn = document.querySelector("#maint-logs-next") as HTMLButtonElement | null;
const pagerStatusEl = document.querySelector("#maint-logs-pager-status");

// Badges
const taskBadge = document.querySelector("#scheduler-task-badge");
const modeBadge = document.querySelector("#scheduler-mode-badge");
const idleBadge = document.querySelector("#scheduler-idle-badge");
const lastActiveEl = document.querySelector("#scheduler-last-active");
const activeQueriesEl = document.querySelector("#scheduler-active-queries");

// Forms
const globalForm = document.querySelector("#global-config-form") as HTMLFormElement | null;
const globalEnabledSelect = document.querySelector("#global-enabled") as HTMLSelectElement | null;
const globalModeSelect = document.querySelector("#global-mode") as HTMLSelectElement | null;
const globalIdleInput = document.querySelector("#global-idle-threshold") as HTMLInputElement | null;
const globalAutoActiveInput = document.querySelector("#global-auto-active-hours") as HTMLInputElement | null;
const globalStatusEl = document.querySelector("#global-config-status");

const jobDialog = document.querySelector("#job-config-dialog") as HTMLDialogElement | null;
const jobForm = document.querySelector("#job-config-form") as HTMLFormElement | null;
const jobCloseBtn = document.querySelector("#job-close-dialog");
const jobNameHidden = document.querySelector("#job-name-hidden") as HTMLInputElement | null;
const jobScheduleInput = document.querySelector("#job-schedule") as HTMLInputElement | null;
const jobEnabledSelect = document.querySelector("#job-enabled") as HTMLSelectElement | null;
const jobRequireIdleSelect = document.querySelector("#job-require-idle") as HTMLSelectElement | null;
const jobMaxRuntimeInput = document.querySelector("#job-max-runtime") as HTMLInputElement | null;
const jobStatusEl = document.querySelector("#job-config-status");

// State
let currentPage = 1;
const LOGS_PAGE_SIZE = 15;
let currentJobs: MaintenanceJobPayload[] = [];

// Helper: Format Dates
function formatDate(isoStr: string | null): string {
  if (!isoStr) return "Never";
  try {
    const d = new Date(isoStr);
    return d.toLocaleString();
  } catch {
    return isoStr;
  }
}

// Helper: Format Duration
function formatDuration(s: number): string {
  if (s < 0.1) return "0s";
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}m ${rem.toFixed(0)}s`;
}

// Render Status and Badges
function renderSchedulerStatus(status: MaintenanceStatusPayload) {
  // Task state
  if (taskBadge) {
    taskBadge.textContent = status.enabled ? "Active" : "Disabled";
    taskBadge.className = status.enabled
      ? "rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider border border-emerald-200 bg-emerald-50 text-emerald-800"
      : "rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider border border-stone-200 bg-stone-100 text-stone-600";
  }

  // Active Mode
  if (modeBadge) {
    const isPromoted = status.mode !== status.configured_mode;
    modeBadge.textContent = status.mode + (isPromoted ? " (auto)" : "");
    modeBadge.className = status.mode === "active"
      ? "rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider border border-violet-200 bg-violet-50 text-violet-800"
      : "rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider border border-stone-200 bg-stone-100 text-stone-600";
  }

  // Idle State
  if (idleBadge) {
    idleBadge.textContent = status.is_idle ? "Idle" : "Active";
    idleBadge.className = status.is_idle
      ? "rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider border border-sky-200 bg-sky-50 text-sky-800"
      : "rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider border border-amber-200 bg-amber-50 text-amber-800";
  }

  if (lastActiveEl) lastActiveEl.textContent = formatDate(status.last_activity_time);
  if (activeQueriesEl) activeQueriesEl.textContent = String(status.active_session_count);

  // Set form values if form is pristine
  if (globalEnabledSelect && !globalForm?.classList.contains("is-dirty")) {
    globalEnabledSelect.value = String(status.enabled);
  }
  if (globalModeSelect && !globalForm?.classList.contains("is-dirty")) {
    globalModeSelect.value = status.configured_mode;
  }
  if (globalIdleInput && !globalForm?.classList.contains("is-dirty")) {
    globalIdleInput.value = String(status.idle_threshold_seconds);
  }
  if (globalAutoActiveInput && !globalForm?.classList.contains("is-dirty")) {
    globalAutoActiveInput.value = String(status.auto_active_after_idle_hours);
  }
}

// Render Job Cards
function renderJobs(jobs: MaintenanceJobPayload[]) {
  currentJobs = jobs;
  if (!jobsContainer) return;

  if (!jobs.length) {
    jobsContainer.innerHTML = '<div class="col-span-full py-6 text-center text-stone-500">No jobs registered in system database.</div>';
    return;
  }

  jobsContainer.innerHTML = jobs
    .map((job) => {
      let statusClass = "border-stone-200 bg-white";
      let badgeClass = "border-stone-200 bg-stone-50 text-stone-600";
      
      if (!job.enabled) {
        statusClass = "border-stone-100 bg-stone-50/50 opacity-60";
        badgeClass = "border-stone-200 bg-stone-100 text-stone-400";
      } else if (job.last_status === "running") {
        statusClass = "border-amber-400 bg-amber-50/20";
        badgeClass = "border-amber-200 bg-amber-50 text-amber-800 animate-pulse";
      } else if (job.last_status === "success") {
        statusClass = "border-stone-200 bg-white";
        badgeClass = "border-emerald-200 bg-emerald-50 text-emerald-800";
      } else if (job.last_status === "failed") {
        statusClass = "border-red-200 bg-red-50/10";
        badgeClass = "border-red-200 bg-red-50 text-red-800";
      }

      const statusText = !job.enabled
        ? "Disabled"
        : (job.last_status ? job.last_status : "Idle");

      return `
        <article class="shell-card border ${statusClass} p-5 flex flex-col justify-between">
          <div>
            <div class="flex items-start justify-between gap-3 mb-2.5">
              <div>
                <h3 class="font-semibold text-stone-900 leading-snug">${escapeHtml(job.name)}</h3>
                <code class="text-xs text-amber-700 bg-amber-50/50 border border-amber-100 px-1.5 py-0.5 rounded mt-1 inline-block">${escapeHtml(job.schedule)}</code>
              </div>
              <span class="rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${badgeClass}">
                ${statusText}
              </span>
            </div>
            
            <div class="text-xs text-stone-500 flex flex-col gap-1 mb-4">
              <div class="flex justify-between">
                <span>Requires Idle:</span>
                <span class="font-medium text-stone-700">${job.require_idle ? "Yes" : "No"}</span>
              </div>
              <div class="flex justify-between">
                <span>Max runtime:</span>
                <span class="font-medium text-stone-700">${job.max_runtime_s}s</span>
              </div>
              <div class="flex justify-between">
                <span>Last executed:</span>
                <span class="font-medium text-stone-700">${formatDate(job.last_run_at)}</span>
              </div>
              ${job.last_summary ? `
                <div class="mt-2 pt-2 border-t border-stone-100 text-stone-600 italic line-clamp-2" title="${escapeHtml(job.last_summary)}">
                  "${escapeHtml(job.last_summary)}"
                </div>
              ` : ""}
            </div>
          </div>

          <div class="flex gap-2 pt-3 border-t border-stone-100">
            <button
              type="button"
              class="flex-1 rounded-xl border border-stone-200 bg-stone-50 px-2.5 py-1.5 text-xs font-semibold text-stone-700 hover:bg-stone-100 transition"
              data-maint-configure="${escapeHtml(job.name)}"
            >
              Configure
            </button>
            <button
              type="button"
              class="flex-1 rounded-xl border border-stone-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-stone-800 hover:bg-stone-50 transition active:scale-95"
              data-maint-trigger="${escapeHtml(job.name)}"
              ${job.last_status === "running" ? "disabled" : ""}
            >
              Trigger Now
            </button>
          </div>
        </article>
      `;
    })
    .join("");

  // Bind configure buttons
  jobsContainer.querySelectorAll("[data-maint-configure]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const name = (btn as HTMLElement).dataset.maintConfigure;
      if (name) openJobConfig(name);
    });
  });

  // Bind trigger buttons
  jobsContainer.querySelectorAll("[data-maint-trigger]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const name = (btn as HTMLElement).dataset.maintTrigger;
      if (name) void triggerJob(name);
    });
  });
}

// Render Runs Logs
function renderRuns(runs: MaintenanceRunPayload[]) {
  if (!runsTbody) return;

  if (!runs.length) {
    runsTbody.innerHTML = `
      <tr>
        <td colspan="6" class="py-6 text-center text-stone-400">No maintenance execution runs logged yet.</td>
      </tr>
    `;
    return;
  }

  runsTbody.innerHTML = runs
    .map((run) => {
      let statusBadge = "border-stone-200 bg-stone-50 text-stone-600";
      if (run.status === "success") {
        statusBadge = "border-emerald-200 bg-emerald-50 text-emerald-800";
      } else if (run.status === "failed") {
        statusBadge = "border-red-200 bg-red-50 text-red-800";
      } else if (run.status === "running") {
        statusBadge = "border-amber-200 bg-amber-50 text-amber-800 animate-pulse";
      }

      const summaryText = run.status === "failed"
        ? (run.error_message || "Unknown execution error")
        : (run.summary || "Completed successfully.");

      return `
        <tr class="border-b border-stone-100 hover:bg-stone-50/40 text-stone-700">
          <td class="py-3 px-3 font-semibold text-stone-900">${escapeHtml(run.job_name)}</td>
          <td class="py-3 px-3 text-xs text-stone-500">${formatDate(run.started_at)}</td>
          <td class="py-3 px-3 text-xs text-stone-600">${formatDuration(run.duration_s)}</td>
          <td class="py-3 px-3 text-xs uppercase text-stone-500 tracking-wider">${escapeHtml(run.mode)}</td>
          <td class="py-3 px-3">
            <span class="rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${statusBadge}">
              ${escapeHtml(run.status)}
            </span>
          </td>
          <td class="py-3 px-3 text-xs text-stone-600 font-serif max-w-[280px] truncate" title="${escapeHtml(summaryText)}">
            ${escapeHtml(summaryText)}
          </td>
        </tr>
      `;
    })
    .join("");
}

// Refresh logic
async function refreshAll() {
  try {
    const status = await getMaintenanceStatus();
    renderSchedulerStatus(status);
    renderJobs(status.jobs);

    const runs = await getMaintenanceRuns(LOGS_PAGE_SIZE, (currentPage - 1) * LOGS_PAGE_SIZE);
    renderRuns(runs);

    // Update logs pager
    if (pagerStatusEl) {
      pagerStatusEl.textContent = `Page ${currentPage}`;
    }
    if (pagerPrevBtn) {
      pagerPrevBtn.disabled = currentPage === 1;
    }
    if (pagerNextBtn) {
      // Simple lookahead: enable next if we got a full page
      pagerNextBtn.disabled = runs.length < LOGS_PAGE_SIZE;
    }
  } catch (error) {
    console.error("Failed to load maintenance configuration:", error);
    showToast("Error loading maintenance information", "danger");
  }
}

// Trigger maintenance job
async function triggerJob(jobName: string) {
  try {
    showToast(`Triggering maintenance job '${jobName}'...`);
    const res = await triggerMaintenanceJob(jobName);
    showToast(res.message, "success");
    await refreshAll();
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Failed to trigger job", "danger");
  }
}

// Open Job Configuration dialog
function openJobConfig(jobName: string) {
  const job = currentJobs.find((j) => j.name === jobName);
  if (!job) return;

  if (jobNameHidden) jobNameHidden.value = jobName;
  if (jobScheduleInput) jobScheduleInput.value = job.schedule;
  if (jobEnabledSelect) jobEnabledSelect.value = String(job.enabled);
  if (jobRequireIdleSelect) jobRequireIdleSelect.value = String(job.require_idle);
  if (jobMaxRuntimeInput) jobMaxRuntimeInput.value = String(job.max_runtime_s);

  const titleEl = document.querySelector("#job-dialog-title");
  if (titleEl) titleEl.textContent = `Settings for ${jobName}`;

  if (jobStatusEl) {
    jobStatusEl.textContent = "";
    jobStatusEl.className = "u-status";
  }

  jobDialog?.showModal();
}

// Close dialog
function closeJobConfig() {
  jobDialog?.close();
}

// Event Listeners
refreshBtn?.addEventListener("click", () => {
  void refreshAll();
});

// Mark form dirty when users modify values so polling doesn't overwrite input fields
globalForm?.addEventListener("input", () => {
  globalForm.classList.add("is-dirty");
});

globalForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!globalEnabledSelect || !globalModeSelect || !globalIdleInput || !globalAutoActiveInput) return;

  if (globalStatusEl) {
    globalStatusEl.textContent = "Updating global settings...";
    globalStatusEl.className = "u-status";
  }

  try {
    const payload = {
      enabled: globalEnabledSelect.value === "true",
      mode: globalModeSelect.value as "report" | "active",
      idle_threshold_seconds: parseInt(globalIdleInput.value),
      auto_active_after_idle_hours: parseFloat(globalAutoActiveInput.value),
    };

    await updateMaintenanceGlobalConfig(payload);
    globalForm.classList.remove("is-dirty");

    if (globalStatusEl) {
      globalStatusEl.textContent = "Configuration updated successfully.";
      globalStatusEl.className = "u-status u-status-success";
    }
    showToast("Global configuration saved", "success");
    await refreshAll();
  } catch (error) {
    const msg = error instanceof Error ? error.message : "Failed to update config";
    if (globalStatusEl) {
      globalStatusEl.textContent = msg;
      globalStatusEl.className = "u-status u-status-danger";
    }
    showToast(msg, "danger");
  }
});

jobForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const jobName = jobNameHidden?.value;
  if (!jobName || !jobScheduleInput || !jobEnabledSelect || !jobRequireIdleSelect || !jobMaxRuntimeInput) return;

  if (jobStatusEl) {
    jobStatusEl.textContent = "Saving job settings...";
    jobStatusEl.className = "u-status";
  }

  try {
    const payload = {
      schedule: jobScheduleInput.value.trim(),
      enabled: jobEnabledSelect.value === "true",
      require_idle: jobRequireIdleSelect.value === "true",
      max_runtime_s: parseInt(jobMaxRuntimeInput.value),
    };

    await updateMaintenanceJobConfig(jobName, payload);
    if (jobStatusEl) {
      jobStatusEl.textContent = "Job settings saved.";
      jobStatusEl.className = "u-status u-status-success";
    }
    showToast(`Job '${jobName}' settings saved`, "success");
    jobDialog?.close();
    await refreshAll();
  } catch (error) {
    const msg = error instanceof Error ? error.message : "Failed to update job settings";
    if (jobStatusEl) {
      jobStatusEl.textContent = msg;
      jobStatusEl.className = "u-status u-status-danger";
    }
    showToast(msg, "danger");
  }
});

// Modal close binds
jobCloseBtn?.addEventListener("click", closeJobConfig);
jobDialog?.addEventListener("click", (e) => {
  if (e.target === jobDialog) closeJobConfig();
});

// Logs pager binds
pagerPrevBtn?.addEventListener("click", () => {
  if (currentPage > 1) {
    currentPage--;
    void refreshAll();
  }
});

pagerNextBtn?.addEventListener("click", () => {
  currentPage++;
  void refreshAll();
});

// Initial load & Polling
void refreshAll();
const pollInterval = window.setInterval(() => {
  // Only refresh status and job cards if dialog is not open to avoid confusing user
  if (!jobDialog?.open) {
    void refreshAll();
  }
}, 8000);

// Cleanup on page transitions / unloads
document.addEventListener("astro:before-swap", () => {
  window.clearInterval(pollInterval);
});
window.addEventListener("beforeunload", () => {
  window.clearInterval(pollInterval);
});
