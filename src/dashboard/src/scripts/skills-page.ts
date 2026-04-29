import {
  createAdminJob,
  createSkill,
  deleteSkill,
  eventStreamUrl,
  getAdminJob,
  listSkills,
  listAdminJobs,
  searchAdminCatalog,
  updateSkill,
  type AdminJobPayload,
  type AdminJobStreamEvent,
  type SkillImportSummaryPayload,
  type SkillPayload,
  type SkillSourcePayload,
} from "../lib/api/admin";
import {
  createDebouncedHandler,
  paginateItems,
  setPagerStatus,
  updatePagerButtons,
} from "./catalog-controls";
import { showDangerConfirm } from "./modal-controller";

const registryEl = document.querySelector("#skill-registry");
const formEl = document.querySelector("#skill-form") as HTMLFormElement | null;
const skillIdEl = document.querySelector(
  "#skill-id",
) as HTMLInputElement | null;
const titleEl = document.querySelector(
  "#skill-title",
) as HTMLInputElement | null;
const contentEl = document.querySelector(
  "#skill-content",
) as HTMLTextAreaElement | null;
const languageEl = document.querySelector(
  "#skill-language",
) as HTMLInputElement | null;
const tagsEl = document.querySelector("#skill-tags") as HTMLInputElement | null;
const workflowStepsEl = document.querySelector(
  "#skill-workflow-steps",
) as HTMLInputElement | null;
const artifactTypesEl = document.querySelector(
  "#skill-artifact-types",
) as HTMLInputElement | null;
const provenanceEl = document.querySelector(
  "#skill-provenance",
) as HTMLInputElement | null;
const qualityScoreEl = document.querySelector(
  "#skill-quality-score",
) as HTMLInputElement | null;
const excerptKindEl = document.querySelector(
  "#skill-excerpt-kind",
) as HTMLSelectElement | null;
const sourceSummaryEl = document.querySelector("#skill-source-summary");
const quickSearchEl = document.querySelector(
  "#skill-quick-search",
) as HTMLInputElement | null;
const paginationStatusEl = document.querySelector("#skill-pagination-status");
const pagePrevButton = document.querySelector("#skill-page-prev");
const pageNextButton = document.querySelector("#skill-page-next");
const quickSearchLoadingEl = document.querySelector(
  "#skill-quick-search-loading",
);
const statusEl = document.querySelector("#skill-editor-status");
const importFormEl = document.querySelector(
  "#skill-import-form",
) as HTMLFormElement | null;
const importModalEl = document.querySelector(
  "#skill-import-modal",
) as HTMLDialogElement | null;
const openImportModalButton = document.querySelector(
  "#skill-open-import-modal",
);
const closeImportModalButton = document.querySelector(
  "#skill-close-import-modal",
);
const importRepoUrlEl = document.querySelector(
  "#skill-import-repo-url",
) as HTMLInputElement | null;
const importPathEl = document.querySelector(
  "#skill-import-path",
) as HTMLInputElement | null;
const importRefEl = document.querySelector(
  "#skill-import-ref",
) as HTMLInputElement | null;
const importProviderEl = document.querySelector(
  "#skill-import-provider",
) as HTMLSelectElement | null;
const importExcerptKindEl = document.querySelector(
  "#skill-import-excerpt-kind",
) as HTMLSelectElement | null;
const importStatusEl = document.querySelector("#skill-import-status");
const importActiveJobEl = document.querySelector("#skill-import-active-job");
const importProgressLogEl = document.querySelector(
  "#skill-import-progress-log",
);
const importJobListEl = document.querySelector("#skill-import-job-list");
const importJobSummaryEl = document.querySelector("#skill-import-job-summary");
const toastRegion = document.querySelector("#dashboard-toast-region");

const PAGE_SIZE = 20;

type SkillExcerptKind = "none" | "reusable_excerpt";
type SkillImportProvider = "github" | "gitlab" | "generic_git";

let visibleSkills: SkillPayload[] = [];
let totalCount = 0;
let selectedSkillId: string | null = null;
let currentQuery = "";
let currentPage = 1;
let recentImportJobs: AdminJobPayload[] = [];
let activeImportJobId: string | null = null;
let importJobStream: EventSource | null = null;
const completedImportRefreshes = new Set<string>();

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

