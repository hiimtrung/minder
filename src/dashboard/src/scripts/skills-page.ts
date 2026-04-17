import {
  createSkill,
  deleteSkill,
  listSkills,
  updateSkill,
  type SkillPayload,
} from "../lib/api/admin";

const registryEl = document.querySelector("#skill-registry");
const formEl = document.querySelector("#skill-form") as HTMLFormElement | null;
const skillIdEl = document.querySelector("#skill-id") as HTMLInputElement | null;
const titleEl = document.querySelector("#skill-title") as HTMLInputElement | null;
const contentEl = document.querySelector("#skill-content") as HTMLTextAreaElement | null;
const languageEl = document.querySelector("#skill-language") as HTMLInputElement | null;
const tagsEl = document.querySelector("#skill-tags") as HTMLInputElement | null;
const workflowStepsEl = document.querySelector("#skill-workflow-steps") as HTMLInputElement | null;
const artifactTypesEl = document.querySelector("#skill-artifact-types") as HTMLInputElement | null;
const provenanceEl = document.querySelector("#skill-provenance") as HTMLInputElement | null;
const qualityScoreEl = document.querySelector("#skill-quality-score") as HTMLInputElement | null;
const statusEl = document.querySelector("#skill-editor-status");
const toastRegion = document.querySelector("#dashboard-toast-region");

let skills: SkillPayload[] = [];
let selectedSkillId: string | null = null;

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
  workflow_steps: splitCsv(workflowStepsEl?.value ?? ""),
  artifact_types: splitCsv(artifactTypesEl?.value ?? ""),
  provenance: provenanceEl?.value.trim() || null,
  quality_score: Number(qualityScoreEl?.value ?? "0") || 0,
});

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
  setStatus("");
};

const renderRegistry = () => {
  if (!(registryEl instanceof HTMLElement)) return;
  if (!skills.length) {
    registryEl.innerHTML = `
      <article class="shell-card p-6 text-sm text-stone-600">
        No skills yet. Ingest the first skill from the editor.
      </article>
    `;
    return;
  }

  registryEl.innerHTML = skills
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
              <h2 class="mt-2 break-words text-xl font-semibold tracking-tight text-stone-950">
                ${escapeHtml(skill.title)}
              </h2>
              <div class="mt-2 flex flex-wrap gap-2">
                <span class="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.18em] text-emerald-800">q ${escapeHtml(skill.quality_score.toFixed(1))}</span>
                ${skill.provenance ? `<span class="rounded-full border border-stone-200 bg-stone-50 px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.18em] text-stone-600">${escapeHtml(skill.provenance)}</span>` : ""}
              </div>
              <p class="mt-3 line-clamp-3 text-sm leading-6 text-stone-600">
                ${escapeHtml(skill.content)}
              </p>
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
        const skill = skills.find((item) => item.id === button.dataset.skillSelect);
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
        const skill = skills.find((item) => item.id === skillId);
        if (!skillId || !skill) return;
        if (!window.confirm(`Delete skill ${skill.title}?`)) return;
        try {
          await deleteSkill(skillId);
          skills = skills.filter((item) => item.id !== skillId);
          if (selectedSkillId === skillId) fillForm();
          renderRegistry();
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

const refreshSkills = async () => {
  if (registryEl instanceof HTMLElement) {
    registryEl.innerHTML = `<article class="shell-card p-6 text-sm text-stone-600">Loading skills...</article>`;
  }
  try {
    skills = await listSkills();
    if (selectedSkillId) {
      const selected = skills.find((item) => item.id === selectedSkillId);
      if (selected) fillForm(selected);
    }
    renderRegistry();
  } catch (error) {
    if (registryEl instanceof HTMLElement) {
      registryEl.innerHTML = `<article class="shell-card p-6 text-sm text-red-700">${escapeHtml(error instanceof Error ? error.message : "Unable to load skills.")}</article>`;
    }
  }
};

document.querySelector("#skill-refresh-button")?.addEventListener("click", () => {
  void refreshSkills();
});

document.querySelector("#skill-reset-button")?.addEventListener("click", () => {
  fillForm();
  renderRegistry();
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
    fillForm(saved);
    await refreshSkills();
    showToast(`${isUpdate ? "Saved" : "Ingested"} skill ${saved.title}.`, "success");
    setStatus("Skill saved.", "success");
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to save skill.";
    setStatus(message, "danger");
    showToast(message, "danger");
  }
});

fillForm();
void refreshSkills();