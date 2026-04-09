import { loginAdmin } from "../lib/api/admin";

const form = document.querySelector("#login-form");
const input = document.querySelector("#api-key");
const status = document.querySelector("#login-status");

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
    if (status) status.textContent = error instanceof Error ? error.message : "Unable to sign in.";
  }
});
