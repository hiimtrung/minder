import {
  createClient,
  type ClientPayload,
  getClientDetail,
  getClientOnboarding,
  listAudit,
  listTools,
  revokeClientKeys,
  rotateClientKey,
  searchAdminCatalog,
  testClientConnection,
  updateClient,
  type ToolInfo,
} from "../lib/api/admin";
import {
  createDebouncedHandler,
  setPagerStatus,
  updatePagerButtons,
} from "./catalog-controls";
import { getEl, setText, escapeHtml, escapeAttr, showToast } from "./ui-utils";
import { showApiKeyModal } from "./modal-controller";
import { snippetTitles, buildSnippetVariants, renderSnippetGuide, ideInstructions } from "./clients-snippets";


// (registry, status, etc. now accessed via getEl)
// (toastRegion moved to ui-utils.ts)
let lastSelectedClientName = "";
let cachedTools: ToolInfo[] = [];

const PAGE_SIZE = 20;
let visibleClients: ClientPayload[] = [];
let totalCount = 0;
let currentQuery = "";
let currentPage = 1;

// (editClientForm, etc. now accessed via getEl)

const setDetailStatus = (
  message: string,
  tone: "default" | "success" | "danger" = "default",
) => {
  const detailStatus = getEl("detail-status");
  if (!detailStatus) return;
  setText(detailStatus, message);
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

// (showToast moved to ui-utils.ts)

const presets: Record<string, string[]> = {
  query: [
    "minder_query",
    "minder_search_code",
    "minder_search_errors",
    "minder_search",
  ],
  read: [
    "minder_query",
    "minder_search_code",
    "minder_search_errors",
    "minder_search",
    "minder_memory_recall",
    "minder_memory_list",
    "minder_workflow_get",
    "minder_session_restore",
    "minder_session_context",
  ],
  full: [
    "minder_memory_store",
    "minder_memory_recall",
    "minder_memory_list",
    "minder_memory_delete",
    "minder_search",
    "minder_search_code",
    "minder_search_errors",
    "minder_query",
    "minder_workflow_get",
    "minder_workflow_step",
    "minder_workflow_update",
    "minder_workflow_guard",
    "minder_session_create",
    "minder_session_save",
    "minder_session_restore",
    "minder_session_context",
  ],
};

// ─── Edit preset map (mirrors create-form presets) ────────────────────────────
const editPresets: Record<string, string[]> = {
  query: [
    "minder_query",
    "minder_search_code",
    "minder_search_errors",
    "minder_search",
  ],
  read: [
    "minder_query",
    "minder_search_code",
    "minder_search_errors",
    "minder_search",
    "minder_memory_recall",
    "minder_memory_list",
    "minder_workflow_get",
    "minder_session_restore",
    "minder_session_context",
  ],
  full: [
    "minder_memory_store",
    "minder_memory_recall",
    "minder_memory_list",
    "minder_memory_delete",
    "minder_search",
    "minder_search_code",
    "minder_search_errors",
    "minder_query",
    "minder_workflow_get",
    "minder_workflow_step",
    "minder_workflow_update",
    "minder_workflow_guard",
    "minder_session_create",
    "minder_session_save",
    "minder_session_restore",
    "minder_session_context",
  ],
};

const setEditStatus = (
  message: string,
  tone: "default" | "success" | "danger" = "default",
) => {
  const editClientStatus = getEl("edit-client-status");
  if (!editClientStatus) return;
  setText(editClientStatus, message);
  editClientStatus.className = "min-h-6 text-sm";
  if (tone === "success") editClientStatus.classList.add("text-emerald-700");
  else if (tone === "danger") editClientStatus.classList.add("text-red-700");
  else editClientStatus.classList.add("text-stone-600");
};

const renderToolCheckboxes = (tools: ToolInfo[], selected: string[]) => {
  const editToolScopes = getEl("edit-tool-scopes");
  if (!editToolScopes) return;
  if (!tools.length) {
    editToolScopes.innerHTML = `<p class="text-sm text-stone-400 px-1">No tools available.</p>`;
    return;
  }
  editToolScopes.innerHTML = tools
    .map((tool) => {
      const checked = selected.includes(tool.name) ? "checked" : "";
      const id = `scope-${tool.name}`;
      return `
        <label for="${id}" class="flex items-start gap-3 rounded-xl px-2 py-2 hover:bg-stone-50 cursor-pointer group">
          <input
            type="checkbox"
            id="${id}"
            name="tool_scope"
            value="${escapeHtml(tool.name)}"
            ${checked}
            class="mt-0.5 h-4 w-4 shrink-0 rounded border-stone-300 accent-amber-600"
          />
          <span class="grid gap-0.5">
            <code class="text-xs font-semibold text-stone-900">${escapeHtml(tool.name)}</code>
            <span class="text-xs leading-5 text-stone-500">${escapeHtml(tool.description)}</span>
          </span>
        </label>
      `;
    })
    .join("");
};

const applyEditPreset = (key: string) => {
  const editToolScopes = getEl("edit-tool-scopes");
  if (!editToolScopes) return;
  if (key === "all") {
    editToolScopes
      .querySelectorAll<HTMLInputElement>("input[type=checkbox]")
      .forEach((cb) => {
        cb.checked = true;
      });
    return;
  }
  const selected = editPresets[key] ?? [];
  editToolScopes
    .querySelectorAll<HTMLInputElement>("input[type=checkbox]")
    .forEach((cb) => {
      cb.checked = selected.includes(cb.value);
    });
};

const getCheckedScopes = (): string[] => {
  const editToolScopes = getEl("edit-tool-scopes");
  if (!editToolScopes) return [];
  return Array.from(
    editToolScopes.querySelectorAll<HTMLInputElement>(
      "input[type=checkbox]:checked",
    ),
  ).map((cb) => cb.value);
};

const loadAndRenderTools = async (selectedScopes: string[] = []) => {
  const editToolScopes = getEl("edit-tool-scopes");
  try {
    if (!cachedTools.length) {
      const payload = await listTools();
      cachedTools = payload.tools;
    }
    renderToolCheckboxes(cachedTools, selectedScopes);
  } catch {
    if (editToolScopes) {
      editToolScopes.innerHTML = `<p class="text-sm text-red-600 px-1">Failed to load tools. Check server connection.</p>`;
    }
  }
};

const currentPath = window.location.pathname.replace(/\/$/, "");
const pathSegments = currentPath.split("/").filter(Boolean);
const selectedClientId =
  pathSegments.length > 2 &&
  pathSegments[0] === "dashboard" &&
  pathSegments[1] === "clients"
    ? decodeURIComponent(pathSegments.at(-1) ?? "") || null
    : null;

if (selectedClientId) {
  document
    .querySelectorAll<HTMLElement>("[data-current-detail-link]")
    .forEach((link) => {
      if (link instanceof HTMLAnchorElement) {
        link.href = window.location.pathname;
      }
    });
}

const renderClients = () => {
  const registry = getEl("client-registry");
  if (!registry) return;

  const pageCount = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
  const start = totalCount === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1;
  const end = Math.min(currentPage * PAGE_SIZE, totalCount);

  setPagerStatus(getEl("client-pagination-status"), {
    slice: {
      items: visibleClients,
      page: currentPage,
      pageCount,
      total: totalCount,
      start,
      end,
    },
    label: "clients",
    query: currentQuery,
  });
  updatePagerButtons(
    getEl("client-page-prev"),
    getEl("client-page-next"),
    currentPage,
    pageCount,
  );

  registry.innerHTML = visibleClients
    .map(
      (client) => `
          <a href="/dashboard/clients/${encodeURIComponent(client.id)}" class="shell-card block p-6 transition hover:-translate-y-0.5">
            <p class="eyebrow">${client.slug}</p>
            <h2 class="mt-3 text-2xl font-semibold tracking-tight text-stone-950">${client.name}</h2>
            <p class="mt-3 text-sm leading-6 text-stone-700">${client.description || "No description yet."}</p>
            <p class="mt-5 text-sm text-stone-500">${client.tool_scopes.join(" · ") || "No scopes assigned"}</p>
          </a>
        `,
    )
    .join("");
};

const syncVisibleClients = async () => {
  const registry = getEl("client-registry");
  if (registry) {
    registry.innerHTML = `<article class="shell-card p-6 text-sm text-stone-600">Loading client registry...</article>`;
  }
  try {
    const result = await searchAdminCatalog<ClientPayload>(
      "clients",
      currentQuery,
      PAGE_SIZE,
      (currentPage - 1) * PAGE_SIZE,
    );
    visibleClients = result.items;
    totalCount = result.total;
    renderClients();
  } catch (error) {
    if (registry) {
      registry.innerHTML = `<article class="shell-card p-6 text-sm text-red-700">${escapeHtml(error instanceof Error ? error.message : "Unable to load clients.")}</article>`;
    }
  }
};

document
  .querySelector("#client-refresh-button")
  ?.addEventListener("click", () => {
    void syncVisibleClients();
  });

getEl("client-page-prev")?.addEventListener("click", () => {
  currentPage = Math.max(1, currentPage - 1);
  void syncVisibleClients();
});

getEl("client-page-next")?.addEventListener("click", () => {
  currentPage += 1;
  void syncVisibleClients();
});

const debouncedSearch = createDebouncedHandler(async () => {
  const quickSearchEl = getEl<HTMLInputElement>("client-quick-search");
  currentQuery = quickSearchEl?.value.trim() ?? "";
  currentPage = 1;
  await syncVisibleClients();
  getEl("client-quick-search-loading")?.classList.add("hidden");
});

getEl("client-quick-search")?.addEventListener("input", () => {
  getEl("client-quick-search-loading")?.classList.remove("hidden");
  debouncedSearch();
});

const renderDetail = async () => {
  const detailShell = getEl("client-detail-shell");
  const detailTitle = getEl("detail-title");
  const snippets = getEl("onboarding-snippets");
  const activity = getEl("activity-feed");

  if (!detailShell || !detailTitle || !snippets || !activity) {
    return;
  }

  if (!selectedClientId) {
    detailTitle.textContent = "Client detail unavailable";
    snippets.innerHTML = `<article class="rounded-3xl border border-stone-300 bg-stone-50/80 p-4 text-sm text-stone-600">Open a client from the registry to load onboarding snippets.</article>`;
    activity.innerHTML = `<div class="rounded-2xl border border-stone-300 bg-stone-50/80 px-4 py-3 text-sm text-stone-600">Open a client from the registry to load audit activity.</div>`;
    setDetailStatus(
      "Select a client from the registry to load lifecycle controls.",
      "danger",
    );
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

    // Populate edit form
    const editClientName = getEl<HTMLInputElement>("edit-client-name");
    const editClientDescription = getEl<HTMLTextAreaElement>("edit-client-description");
    if (editClientName) editClientName.value = detail.client.name;
    if (editClientDescription)
      editClientDescription.value = detail.client.description;
    void loadAndRenderTools(detail.client.tool_scopes);
    snippets.innerHTML = Object.entries(onboarding.templates)
      .map(([target, template]) => {
        const title = snippetTitles[target] ?? target.replaceAll("_", " ");
        const variants = buildSnippetVariants(target, template);
        const isExpandedByDefault = target === "";
        const tabButtons = variants
          .map(
            (variant, index) => `
              <button
                type="button"
                class="rounded-full border px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.16em] transition ${index === 0 ? "border-amber-300 bg-amber-100 text-amber-950" : "border-stone-300 bg-white text-stone-700 hover:border-stone-400"}"
                data-snippet-tab
                data-target="${escapeHtml(target)}"
                data-variant-id="${escapeHtml(variant.id)}"
                aria-pressed="${index === 0 ? "true" : "false"}"
              >
                ${escapeHtml(variant.label)}
              </button>
            `,
          )
          .join("");
        const panels = variants
          .map((variant, index) => {
            const guideMarkup = renderSnippetGuide(variant);
            const copyButtons = variant.copyTargets
              .map(
                (copyTarget) => `
                  <button
                    type="button"
                    class="action-pill snippet-copy-button"
                    data-snippet-label="${escapeAttr(`${title} ${variant.label} ${copyTarget.label}`)}"
                    data-snippet-content="${escapeAttr(copyTarget.content)}"
                  >
                    ${escapeHtml(copyTarget.label)}
                  </button>
                `,
              )
              .join("");

            return `
              <div data-snippet-panel="${escapeHtml(target)}:${escapeHtml(variant.id)}" class="${index === 0 ? "" : "hidden"}">
                <div class="flex flex-wrap items-center justify-between gap-3">
                  <div class="flex flex-wrap items-center gap-2">
                    ${variant.preferred ? '<span class="inline-flex items-center rounded-full bg-emerald-100 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-900">Preferred</span>' : ""}
                  </div>
                  <div class="flex flex-wrap items-center justify-end gap-3">
                    ${copyButtons}
                  </div>
                </div>
                ${guideMarkup}
                <pre class="snippet-pre mt-4 overflow-x-auto whitespace-pre-wrap rounded-2xl bg-white px-4 py-4 text-sm leading-7 text-stone-700">${escapeHtml(variant.template)}</pre>
              </div>
            `;
          })
          .join("");
        return `
          <details class="snippet-card rounded-3xl border border-stone-300 bg-stone-50/80 p-5 open:border-amber-300 open:bg-amber-50/40" ${isExpandedByDefault ? "open" : ""}>
            <summary class="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3">
              <div>
                <h3 class="text-sm font-semibold uppercase tracking-[0.16em] text-amber-800">${escapeHtml(title)}</h3>
                <p class="mt-2 text-sm text-stone-600">Expand to view the preferred remote setup first, then switch to optional local stdio if you need it.</p>
              </div>
              <span class="action-pill" data-snippet-toggle-label>${isExpandedByDefault ? "Collapse" : "Expand"}</span>
            </summary>
            <div class="mt-4 border-t border-stone-200 pt-4">
              <div class="flex flex-wrap items-center justify-between gap-3">
                <div class="flex flex-wrap gap-2" data-snippet-tabs="${escapeHtml(target)}">
                  ${tabButtons}
                </div>
                <div class="text-xs uppercase tracking-[0.16em] text-stone-500">Remote first, local optional</div>
              </div>
              <div class="mt-4 grid gap-4">
                ${panels}
              </div>
            </div>
          </details>
        `;
      })
      .join("");

    snippets
      .querySelectorAll<HTMLDetailsElement>("details.snippet-card")
      .forEach((card) => {
        const updateToggleLabel = () => {
          const label = card.querySelector<HTMLElement>(
            "[data-snippet-toggle-label]",
          );
          if (label) {
            label.textContent = card.open ? "Collapse" : "Expand";
          }
        };
        updateToggleLabel();
        card.addEventListener("toggle", updateToggleLabel);
      });

    const relatedEvents = audit.events
      .filter((event) => event.resource_id === detail.client.id)
      .slice(0, 8);
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
    setDetailStatus(
      error instanceof Error ? error.message : "Unable to load client detail.",
      "danger",
    );
  }
};

const getCreateCheckedScopes = (): string[] => {
  const createToolScopes = getEl("client-tool-scopes");
  if (!createToolScopes) return [];
  return Array.from(
    createToolScopes.querySelectorAll<HTMLInputElement>(
      "input[type=checkbox]:checked",
    ),
  ).map((cb) => cb.value);
};

const renderCreateToolCheckboxes = (tools: ToolInfo[], selected: string[]) => {
  const createToolScopes = getEl("client-tool-scopes");
  if (!createToolScopes) return;
  if (!tools.length) {
    createToolScopes.innerHTML = `<p class="text-sm text-stone-400 px-1">No tools available.</p>`;
    return;
  }
  createToolScopes.innerHTML = tools
    .map((tool) => {
      const checked = selected.includes(tool.name) ? "checked" : "";
      const id = `create-scope-${tool.name}`;
      return `
        <label for="${id}" class="flex items-start gap-3 rounded-xl px-2 py-2 hover:bg-stone-50 cursor-pointer">
          <input
            type="checkbox"
            id="${id}"
            name="create_tool_scope"
            value="${escapeHtml(tool.name)}"
            ${checked}
            class="mt-0.5 h-4 w-4 shrink-0 rounded border-stone-300 accent-amber-600"
          />
          <span class="grid gap-0.5">
            <code class="text-xs font-semibold text-stone-900">${escapeHtml(tool.name)}</code>
            <span class="text-xs leading-5 text-stone-500">${escapeHtml(tool.description)}</span>
          </span>
        </label>
      `;
    })
    .join("");
};

const loadCreateTools = async (selectedScopes: string[] = []) => {
  const createToolScopes = getEl("client-tool-scopes");
  try {
    if (!cachedTools.length) {
      const payload = await listTools();
      cachedTools = payload.tools;
    }
    renderCreateToolCheckboxes(cachedTools, selectedScopes);
  } catch {
    if (createToolScopes) {
      createToolScopes.innerHTML = `<p class="text-sm text-red-600 px-1">Failed to load tools.</p>`;
    }
  }
};

document.querySelectorAll("[data-tool-preset]").forEach((button) => {
  button.addEventListener("click", () => {
    const key = button.getAttribute("data-tool-preset") ?? "";
    const createToolScopes = getEl("client-tool-scopes");
    if (!createToolScopes) return;
    if (key === "all") {
      createToolScopes
        .querySelectorAll<HTMLInputElement>("input[type=checkbox]")
        .forEach((cb) => {
          cb.checked = true;
        });
      return;
    }
    const selected = presets[key] ?? [];
    createToolScopes
      .querySelectorAll<HTMLInputElement>("input[type=checkbox]")
      .forEach((cb) => {
        cb.checked = selected.includes(cb.value);
      });
  });
});

document
  .querySelector("#create-refresh-tools")
  ?.addEventListener("click", async () => {
    cachedTools = [];
    const createToolScopes = getEl("client-tool-scopes");
    if (createToolScopes) {
      createToolScopes.innerHTML = `<p class="text-sm text-stone-400 px-1">Refreshing...</p>`;
    }
    await loadCreateTools();
    showToast("Tool list refreshed.", "success");
  });

document
  .querySelector("#create-client-form")
  ?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = (getEl("client-name") as HTMLInputElement | null)?.value.trim() ?? "";
    const slug = (getEl("client-slug") as HTMLInputElement | null)?.value.trim() ?? "";
    const description = (getEl("client-description") as HTMLTextAreaElement | null)?.value.trim() ?? "";
    const repoScopeInput = (getEl("client-repo-scopes") as HTMLInputElement | null)?.value.trim() ?? "";
    const repo_scopes = repoScopeInput
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    const selectedTools = getCreateCheckedScopes();

    const status = getEl("create-client-status");
    if (!name || !slug) {
      if (status) status.textContent = "Name and slug are required.";
      return;
    }

    if (status) status.textContent = "Creating client...";
    try {
      const created = await createClient({
        name,
        slug,
        description,
        tool_scopes: selectedTools,
        repo_scopes,
      });
      if (status) status.textContent = `Created ${created.client.slug}.`;
      showApiKeyModal(created.client_api_key);
      showToast(`Created client ${created.client.slug}.`, "success");
      await syncVisibleClients();
    } catch (error) {
      const status = getEl("create-client-status");
      const message =
        error instanceof Error ? error.message : "Unable to create client.";
      if (status) status.textContent = message;
      showToast(message, "danger");
    }
  });