const setStatusLine = (
  target: Element | null,
  message: string,
  tone: "default" | "success" | "danger" = "default",
) => {
  if (!(target instanceof HTMLElement)) return;
  target.textContent = message;
  target.className = "u-status";
  if (tone === "success") target.classList.add("u-status-success");
  else if (tone === "danger") target.classList.add("u-status-danger");
};

const setStatus = (
  message: string,
  tone: "default" | "success" | "danger" = "default",
) => setStatusLine(statusEl, message, tone);

const setImportStatus = (
  message: string,
  tone: "default" | "success" | "danger" = "default",
) => setStatusLine(importStatusEl, message, tone);

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
  workflow_steps: splitCsv(workflowStepsEl?.value ?? ""),
  artifact_types: splitCsv(artifactTypesEl?.value ?? ""),
  provenance: provenanceEl?.value.trim() || null,
  quality_score: Number(qualityScoreEl?.value ?? "0") || 0,
  excerpt_kind: (excerptKindEl?.value === "reusable_excerpt"
    ? "reusable_excerpt"
    : "none") as SkillExcerptKind,
});

const currentImportDraft = () => ({
  repo_url: importRepoUrlEl?.value.trim() ?? "",
  path: importPathEl?.value.trim() || "skills",
  ref: importRefEl?.value.trim() || undefined,
  provider: (importProviderEl?.value === "github" ||
  importProviderEl?.value === "gitlab" ||
  importProviderEl?.value === "generic_git"
    ? importProviderEl.value
    : undefined) as SkillImportProvider | undefined,
  excerpt_kind: (importExcerptKindEl?.value === "reusable_excerpt"
    ? "reusable_excerpt"
    : "none") as SkillExcerptKind,
});

const summarizeSource = (source: SkillSourcePayload | null): string => {
  if (!source) return "";
  const location = source.file_path
    ? `${source.path}/${source.file_path}`
    : source.path;
  const ref = source.ref ? ` · ${source.ref}` : "";
  return `${source.provider} · ${location}${ref}`;
};

const updateSourceSummary = (skill?: SkillPayload) => {
  if (!(sourceSummaryEl instanceof HTMLElement)) return;
  if (!skill?.source) {
    sourceSummaryEl.innerHTML = "";
    sourceSummaryEl.classList.add("hidden");
    return;
  }

  sourceSummaryEl.innerHTML = `
    <p class="eyebrow">Imported source</p>
    <p class="mt-2 wrap-break-word text-sm font-medium text-stone-800">${escapeHtml(skill.source.repo_url)}</p>
    <p class="mt-1 text-sm text-stone-600">${escapeHtml(summarizeSource(skill.source))}</p>
  `;
  sourceSummaryEl.classList.remove("hidden");
};

const fillForm = (skill?: SkillPayload) => {
  selectedSkillId = skill?.id ?? null;
  if (skillIdEl) skillIdEl.value = skill?.id ?? "";
  if (titleEl) titleEl.value = skill?.title ?? "";
  if (contentEl) contentEl.value = skill?.content ?? "";
  if (languageEl) languageEl.value = skill?.language ?? "markdown";
  if (tagsEl) tagsEl.value = (skill?.tags ?? []).join(", ");
  if (workflowStepsEl) {
    workflowStepsEl.value = (skill?.workflow_step_tags ?? []).join(", ");
  }
  if (artifactTypesEl) {
    artifactTypesEl.value = (skill?.artifact_type_tags ?? []).join(", ");
  }
  if (provenanceEl) provenanceEl.value = skill?.provenance ?? "";
  if (qualityScoreEl) {
    qualityScoreEl.value = String(skill?.quality_score ?? 0.7);
  }
  if (excerptKindEl) {
    excerptKindEl.value = skill?.excerpt_kind ?? "none";
  }
  updateSourceSummary(skill);
  setStatus("");
};

const selectSkillById = (skillId: string | null) => {
  if (!skillId) return;
  const skill = visibleSkills.find((item) => item.id === skillId);
  if (!skill) return;
  fillForm(skill);
};

const importSummaryMessage = (summary: SkillImportSummaryPayload): string => {
  const created = `${summary.created_count} new`;
  const updated = `${summary.updated_count} updated`;
  return `Imported ${summary.imported_count} skills (${created}, ${updated}).`;
};

