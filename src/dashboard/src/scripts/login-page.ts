import { getDashboardBootstrapState, loginAdmin } from "../lib/api/admin";

const form = document.querySelector("#login-form");
const input = document.querySelector("#api-key");
const status = document.querySelector("#login-status");
const setupHint = document.querySelector("#setup-hint");

// ---------------------------------------------------------------------------
// Bootstrap check — show "First-Time Setup" hint only on a fresh install
// ---------------------------------------------------------------------------

void (async () => {
  try {
    const { has_admin_users } = await getDashboardBootstrapState();
    if (!has_admin_users && setupHint) {
      setupHint.classList.remove("hidden");
    }
  } catch {
    // If the check fails, leave the hint hidden — login still works.
  }
})();

// ---------------------------------------------------------------------------
// Login form
// ---------------------------------------------------------------------------

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const apiKey = input instanceof HTMLInputElement ? input.value.trim() : "";
  if (!apiKey) {
    if (status) status.textContent = "Admin API key is required.";
    return;
  }

  if (status) status.textContent = "Signing in...";
  try {
    await loginAdmin(apiKey);
    window.location.href = "/dashboard/clients";
  } catch (error) {
    if (status) {
      status.textContent =
        error instanceof Error ? error.message : "Unable to sign in.";
    }
  }
});
