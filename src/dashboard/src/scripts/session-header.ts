import { getAdminSession, logoutAdmin } from "../lib/api/admin";

const badge = document.querySelector("#dashboard-session-badge");
const logoutButton = document.querySelector("#dashboard-logout-button");

const setBadge = (message: string, tone: "active" | "idle" | "danger" = "active") => {
  if (!(badge instanceof HTMLElement)) return;
  badge.textContent = message;
  badge.className =
    "inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold tracking-[0.18em] uppercase";
  if (tone === "danger") {
    badge.classList.add("border", "border-red-200", "bg-red-50", "text-red-800");
    return;
  }
  if (tone === "idle") {
    badge.classList.add("border", "border-stone-300", "bg-white", "text-stone-700");
    return;
  }
  badge.classList.add("border", "border-emerald-200", "bg-emerald-50", "text-emerald-800");
};

const boot = async () => {
  try {
    const session = await getAdminSession();
    setBadge(session.admin.display_name || session.admin.username, "active");
  } catch {
    setBadge("Session Missing", "danger");
  }
};

logoutButton?.addEventListener("click", async () => {
  try {
    await logoutAdmin();
  } finally {
    window.location.href = "/dashboard/login";
  }
});

void boot();