const isRunningJob = (job: AdminJobPayload): boolean =>
  job.status === "queued" || job.status === "running";

const sortJobs = (jobs: AdminJobPayload[]): AdminJobPayload[] =>
  [...jobs].sort((left, right) => {
    const leftTime = new Date(left.created_at ?? 0).getTime();
    const rightTime = new Date(right.created_at ?? 0).getTime();
    return rightTime - leftTime;
  });

const jobStatusTone = (status: string): string => {
  if (status === "completed")
    return "border-emerald-200 bg-emerald-50 text-emerald-800";
  if (status === "failed") return "border-red-200 bg-red-50 text-red-800";
  if (status === "running")
    return "border-amber-200 bg-amber-50 text-amber-800";
  return "border-stone-200 bg-stone-100 text-stone-700";
};

const summarizeJob = (job: AdminJobPayload): string => {
  if (job.status === "completed" && job.result_payload) {
    const summary = job.result_payload as unknown as SkillImportSummaryPayload;
    return importSummaryMessage(summary);
  }
  return job.message || job.error_message || job.title;
};

const renderImportSummaryBanner = () => {
  if (!(importJobSummaryEl instanceof HTMLElement)) return;
  const runningJobs = recentImportJobs.filter(isRunningJob);
  if (!runningJobs.length) {
    importJobSummaryEl.classList.add("hidden");
    importJobSummaryEl.innerHTML = "";
    return;
  }
  const latest = runningJobs[0];
  importJobSummaryEl.innerHTML = `<p class="font-medium">${runningJobs.length} import job${runningJobs.length === 1 ? " is" : "s are"} running in the background.</p><p class="mt-1 wrap-break-word text-amber-900/80">${escapeHtml(summarizeJob(latest))}</p>`;
  importJobSummaryEl.classList.remove("hidden");
};

const renderProgressLog = (job: AdminJobPayload | null) => {
  if (!(importProgressLogEl instanceof HTMLElement)) return;
  if (!job?.events?.length) {
    importProgressLogEl.classList.add("hidden");
    importProgressLogEl.innerHTML = "";
    return;
  }
  importProgressLogEl.innerHTML = job.events
    .slice()
    .reverse()
    .map(
      (event) =>
        `<div class="border-b border-stone-800 py-2 last:border-b-0"><div class="flex items-center justify-between gap-3"><span class="wrap-break-word font-medium text-stone-100">${escapeHtml(event.message)}</span><span class="text-[11px] uppercase tracking-[0.18em] text-stone-400">${escapeHtml(event.status)}</span></div><div class="mt-1 wrap-break-word text-stone-400">${escapeHtml(event.created_at ?? "")}${typeof event.progress_current === "number" && typeof event.progress_total === "number" && event.progress_total > 0 ? ` · ${event.progress_current}/${event.progress_total}` : ""}</div></div>`,
    )
    .join("");
  importProgressLogEl.classList.remove("hidden");
};

const renderActiveImportJob = (job: AdminJobPayload | null) => {
  if (!(importActiveJobEl instanceof HTMLElement)) return;
  if (!job) {
    importActiveJobEl.classList.add("hidden");
    importActiveJobEl.innerHTML = "";
    renderProgressLog(null);
    return;
  }
  const percent = Math.max(0, Math.min(100, Number(job.progress_percent || 0)));
  importActiveJobEl.innerHTML = `
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0 flex-1">
        <p class="eyebrow">Tracked job</p>
        <h3 class="mt-2 wrap-break-word text-lg font-semibold tracking-tight text-stone-950">${escapeHtml(job.title)}</h3>
        <p class="mt-2 wrap-break-word text-sm leading-6 text-stone-600">${escapeHtml(summarizeJob(job))}</p>
      </div>
      <span class="rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] ${jobStatusTone(job.status)}">${escapeHtml(job.status)}</span>
    </div>
    <div class="mt-4 h-2 overflow-hidden rounded-full bg-stone-200">
      <div class="h-full rounded-full bg-amber-600 transition-[width] duration-300" style="width:${percent}%"></div>
    </div>
    <div class="mt-2 flex flex-wrap items-center justify-between gap-3 text-xs text-stone-500">
      <span>${job.progress_total > 0 ? `${job.progress_current}/${job.progress_total}` : "waiting for progress"}</span>
      <span>${escapeHtml(job.updated_at ?? "")}</span>
    </div>
  `;
  importActiveJobEl.classList.remove("hidden");
  renderProgressLog(job);
};

