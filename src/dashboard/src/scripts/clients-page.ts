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
    detailTitle.textContent = detail.client.name;
    snippets.innerHTML = Object.entries(onboarding.templates)
      .map(
        ([target, template]) => `
          <article class="rounded-3xl border border-stone-300 bg-stone-50/80 p-4">
            <h3 class="text-sm font-semibold uppercase tracking-[0.16em] text-amber-800">${target}</h3>
            <pre class="mt-4 overflow-x-auto whitespace-pre-wrap text-xs leading-6 text-stone-700">${template.replaceAll("<", "&lt;")}</pre>
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
    if (detailStatus) detailStatus.textContent = error instanceof Error ? error.message : "Unable to load client detail.";
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
    await renderClients();
  } catch (error) {
    if (status) status.textContent = error instanceof Error ? error.message : "Unable to create client.";
  }
});

document.querySelector("#rotate-client-key")?.addEventListener("click", async () => {
  if (!selectedClientId) return;
  if (detailStatus) detailStatus.textContent = "Issuing new client key...";
  try {
    const rotated = await rotateClientKey(selectedClientId);
    if (rotatedKeyValue) rotatedKeyValue.textContent = rotated.client_api_key;
    rotatedKeyResult?.classList.remove("hidden");
    if (detailStatus) detailStatus.textContent = "Issued new client key.";
    await renderDetail();
  } catch (error) {
    if (detailStatus) detailStatus.textContent = error instanceof Error ? error.message : "Unable to rotate key.";
  }
});

document.querySelector("#revoke-client-key")?.addEventListener("click", async () => {
  if (!selectedClientId) return;
  if (detailStatus) detailStatus.textContent = "Revoking client keys...";
  try {
    await revokeClientKeys(selectedClientId);
    if (detailStatus) detailStatus.textContent = "Revoked all client keys.";
    await renderDetail();
  } catch (error) {
    if (detailStatus) detailStatus.textContent = error instanceof Error ? error.message : "Unable to revoke keys.";
  }
});

document.querySelector("#test-client-connection")?.addEventListener("click", async () => {
  const clientKey =
    (document.querySelector("#connection-api-key") as HTMLInputElement | null)?.value.trim() ?? "";
  if (!clientKey) {
    if (detailStatus) detailStatus.textContent = "Client API key is required.";
    return;
  }
  if (detailStatus) detailStatus.textContent = "Running connection test...";
  try {
    const result = await testClientConnection(clientKey);
    if (detailStatus) detailStatus.textContent = `Connection test passed for ${result.client.slug}.`;
  } catch (error) {
    if (detailStatus) detailStatus.textContent = error instanceof Error ? error.message : "Connection test failed.";
  }
});

void renderClients();
void renderDetail();
