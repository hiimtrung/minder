import { getAdminSession, logoutAdmin } from "../lib/api/admin";

const badge = document.querySelector("#dashboard-session-badge");
const logoutButton = document.querySelector("#dashboard-logout-button");

const setBadge = (message: string, tone: "active" | "idle" | "danger" = "active") => {
  if (!(badge instanceof HTMLElement)) return;
  badge.textContent = message;
  badge.className = "session-badge";
  if (tone === "active") {
    badge.classList.add("active");
  } else if (tone === "danger") {
    badge.classList.add("border-red-200", "bg-red-50", "text-red-800");
  }
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