const renderImportJobList = () => {
  if (!(importJobListEl instanceof HTMLElement)) return;
  if (!recentImportJobs.length) {
    importJobListEl.innerHTML =
      '<div class="rounded-2xl border border-stone-800 bg-stone-900/70 px-4 py-3 text-sm text-stone-400">No import jobs yet.</div>';
    return;
  }
  importJobListEl.innerHTML = recentImportJobs
    .slice(0, 8)
    .map(
      (job) => `
        <button
          type="button"
          class="overflow-hidden rounded-2xl border border-stone-800 bg-stone-900/70 px-4 py-3 text-left transition hover:border-stone-600 hover:bg-stone-900"
          data-import-job-id="${escapeHtml(job.id)}"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0 flex-1">
              <p class="wrap-break-word text-sm font-medium text-stone-100">${escapeHtml(job.title)}</p>
              <p class="mt-1 wrap-break-word text-xs leading-5 text-stone-400">${escapeHtml(summarizeJob(job))}</p>
            </div>
            <span class="rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] ${jobStatusTone(job.status)}">${escapeHtml(job.status)}</span>
          </div>
        </button>
      `,
    )
    .join("");
  importJobListEl
    .querySelectorAll<HTMLButtonElement>("[data-import-job-id]")
    .forEach((button) => {
      button.addEventListener("click", () => {
        const jobId = button.dataset.importJobId;
        if (!jobId) return;
        void activateImportJob(jobId);
      });
    });
};

const upsertImportJob = (job: AdminJobPayload) => {
  const nextJobs = sortJobs([
    job,
    ...recentImportJobs.filter((item) => item.id !== job.id),
  ]);
  recentImportJobs = nextJobs;
  renderImportSummaryBanner();
  renderImportJobList();
  if (activeImportJobId === job.id) {
    renderActiveImportJob(job);
  }
  if (
    job.status === "completed" &&
    job.result_payload &&
    !completedImportRefreshes.has(job.id)
  ) {
    completedImportRefreshes.add(job.id);
    const summary = job.result_payload as unknown as SkillImportSummaryPayload;
    setImportStatus(importSummaryMessage(summary), "success");
    showToast(importSummaryMessage(summary), "success");
    void syncVisibleSkills();
    if (summary.imported[0]?.id) {
      // Note: we might need to search for it if it's not on the current page
      selectSkillById(summary.imported[0].id);
    }
  }
  if (job.status === "failed") {
    setImportStatus(
      job.error_message || job.message || "Import job failed.",
      "danger",
    );
    showToast(
      job.error_message || job.message || "Import job failed.",
      "danger",
    );
  }
};

const stopImportJobStream = () => {
  importJobStream?.close();
  importJobStream = null;
};

const trackImportJob = (jobId: string) => {
  stopImportJobStream();
  activeImportJobId = jobId;
  const stream = new EventSource(
    eventStreamUrl(`/api/v1/jobs/${jobId}/stream`),
    { withCredentials: true },
  );
  importJobStream = stream;
  stream.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data) as AdminJobStreamEvent;
      if (payload.type === "job") {
        upsertImportJob(payload.payload);
        if (!isRunningJob(payload.payload)) {
          stopImportJobStream();
        }
      }
    } catch {
      // Ignore malformed stream payloads.
    }
  };
  stream.onerror = () => {
    if (!importJobStream) return;
    stopImportJobStream();
  };
};

const activateImportJob = async (jobId: string) => {
  activeImportJobId = jobId;
  const existing = recentImportJobs.find((job) => job.id === jobId) ?? null;
  const job = existing ?? (await getAdminJob(jobId));
  upsertImportJob(job);
  renderActiveImportJob(job);
  if (isRunningJob(job)) {
    trackImportJob(job.id);
  } else {
    stopImportJobStream();
  }
};