document
  .querySelector("#rotate-client-key")
  ?.addEventListener("click", async () => {
    if (!selectedClientId) return;
    setDetailStatus("Issuing new client key...");
    try {
      const rotated = await rotateClientKey(selectedClientId);
      setDetailStatus("Issued new client key.", "success");
      showApiKeyModal(rotated.client_api_key);
      showToast("Issued new client key.", "success");
      await renderDetail();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to rotate key.";
      setDetailStatus(message, "danger");
      showToast(message, "danger");
    }
  });

document
  .querySelector("#revoke-client-key")
  ?.addEventListener("click", async () => {
    if (!selectedClientId) return;
    setDetailStatus("Revoking client keys...");
    try {
      await revokeClientKeys(selectedClientId);
      setDetailStatus("Revoked all client keys.", "success");
      showToast("Revoked all client keys.", "success");
      await renderDetail();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to revoke keys.";
      setDetailStatus(message, "danger");
      showToast(message, "danger");
    }
  });

document
  .querySelector("#test-client-connection")
  ?.addEventListener("click", async () => {
    const clientKey =
      (
        document.querySelector("#connection-api-key") as HTMLInputElement | null
      )?.value.trim() ?? "";
    if (!clientKey) {
      setDetailStatus("Client API key is required.", "danger");
      return;
    }
    setDetailStatus(
      `Running connection test${lastSelectedClientName ? ` for ${lastSelectedClientName}` : ""}...`,
    );
    try {
      const result = await testClientConnection(clientKey);
      setDetailStatus(
        `Connection test passed for ${result.client.slug}.`,
        "success",
      );
      showToast(`Connection test passed for ${result.client.slug}.`, "success");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Connection test failed.";
      setDetailStatus(message, "danger");
      showToast(message, "danger");
    }
  });

