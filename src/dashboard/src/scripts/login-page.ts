import { getDashboardBootstrapState, loginAdmin } from "../lib/api/admin";

const loginForm = document.querySelector("#login-form");
const usernameInput = document.querySelector("#login-username") as HTMLInputElement | null;
const passwordInput = document.querySelector("#login-password") as HTMLInputElement | null;
const loginStatus = document.querySelector("#login-status");

const apiKeyForm = document.querySelector("#apikey-form");
const apiKeyInput = document.querySelector("#api-key") as HTMLInputElement | null;
const apiKeyStatus = document.querySelector("#apikey-status");

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
// Redirect helper
// ---------------------------------------------------------------------------

const redirectToDashboard = () => {
  window.location.href = "/dashboard/clients";
};

// ---------------------------------------------------------------------------
// Primary login: username + password
// ---------------------------------------------------------------------------

loginForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const username = usernameInput?.value.trim() ?? "";
  const password = passwordInput?.value ?? "";

  if (!username || !password) {
    if (loginStatus) loginStatus.textContent = "Username and password are required.";
    return;
  }

  if (loginStatus) loginStatus.textContent = "Signing in...";
  try {
    await loginAdmin({ username, password });
    redirectToDashboard();
  } catch (error) {
    if (loginStatus) {
      loginStatus.textContent =
        error instanceof Error ? error.message : "Unable to sign in.";
    }
  }
});

// ---------------------------------------------------------------------------
// Fallback login: API key
// ---------------------------------------------------------------------------

apiKeyForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const api_key = apiKeyInput?.value.trim() ?? "";

  if (!api_key) {
    if (apiKeyStatus) apiKeyStatus.textContent = "Admin API key is required.";
    return;
  }

  if (apiKeyStatus) apiKeyStatus.textContent = "Signing in...";
  try {
    await loginAdmin({ api_key });
    redirectToDashboard();
  } catch (error) {
    if (apiKeyStatus) {
      apiKeyStatus.textContent =
        error instanceof Error ? error.message : "Unable to sign in.";
    }
  }
});
