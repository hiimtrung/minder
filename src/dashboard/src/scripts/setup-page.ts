import { setupAdmin } from "../lib/api/admin";

const form = document.querySelector("#setup-form");
const status = document.querySelector("#setup-status");
const result = document.querySelector("#setup-result");
const apiKeyNode = document.querySelector("#setup-api-key");

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const username = (document.querySelector("#setup-username") as HTMLInputElement | null)?.value.trim() ?? "";
  const email = (document.querySelector("#setup-email") as HTMLInputElement | null)?.value.trim() ?? "";
  const display_name =
    (document.querySelector("#setup-display-name") as HTMLInputElement | null)?.value.trim() ?? "";

  if (!username || !email || !display_name) {
    if (status) status.textContent = "All fields are required.";
    return;
  }

  if (status) status.textContent = "Creating initial admin...";
  try {
    const created = await setupAdmin({ username, email, display_name });
    if (apiKeyNode) apiKeyNode.textContent = created.api_key;
    result?.classList.remove("hidden");
    if (status) status.textContent = "Admin created. Copy the bootstrap API key now.";
  } catch (error) {
    if (status) status.textContent = error instanceof Error ? error.message : "Setup failed.";
  }
});