getEl("onboarding-snippets")?.addEventListener("click", async (event) => {
  const snippets = getEl("onboarding-snippets");
  if (!snippets) return;
  const tabButton = (event.target as HTMLElement | null)?.closest(
    "[data-snippet-tab]",
  );
  if (tabButton instanceof HTMLButtonElement) {
    const target = tabButton.dataset.target ?? "";
    const variantId = tabButton.dataset.variantId ?? "";
    snippets
      .querySelectorAll<HTMLButtonElement>(
        `[data-snippet-tab][data-target="${target}"]`,
      )
      .forEach((button) => {
        const isActive = button.dataset.variantId === variantId;
        button.setAttribute("aria-pressed", isActive ? "true" : "false");
        button.className = `rounded-full border px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.16em] transition ${isActive ? "border-amber-300 bg-amber-100 text-amber-950" : "border-stone-300 bg-white text-stone-700 hover:border-stone-400"}`;
      });
    snippets
      .querySelectorAll<HTMLElement>(`[data-snippet-panel^="${target}:"]`)
      .forEach((panel) => {
        panel.classList.toggle(
          "hidden",
          panel.dataset.snippetPanel !== `${target}:${variantId}`,
        );
      });
    return;
  }

  const button = (event.target as HTMLElement | null)?.closest(
    ".snippet-copy-button",
  );
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

// ─── Edit form — preset buttons ───────────────────────────────────────────────
document.querySelectorAll("[data-edit-preset]").forEach((button) => {
  button.addEventListener("click", () => {
    const key = button.getAttribute("data-edit-preset") ?? "";
    applyEditPreset(key);
  });
});

document.querySelector("#edit-select-none")?.addEventListener("click", () => {
  const editToolScopes = getEl("edit-tool-scopes");
  if (!editToolScopes) return;
  editToolScopes
    .querySelectorAll<HTMLInputElement>("input[type=checkbox]")
    .forEach((cb) => {
      cb.checked = false;
    });
});

// ─── Edit form — refresh tools button ────────────────────────────────────────
document
  .querySelector("#refresh-tools")
  ?.addEventListener("click", async () => {
    cachedTools = [];
    await loadAndRenderTools();
    await syncVisibleClients();
    showToast("Tool list refreshed.", "success");
  });

// ─── Edit form — submit ───────────────────────────────────────────────────────
getEl("edit-client-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedClientId) return;

  const name = (getEl("edit-client-name") as HTMLInputElement | null)?.value.trim() ?? "";
  const description = (getEl("edit-client-description") as HTMLTextAreaElement | null)?.value.trim() ?? "";
  const tool_scopes = getCheckedScopes();

  if (!name) {
    setEditStatus("Name is required.", "danger");
    return;
  }

  setEditStatus("Saving changes...");
  try {
    const result = await updateClient(selectedClientId, {
      name,
      description,
      tool_scopes,
    });
    lastSelectedClientName = result.client.name;
    const detailTitle = getEl("detail-title");
    if (detailTitle) detailTitle.textContent = result.client.name;
    document.title = `${result.client.name} · Minder`;
    setEditStatus("Changes saved.", "success");
    showToast(`Saved ${result.client.slug}.`, "success");
    await syncVisibleClients();
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unable to save changes.";
    setEditStatus(message, "danger");
    showToast(message, "danger");
  }
});


const renderAgentInstructions = () => {
  const container = getEl("agent-instruction-snippets");
  if (!container) return;

  container.innerHTML = ideInstructions
    .map(
      ({ id, title, filename, content }) => `
      <details class="snippet-card rounded-3xl border border-stone-300 bg-stone-50/80 p-5 open:border-amber-300 open:bg-amber-50/40">
        <summary class="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3">
          <div>
            <h3 class="text-sm font-semibold uppercase tracking-[0.16em] text-amber-800">${escapeHtml(title)}</h3>
            <p class="mt-2 text-sm text-stone-600">Paste into <code class="text-xs font-mono">${escapeHtml(filename)}</code> in your project root.</p>
          </div>
          <span class="action-pill" data-instruction-toggle-label="${escapeAttr(id)}">Expand</span>
        </summary>
        <div class="mt-4 border-t border-stone-200 pt-4">
          <div class="flex flex-wrap items-center justify-end gap-3">
            <button
              type="button"
              class="action-pill instruction-copy-button"
              data-instruction-content="${escapeAttr(content)}"
              data-instruction-label="${escapeAttr(title)}"
            >
              Copy instruction
            </button>
          </div>
          <pre class="snippet-pre mt-4 overflow-x-auto whitespace-pre-wrap rounded-2xl bg-white px-4 py-4 text-sm leading-7 text-stone-700">${escapeHtml(content)}</pre>
        </div>
      </details>
    `,
    )
    .join("");

  container
    .querySelectorAll<HTMLDetailsElement>("details.snippet-card")
    .forEach((card) => {
      const id = card.querySelector<HTMLElement>("[data-instruction-toggle-label]")
        ?.dataset.instructionToggleLabel ?? "";
      const updateLabel = () => {
        const label = card.querySelector<HTMLElement>(
          `[data-instruction-toggle-label="${id}"]`,
        );
        if (label) label.textContent = card.open ? "Collapse" : "Expand";
      };
      updateLabel();
      card.addEventListener("toggle", updateLabel);
    });
};

getEl("agent-instruction-snippets")?.addEventListener("click", async (event) => {
  const button = (event.target as HTMLElement | null)?.closest(
    ".instruction-copy-button",
  );
  if (!(button instanceof HTMLButtonElement)) return;
  const content = button.dataset.instructionContent ?? "";
  const label = button.dataset.instructionLabel ?? "instruction";
  try {
    await navigator.clipboard.writeText(content);
    showToast(`Copied ${label} instruction.`, "success");
  } catch {
    showToast(`Unable to copy ${label} instruction.`, "danger");
  }
});

void syncVisibleClients();
void renderDetail();
if (getEl("agent-instruction-snippets")) renderAgentInstructions();
if (getEl("client-tool-scopes")) void loadCreateTools();
