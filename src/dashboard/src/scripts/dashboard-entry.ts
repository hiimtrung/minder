import { getDashboardBootstrapState } from "../lib/api/admin";

const status = document.querySelector("#dashboard-entry-status");

const setMessage = (message: string) => {
  if (status instanceof HTMLElement) {
    status.textContent = message;
  }
};

const redirectToTarget = async () => {
  setMessage("Resolving dashboard state...");
  try {
    const state = await getDashboardBootstrapState();
    const next = !state.has_admin_users
      ? "/dashboard/setup"
      : state.has_admin_session
        ? "/dashboard/repositories"
        : "/dashboard/login";
    window.location.replace(next);
  } catch {
    window.location.replace("/dashboard/login");
  }
};

void redirectToTarget();
