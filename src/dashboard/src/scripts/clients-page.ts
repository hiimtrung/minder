import {
  createClient,
  getClientDetail,
  getClientOnboarding,
  listAudit,
  listClients,
  revokeClientKeys,
  rotateClientKey,
  testClientConnection,
} from "../lib/api/admin";

const registry = document.querySelector("#client-registry");
const status = document.querySelector("#create-client-status");
const createdResult = document.querySelector("#client-created-result");
const createdKey = document.querySelector("#client-created-key");
const toolScopes = document.querySelector("#client-tool-scopes");
const detailShell = document.querySelector("#client-detail-shell");
const detailTitle = document.querySelector("#detail-title");
const detailStatus = document.querySelector("#detail-status");
const snippets = document.querySelector("#onboarding-snippets");
const activity = document.querySelector("#activity-feed");
const rotatedKeyResult = document.querySelector("#rotated-key-result");
const rotatedKeyValue = document.querySelector("#rotated-key-value");
const toastRegion = document.querySelector("#dashboard-toast-region");
let lastSelectedClientName = "";

const escapeHtml = (value: string): string =>
  value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

const setDetailStatus = (message: string, tone: "default" | "success" | "danger" = "default") => {
  if (!detailStatus) return;
  detailStatus.textContent = message;
  detailStatus.className = "mt-4 min-h-6 text-sm";
  if (tone === "success") {
    detailStatus.classList.add("text-emerald-700");
    return;
  }
  if (tone === "danger") {
    detailStatus.classList.add("text-red-700");
    return;
  }
  detailStatus.classList.add("text-stone-600");
};

const showToast = (message: string, tone: "success" | "danger" | "default" = "default") => {
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

const presets: Record<string, string[]> = {
  query: ["minder_query", "minder_search_code", "minder_search_errors"],
  read: [
    "minder_query",
    "minder_search_code",
    "minder_search_errors",
    "minder_search",
    "minder_memory_recall",
    "minder_workflow_get",
  ],
  full: [
    "minder_query",
    "minder_search_code",
    "minder_search_errors",
    "minder_search",
    "minder_memory_recall",
    "minder_workflow_get",
    "minder_workflow_step",
  ],
};

const currentPath = window.location.pathname.replace(/\/$/, "");
const selectedClientId = currentPath.startsWith("/dashboard/clients/")
  ? currentPath.split("/").filter(Boolean).at(-1) ?? null
  : null;

const renderClients = async () => {
  if (!registry) return;
  try {
    const payload = await listClients();
    registry.innerHTML = payload.clients.length
      ? payload.clients
          .map(
            (client) => `
              <a href="/dashboard/clients/${client.id}" class="shell-card block p-6 transition hover:-translate-y-0.5">
                <p class="eyebrow">${client.slug}</p>
                <h2 class="mt-3 text-2xl font-semibold tracking-tight text-stone-950">${client.name}</h2>
                <p class="mt-3 text-sm leading-6 text-stone-700">${client.description || "No description yet."}</p>
                <p class="mt-5 text-sm text-stone-500">${client.tool_scopes.join(" · ") || "No scopes assigned"}</p>
              </a>
            `,
          )
          .join("")
      : `<article class="shell-card p-6 text-sm text-stone-600">No clients yet. Create the first one from this page.</article>`;
  } catch (error) {
    registry.innerHTML = `<article class="shell-card p-6 text-sm text-red-700">${
      error instanceof Error ? error.message : "Unable to load clients."
    }</article>`;
  }
};

const renderDetail = async () => {
  if (!selectedClientId || !detailShell || !detailTitle || !snippets || !activity) {
    return;
  }

  detailShell.classList.remove("hidden");

  try {
    const [detail, onboarding, audit] = await Promise.all([
      getClientDetail(selectedClientId),
      getClientOnboarding(selectedClientId),
      listAudit(),
    ]);

    document.title = `${detail.client.name} · Minder`;
    lastSelectedClientName = detail.client.name;
    detailTitle.textContent = detail.client.name;
    snippets.innerHTML = Object.entries(onboarding.templates)
      .map(
        ([target, template]) => `
          <article class="snippet-card rounded-3xl border border-stone-300 bg-stone-50/80 p-5">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <h3 class="text-sm font-semibold uppercase tracking-[0.16em] text-amber-800">${escapeHtml(target)}</h3>
              <button
                type="button"
                class="action-pill snippet-copy-button"
                data-snippet-label="${escapeHtml(target)}"
                data-snippet-content="${escapeHtml(template)}"
              >
                Copy Snippet
              </button>
            </div>
            <pre class="snippet-pre mt-4 overflow-x-auto whitespace-pre-wrap rounded-2xl bg-white px-4 py-4 text-sm leading-7 text-stone-700">${escapeHtml(template)}</pre>
          </article>
        `,
      )
      .join("");

    const relatedEvents = audit.events.filter((event) => event.resource_id === detail.client.id).slice(0, 8);
    activity.innerHTML = relatedEvents.length
      ? relatedEvents
          .map(
            (event) => `
              <div class="rounded-2xl border border-stone-300 bg-stone-50/80 px-4 py-3 text-sm text-stone-700">
                <strong class="text-stone-900">${event.event_type}</strong>
                <span class="mt-1 block text-stone-500">${event.created_at ?? "unknown time"}</span>
              </div>
            `,
          )
          .join("")
      : `<div class="rounded-2xl border border-stone-300 bg-stone-50/80 px-4 py-3 text-sm text-stone-600">No activity recorded yet.</div>`;
  } catch (error) {
    setDetailStatus(error instanceof Error ? error.message : "Unable to load client detail.", "danger");
  }
};

document.querySelectorAll("[data-tool-preset]").forEach((button) => {
  button.addEventListener("click", () => {
    const key = button.getAttribute("data-tool-preset") ?? "";
    const selected = presets[key] ?? [];
    if (!(toolScopes instanceof HTMLSelectElement)) return;
    Array.from(toolScopes.options).forEach((option) => {
      option.selected = selected.includes(option.value);
    });
  });
});

document.querySelector("#create-client-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = (document.querySelector("#client-name") as HTMLInputElement | null)?.value.trim() ?? "";
  const slug = (document.querySelector("#client-slug") as HTMLInputElement | null)?.value.trim() ?? "";
  const description =
    (document.querySelector("#client-description") as HTMLTextAreaElement | null)?.value.trim() ?? "";
  const repoScopeInput =
    (document.querySelector("#client-repo-scopes") as HTMLInputElement | null)?.value.trim() ?? "";
  const repo_scopes = repoScopeInput
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const selectedTools =
    toolScopes instanceof HTMLSelectElement
      ? Array.from(toolScopes.selectedOptions).map((option) => option.value)
      : [];

  if (!name || !slug) {
    if (status) status.textContent = "Name and slug are required.";
    return;
  }

  if (status) status.textContent = "Creating client...";
  try {
    const created = await createClient({ name, slug, description, tool_scopes: selectedTools, repo_scopes });
    if (createdKey) createdKey.textContent = created.client_api_key;
    createdResult?.classList.remove("hidden");
    if (status) status.textContent = `Created ${created.client.slug}.`;
    showToast(`Created client ${created.client.slug}.`, "success");
    await renderClients();
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to create client.";
    if (status) status.textContent = message;
    showToast(message, "danger");
  }
});

