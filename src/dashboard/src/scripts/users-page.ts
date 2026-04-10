import {
  listUsers,
  updateUser,
  type UserPayload,
} from "../lib/api/admin";

// ---------------------------------------------------------------------------
// Element refs
// ---------------------------------------------------------------------------

const userListEl = document.querySelector("#user-list");
const editUserForm = document.querySelector("#edit-user-form");
const editUserHint = document.querySelector("#edit-user-hint");
const editDisplayName = document.querySelector("#edit-user-display-name") as HTMLInputElement | null;
const editRole = document.querySelector("#edit-user-role") as HTMLSelectElement | null;
const editIsActive = document.querySelector("#edit-user-is-active") as HTMLInputElement | null;
const editUserStatus = document.querySelector("#edit-user-status");
const cancelEditButton = document.querySelector("#cancel-edit-user");
const showInactiveToggle = document.querySelector(
  "#show-inactive-toggle",
) as HTMLInputElement | null;
const toastRegion = document.querySelector("#dashboard-toast-region");

let selectedUserId: string | null = null;
let cachedUsers: UserPayload[] = [];

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------

const showToast = (
  message: string,
  tone: "success" | "danger" | "default" = "default",
) => {
  if (!(toastRegion instanceof HTMLElement)) return;
  const toast = document.createElement("div");
  toast.className =
    "pointer-events-auto rounded-2xl border px-4 py-3 text-sm shadow-[0_18px_40px_rgba(28,25,23,0.12)] backdrop-blur transition";
  if (tone === "success") {
    toast.classList.add("border-emerald-200", "bg-emerald-50/95", "text-emerald-900");
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

// ---------------------------------------------------------------------------
// Edit panel
// ---------------------------------------------------------------------------

const setEditStatus = (
  message: string,
  tone: "default" | "success" | "danger" = "default",
) => {
  if (!editUserStatus) return;
  editUserStatus.textContent = message;
  editUserStatus.className = "min-h-6 text-sm";
  if (tone === "success") editUserStatus.classList.add("text-emerald-700");
  else if (tone === "danger") editUserStatus.classList.add("text-red-700");
  else editUserStatus.classList.add("text-stone-600");
};

const openEditPanel = (user: UserPayload) => {
  selectedUserId = user.id;
  if (editDisplayName) editDisplayName.value = user.display_name;
  if (editRole) editRole.value = user.role;
  if (editIsActive) editIsActive.checked = user.is_active;
  setEditStatus("");
  editUserHint?.classList.add("hidden");
  editUserForm?.classList.remove("hidden");
};

const closeEditPanel = () => {
  selectedUserId = null;
  editUserHint?.classList.remove("hidden");
  editUserForm?.classList.add("hidden");
};

cancelEditButton?.addEventListener("click", closeEditPanel);

editUserForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedUserId) return;

  const display_name = editDisplayName?.value.trim() ?? "";
  const role = editRole?.value ?? "member";
  const is_active = editIsActive?.checked ?? true;

  setEditStatus("Saving changes...");
  try {
    const result = await updateUser(selectedUserId, { display_name, role, is_active });
    const updated = result.user;
    // Patch cached list
    const idx = cachedUsers.findIndex((u) => u.id === updated.id);
    if (idx >= 0) cachedUsers[idx] = updated;
    await renderUsers();
    setEditStatus("Changes saved.", "success");
    showToast(`Saved ${updated.display_name}.`, "success");
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to save changes.";
    setEditStatus(message, "danger");
    showToast(message, "danger");
  }
});

// ---------------------------------------------------------------------------
// User list
// ---------------------------------------------------------------------------

const escapeHtml = (value: string): string =>
  value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

const renderUsers = async () => {
  if (!userListEl) return;
  const activeOnly = !(showInactiveToggle?.checked ?? false);
  try {
    const payload = await listUsers(!activeOnly);
    cachedUsers = payload.users;

    if (!cachedUsers.length) {
      userListEl.innerHTML = `<div class="rounded-2xl border border-stone-300 bg-stone-50/80 px-4 py-3 text-sm text-stone-600">No users found.</div>`;
      return;
    }

    userListEl.innerHTML = cachedUsers
      .map(
        (user) => `
        <button
          type="button"
          data-user-id="${escapeHtml(user.id)}"
          class="w-full text-left rounded-2xl border ${
            user.is_active
              ? "border-stone-200 bg-white hover:border-stone-300"
              : "border-stone-200 bg-stone-50/60 opacity-60"
          } px-5 py-4 transition ${
            selectedUserId === user.id ? "ring-2 ring-amber-400" : ""
          }"
        >
          <div class="flex items-center justify-between gap-4">
            <div class="min-w-0">
              <p class="truncate text-sm font-semibold text-stone-900">${escapeHtml(user.display_name)}</p>
              <p class="mt-0.5 truncate text-xs text-stone-500">${escapeHtml(user.email)}</p>
            </div>
            <div class="flex shrink-0 items-center gap-2">
              <span class="rounded-full border border-stone-200 bg-stone-100 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-stone-600">${escapeHtml(user.role)}</span>
              ${
                !user.is_active
                  ? `<span class="rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-[11px] font-semibold text-red-700">Inactive</span>`
                  : ""
              }
            </div>
          </div>
        </button>
      `,
      )
      .join("");

    // Wire row clicks
    userListEl.querySelectorAll<HTMLButtonElement>("[data-user-id]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const uid = btn.dataset.userId ?? "";
        const user = cachedUsers.find((u) => u.id === uid);
        if (user) openEditPanel(user);
        // Highlight selected row
        userListEl
          .querySelectorAll<HTMLButtonElement>("[data-user-id]")
          .forEach((b) => b.classList.remove("ring-2", "ring-amber-400"));
        btn.classList.add("ring-2", "ring-amber-400");
      });
    });
  } catch (error) {
    if (userListEl) {
      userListEl.innerHTML = `<div class="rounded-2xl border border-red-200 bg-red-50/80 px-4 py-3 text-sm text-red-700">${
        error instanceof Error ? error.message : "Unable to load users."
      }</div>`;
    }
  }
};

showInactiveToggle?.addEventListener("change", () => {
  void renderUsers();
});

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

void renderUsers();