const refreshImportJobs = async () => {
  const payload = await listAdminJobs({
    job_type: "skill_import_git",
    limit: 12,
  });
  recentImportJobs = sortJobs(payload.jobs);
  renderImportSummaryBanner();
  renderImportJobList();
  const trackedJob =
    recentImportJobs.find((job) => job.id === activeImportJobId) ??
    recentImportJobs.find(isRunningJob) ??
    recentImportJobs[0] ??
    null;
  if (trackedJob) {
    await activateImportJob(trackedJob.id);
    return;
  }
  renderActiveImportJob(null);
};

const openImportModal = async () => {
  if (importModalEl && !importModalEl.open) {
    importModalEl.showModal();
  }
  await refreshImportJobs();
};

const closeImportModal = () => {
  importModalEl?.close();
};

const renderRegistry = () => {
  if (!(registryEl instanceof HTMLElement)) return;

  const pageCount = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
  const start = totalCount === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1;
  const end = Math.min(currentPage * PAGE_SIZE, totalCount);

  setPagerStatus(paginationStatusEl, {
    slice: {
      items: visibleSkills,
      page: currentPage,
      pageCount,
      total: totalCount,
      start,
      end,
    },
    label: "skills",
    query: currentQuery,
  });
  updatePagerButtons(pagePrevButton, pageNextButton, currentPage, pageCount);

  if (!visibleSkills.length) {
    registryEl.innerHTML = `
      <article class="shell-card p-6 text-sm text-stone-600">
        ${currentQuery ? `No skills matched \"${escapeHtml(currentQuery)}\".` : "No skills yet. Ingest the first skill from the editor."}
      </article>
    `;
    return;
  }

  registryEl.innerHTML = visibleSkills
    .map((skill) => {
      const activeClass =
        skill.id === selectedSkillId
          ? "border-amber-400 bg-amber-50/70"
          : "border-stone-200 bg-white";
      return `
        <article class="shell-card border ${activeClass} p-5">
          <div class="flex items-start justify-between gap-3">
            <button
              type="button"
              class="min-w-0 flex-1 text-left"
              data-skill-select="${escapeHtml(skill.id)}"
            >
              <p class="eyebrow">${escapeHtml(skill.language)}</p>
              <h2 class="mt-2 wrap-break-word text-xl font-semibold tracking-tight text-stone-950">
                ${escapeHtml(skill.title)}
              </h2>
              <div class="mt-2 flex flex-wrap gap-2">
                <span class="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.18em] text-emerald-800">q ${escapeHtml(skill.quality_score.toFixed(1))}</span>
                ${skill.provenance ? `<span class="rounded-full border border-stone-200 bg-stone-50 px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.18em] text-stone-600">${escapeHtml(skill.provenance)}</span>` : ""}
                ${skill.excerpt_kind === "reusable_excerpt" ? `<span class="rounded-full border border-violet-200 bg-violet-50 px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.18em] text-violet-700">excerpt</span>` : ""}
                ${skill.source ? `<span class="rounded-full border border-sky-200 bg-sky-50 px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.18em] text-sky-700">${escapeHtml(skill.source.provider)}</span>` : ""}
              </div>
              <p class="mt-3 line-clamp-3 text-sm leading-6 text-stone-600">
                ${escapeHtml(skill.content)}
              </p>
              ${skill.source ? `<p class="mt-3 wrap-break-word text-xs text-stone-500">${escapeHtml(summarizeSource(skill.source))}</p>` : ""}
              <div class="mt-4 flex flex-wrap gap-2">
                ${(skill.workflow_step_tags ?? []).map((tag) => `<span class="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-[11px] text-amber-700">${escapeHtml(tag)}</span>`).join("")}
                ${(skill.artifact_type_tags ?? []).map((tag) => `<span class="rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-[11px] text-blue-700">${escapeHtml(tag)}</span>`).join("")}
              </div>
            </button>
            <button
              type="button"
              class="rounded-xl border border-red-200 px-3 py-1.5 text-xs text-red-700 transition hover:bg-red-50"
              data-skill-delete="${escapeHtml(skill.id)}"
            >
              Delete
            </button>
          </div>
        </article>
      `;
    })
    .join("");

  registryEl
    .querySelectorAll<HTMLButtonElement>("[data-skill-select]")
    .forEach((button) => {
      button.addEventListener("click", () => {
        const skill = visibleSkills.find(
          (item) => item.id === button.dataset.skillSelect,
        );
        if (!skill) return;
        fillForm(skill);
        renderRegistry();
      });
    });

  registryEl
    .querySelectorAll<HTMLButtonElement>("[data-skill-delete]")
    .forEach((button) => {
      button.addEventListener("click", async () => {
        const skillId = button.dataset.skillDelete;
        const skill = visibleSkills.find((item) => item.id === skillId);
        if (!skillId || !skill) return;
        if (!(await showDangerConfirm(`Delete skill ${skill.title}?`))) return;
        try {
          await deleteSkill(skillId);
          if (selectedSkillId === skillId) fillForm();
          await syncVisibleSkills();
          showToast(`Deleted ${skill.title}.`, "success");
        } catch (error) {
          showToast(
            error instanceof Error ? error.message : "Unable to delete skill.",
            "danger",
          );
        }
      });
    });
};

const syncVisibleSkills = async () => {
  if (registryEl instanceof HTMLElement) {
    registryEl.innerHTML = `<article class="shell-card p-6 text-sm text-stone-600">Loading skills...</article>`;
  }
  try {
    const result = await searchAdminCatalog<SkillPayload>(
      "skills",
      currentQuery,
      PAGE_SIZE,
      (currentPage - 1) * PAGE_SIZE,
    );
    visibleSkills = result.items;
    totalCount = result.total;
    renderRegistry();
  } catch (error) {
    if (registryEl instanceof HTMLElement) {
      registryEl.innerHTML = `<article class="shell-card p-6 text-sm text-red-700">${escapeHtml(error instanceof Error ? error.message : "Unable to load skills.")}</article>`;
    }
  }
};

document
  .querySelector("#skill-refresh-button")
  ?.addEventListener("click", () => {
    void syncVisibleSkills();
  });

document.querySelector("#skill-reset-button")?.addEventListener("click", () => {
  fillForm();
  renderRegistry();
});

pagePrevButton?.addEventListener("click", () => {
  currentPage = Math.max(1, currentPage - 1);
  void syncVisibleSkills();
});

pageNextButton?.addEventListener("click", () => {
  currentPage += 1;
  void syncVisibleSkills();
});

const debouncedSearch = createDebouncedHandler(async () => {
  currentQuery = quickSearchEl?.value.trim() ?? "";
  currentPage = 1;
  await syncVisibleSkills();
  quickSearchLoadingEl?.classList.add("hidden");
});

quickSearchEl?.addEventListener("input", () => {
  quickSearchLoadingEl?.classList.remove("hidden");
  debouncedSearch();
});

formEl?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const draft = currentDraft();
  const currentSkillId = skillIdEl?.value.trim() ?? "";
  const isUpdate = Boolean(currentSkillId);
  if (!draft.title.trim()) {
    setStatus("Title is required.", "danger");
    return;
  }
  if (!draft.content.trim()) {
    setStatus("Skill content is required.", "danger");
    return;
  }
  setStatus(isUpdate ? "Saving skill changes..." : "Ingesting skill...");
  try {
    const saved = isUpdate
      ? await updateSkill(currentSkillId, draft)
      : await createSkill(draft);
    await syncVisibleSkills();
    selectSkillById(saved.id);
    showToast(
      `${isUpdate ? "Saved" : "Ingested"} skill ${saved.title}.`,
      "success",
    );
    setStatus("Skill saved.", "success");
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unable to save skill.";
    setStatus(message, "danger");
    showToast(message, "danger");
  }
});

importFormEl?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const draft = currentImportDraft();
  if (!draft.repo_url) {
    setImportStatus("Repository URL is required.", "danger");
    return;
  }

  setImportStatus("Queueing import job...");
  try {
    const job = await createAdminJob({
      job_type: "skill_import_git",
      payload: draft,
    });
    upsertImportJob(job);
    await activateImportJob(job.id);
    setImportStatus("Import job queued. Progress will stream live.", "success");
    showToast("Import job queued.", "success");
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unable to import skill pack.";
    setImportStatus(message, "danger");
    showToast(message, "danger");
  }
});

openImportModalButton?.addEventListener("click", () => {
  void openImportModal();
});

closeImportModalButton?.addEventListener("click", () => {
  closeImportModal();
});

importModalEl?.addEventListener("close", () => {
  stopImportJobStream();
});

fillForm();
setImportStatus("");
void syncVisibleSkills();
void refreshImportJobs();