document.querySelector("#rotate-client-key")?.addEventListener("click", async () => {
  if (!selectedClientId) return;
  setDetailStatus("Issuing new client key...");
  try {
    const rotated = await rotateClientKey(selectedClientId);
    if (rotatedKeyValue) rotatedKeyValue.textContent = rotated.client_api_key;
    rotatedKeyResult?.classList.remove("hidden");
    setDetailStatus("Issued new client key.", "success");
    showToast("Issued new client key.", "success");
    await renderDetail();
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to rotate key.";
    setDetailStatus(message, "danger");
    showToast(message, "danger");
  }
});

document.querySelector("#revoke-client-key")?.addEventListener("click", async () => {
  if (!selectedClientId) return;
  setDetailStatus("Revoking client keys...");
  try {
    await revokeClientKeys(selectedClientId);
    setDetailStatus("Revoked all client keys.", "success");
    showToast("Revoked all client keys.", "success");
    await renderDetail();
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to revoke keys.";
    setDetailStatus(message, "danger");
    showToast(message, "danger");
  }
});

document.querySelector("#test-client-connection")?.addEventListener("click", async () => {
  const clientKey =
    (document.querySelector("#connection-api-key") as HTMLInputElement | null)?.value.trim() ?? "";
  if (!clientKey) {
    setDetailStatus("Client API key is required.", "danger");
    return;
  }
  setDetailStatus(`Running connection test${lastSelectedClientName ? ` for ${lastSelectedClientName}` : ""}...`);
  try {
    const result = await testClientConnection(clientKey);
    setDetailStatus(`Connection test passed for ${result.client.slug}.`, "success");
    showToast(`Connection test passed for ${result.client.slug}.`, "success");
  } catch (error) {
    const message = error instanceof Error ? error.message : "Connection test failed.";
    setDetailStatus(message, "danger");
    showToast(message, "danger");
  }
});

snippets?.addEventListener("click", async (event) => {
  const button = (event.target as HTMLElement | null)?.closest(".snippet-copy-button");
  if (!(button instanceof HTMLButtonElement)) return;
  const content = button.dataset.snippetContent ?? "";
  const label = button.dataset.snippetLabel ?? "snippet";
  try {
    await navigator.clipboard.writeText(content);
    setDetailStatus(`Copied ${label} snippet to clipboard.`, "success");
    showToast(`Copied ${label} snippet.`, "success");
  } catch {
    setDetailStatus(`Unable to copy ${label} snippet automatically.`, "danger");
    showToast(`Unable to copy ${label} snippet automatically.`, "danger");
  }
});

void renderClients();
void renderDetail();
