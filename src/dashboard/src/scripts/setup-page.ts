import { setupAdmin } from "../lib/api/admin";

const form = document.querySelector("#setup-form");
const status = document.querySelector("#setup-status");
const result = document.querySelector("#setup-result");
const apiKeyNode = document.querySelector("#setup-api-key");

const setStatus = (message: string, tone: "default" | "danger" = "default") => {
  if (!status) return;
  status.textContent = message;
  status.className = "min-h-6 text-sm";
  if (tone === "danger") status.classList.add("text-red-600");
  else status.classList.add("text-stone-600");
};

form?.addEventListener("submit", async (event) => {
  event.preventDefault();

  const username =
    (document.querySelector("#setup-username") as HTMLInputElement | null)?.value.trim() ?? "";
  const email =
    (document.querySelector("#setup-email") as HTMLInputElement | null)?.value.trim() ?? "";
  const display_name =
    (document.querySelector("#setup-display-name") as HTMLInputElement | null)?.value.trim() ?? "";
  const password =
    (document.querySelector("#setup-password") as HTMLInputElement | null)?.value ?? "";
  const passwordConfirm =
    (document.querySelector("#setup-password-confirm") as HTMLInputElement | null)?.value ?? "";

  if (!username || !email || !display_name) {
    setStatus("Username, email, and display name are required.", "danger");
    return;
  }

  if (password && password.length < 8) {
    setStatus("Password must be at least 8 characters.", "danger");
    return;
  }

  if (password !== passwordConfirm) {
    setStatus("Passwords do not match.", "danger");
    return;
  }

  setStatus("Creating initial admin...");
  try {
    const created = await setupAdmin({
      username,
      email,
      display_name,
      password: password || undefined,
    });
    if (apiKeyNode) apiKeyNode.textContent = created.api_key;
    result?.classList.remove("hidden");
    setStatus("Admin created. You can now sign in with username + password.");
  } catch (error) {
    setStatus(error instanceof Error ? error.message : "Setup failed.", "danger");
  }
});
