import {
  createClient,
  getClientDetail,
  getClientOnboarding,
  listAudit,
  listClients,
  listTools,
  revokeClientKeys,
  rotateClientKey,
  testClientConnection,
  updateClient,
  type ToolInfo,
} from "../lib/api/admin";

const registry = document.querySelector("#client-registry");
const status = document.querySelector("#create-client-status");
const createdResult = document.querySelector("#client-created-result");
const createdKey = document.querySelector("#client-created-key");
const createToolScopes = document.querySelector("#client-tool-scopes");
const detailShell = document.querySelector("#client-detail-shell");
const detailTitle = document.querySelector("#detail-title");
const detailStatus = document.querySelector("#detail-status");
const snippets = document.querySelector("#onboarding-snippets");
const activity = document.querySelector("#activity-feed");
const rotatedKeyResult = document.querySelector("#rotated-key-result");
const rotatedKeyValue = document.querySelector("#rotated-key-value");
const toastRegion = document.querySelector("#dashboard-toast-region");
let lastSelectedClientName = "";
let cachedTools: ToolInfo[] = [];

// Edit form elements (detail page only)
const editClientForm = document.querySelector("#edit-client-form");
const editClientName = document.querySelector(
  "#edit-client-name",
) as HTMLInputElement | null;
const editClientDescription = document.querySelector(
  "#edit-client-description",
) as HTMLTextAreaElement | null;
const editToolScopes = document.querySelector("#edit-tool-scopes");
const editClientStatus = document.querySelector("#edit-client-status");

const snippetTitles: Record<string, string> = {
  codex: "OpenAI Codex",
  vscode: "VS Code / GitHub Copilot",
  copilot_cli: "GitHub Copilot CLI",
  antigravity: "Google Antigravity",
  cursor: "Cursor",
  claude_code: "Claude Code",
};

type SnippetDoc = {
  label: string;
  href: string;
};

type SnippetVariant = {
  id: string;
  label: string;
  summary: string;
  transport: string;
  steps: string[];
  docs: SnippetDoc[];
  template: string;
  preferred?: boolean;
  copyTargets: Array<{
    label: string;
    content: string;
  }>;
};

const docsByTarget: Record<string, SnippetDoc[]> = {
  codex: [
    {
      label: "OpenAI Codex MCP docs",
      href: "https://developers.openai.com/codex/mcp",
    },
  ],
  vscode: [
    {
      label: "GitHub Copilot Chat MCP guide",
      href: "https://docs.github.com/en/copilot/how-tos/provide-context/use-mcp/extend-copilot-chat-with-mcp",
    },
    {
      label: "VS Code MCP configuration reference",
      href: "https://code.visualstudio.com/docs/copilot/reference/mcp-configuration",
    },
  ],
  copilot_cli: [
    {
      label: "GitHub Copilot CLI MCP docs",
      href: "https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers",
    },
  ],
  antigravity: [
    {
      label: "Google Antigravity MCP docs",
      href: "https://antigravity.google/docs/mcp",
    },
  ],
  cursor: [
    {
      label: "Cursor MCP docs",
      href: "https://cursor.com/docs/mcp",
    },
  ],
  claude_code: [
    {
      label: "Claude Code MCP docs",
      href: "https://code.claude.com/docs/en/mcp",
    },
  ],
};

const localSnippetTemplates: Record<string, string> = {
  codex: [
    "[mcp_servers.minder]",
    'command = "uv"',
    'args = ["run", "python", "-m", "minder.server"]',
    'cwd = "/absolute/path/to/minder"',
    'env = { MINDER_SERVER__TRANSPORT = "stdio", MINDER_CLIENT_API_KEY = "<mkc_...>" }',
  ].join("\n"),
  vscode: JSON.stringify(
    {
      servers: {
        minder: {
          type: "stdio",
          command: "uv",
          args: ["run", "python", "-m", "minder.server"],
          cwd: "/absolute/path/to/minder",
          env: {
            MINDER_SERVER__TRANSPORT: "stdio",
            MINDER_CLIENT_API_KEY: "<mkc_...>",
          },
        },
      },
      inputs: [],
    },
    null,
    2,
  ),
  copilot_cli: JSON.stringify(
    {
      mcpServers: {
        minder: {
          type: "stdio",
          command: "uv",
          args: ["run", "python", "-m", "minder.server"],
          cwd: "/absolute/path/to/minder",
          env: {
            MINDER_SERVER__TRANSPORT: "stdio",
            MINDER_CLIENT_API_KEY: "<mkc_...>",
          },
          tools: ["*"],
        },
      },
    },
    null,
    2,
  ),
  antigravity: JSON.stringify(
    {
      mcpServers: {
        minder: {
          command: "uv",
          args: ["run", "python", "-m", "minder.server"],
          cwd: "/absolute/path/to/minder",
          env: {
            MINDER_SERVER__TRANSPORT: "stdio",
            MINDER_CLIENT_API_KEY: "<mkc_...>",
          },
        },
      },
    },
    null,
    2,
  ),
  cursor: JSON.stringify(
    {
      mcpServers: {
        minder: {
          type: "stdio",
          command: "uv",
          args: ["run", "python", "-m", "minder.server"],
          cwd: "/absolute/path/to/minder",
          env: {
            MINDER_SERVER__TRANSPORT: "stdio",
            MINDER_CLIENT_API_KEY: "<mkc_...>",
          },
        },
      },
    },
    null,
    2,
  ),
  claude_code: JSON.stringify(
    {
      mcpServers: {
        minder: {
          command: "uv",
          args: ["run", "python", "-m", "minder.server"],
          cwd: "/absolute/path/to/minder",
          env: {
            MINDER_SERVER__TRANSPORT: "stdio",
            MINDER_CLIENT_API_KEY: "<mkc_...>",
          },
        },
      },
    },
    null,
    2,
  ),
};

const escapeHtml = (value: string): string =>
  value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

const formatSnippet = (template: string): string => {
  try {
    return JSON.stringify(JSON.parse(template), null, 2);
  } catch {
    return template;
  }
};

const extractJsonServerEntry = (template: string): string | null => {
  try {
    const payload = JSON.parse(template) as {
      servers?: Record<string, unknown>;
      mcpServers?: Record<string, unknown>;
    };
    const entry = payload.servers?.minder ?? payload.mcpServers?.minder;
    if (!entry) {
      return null;
    }
    return JSON.stringify(entry, null, 2);
  } catch {
    return null;
  }
};

const buildSnippetVariants = (
  target: string,
  remoteTemplate: string,
): SnippetVariant[] => {
  const docs = docsByTarget[target] ?? [];
  const formattedRemote = formatSnippet(remoteTemplate);
  const formattedLocal = localSnippetTemplates[target]
    ? formatSnippet(localSnippetTemplates[target])
    : "";
  const remoteEntry = extractJsonServerEntry(formattedRemote);
  const localEntry = extractJsonServerEntry(formattedLocal);

  const buildCopyTargets = (
    fullContent: string,
    entryContent: string | null,
    fullLabel = "Copy Snippet",
  ): SnippetVariant["copyTargets"] => {
    const targets = [{ label: fullLabel, content: fullContent }];
    if (entryContent) {
      targets.push({ label: "Copy Server Entry", content: entryContent });
    }
    return targets;
  };

  switch (target) {
    case "codex":
      return [
        {
          id: "remote",
          label: "Preferred Remote",
          transport: "Remote endpoint",
          summary:
            "Start with the remote Minder endpoint so Codex connects without launching a local process. If your Codex build only works reliably with local MCP, switch to the Local stdio tab.",
          steps: [
            "Open ~/.codex/config.toml or the trusted project .codex/config.toml file.",
            "Paste this remote minder block under mcp_servers.",
            "Replace <mkc_...> with the client API key shown in this dashboard.",
            "Run codex mcp or reopen the MCP panel and confirm the minder server is connected.",
          ],
          docs,
          template: formattedRemote,
          preferred: true,
          copyTargets: buildCopyTargets(formattedRemote, null),
        },
        {
          id: "local",
          label: "Local stdio",
          transport: "Optional fallback",
          summary:
            "Use this when you want Codex to start Minder directly on your machine or if the remote endpoint is not suitable for your setup.",
          steps: [
            "Keep the config in ~/.codex/config.toml or a trusted project .codex/config.toml.",
            "Replace /absolute/path/to/minder and <mkc_...> with your repo path and client API key.",
            "Restart Codex or reopen the MCP panel.",
          ],
          docs,
          template: formattedLocal,
          copyTargets: buildCopyTargets(formattedLocal, null),
        },
      ];
    case "vscode":
      return [
        {
          id: "remote",
          label: "Preferred SSE",
          transport: "Remote SSE",
          summary:
            "Use this for the cleanest VS Code / Copilot Chat setup against Minder's remote endpoint.",
          steps: [
            "Open .vscode/mcp.json in the repository or run MCP: Open User Configuration.",
            "Replace the minder server under servers with this remote configuration.",
            "Replace <mkc_...> with the client API key shown in this dashboard.",
            "Save the file, start or restart the server, then open Copilot Chat in Agent mode and verify Minder tools are available.",
          ],
          docs,
          template: formattedRemote,
          preferred: true,
          copyTargets: buildCopyTargets(
            formattedRemote,
            remoteEntry,
            "Copy Full File",
          ),
        },
        {
          id: "local",
          label: "Local stdio",
          transport: "Optional fallback",
          summary:
            "Use this when you want VS Code to start Minder locally instead of connecting to the remote SSE endpoint.",
          steps: [
            "Keep this in .vscode/mcp.json or your user-profile mcp.json.",
            "Replace /absolute/path/to/minder and <mkc_...> with your local repo path and client API key.",
            "Save, restart the server from MCP: List Servers, and verify the tools reload.",
          ],
          docs,
          template: formattedLocal,
          copyTargets: buildCopyTargets(
            formattedLocal,
            localEntry,
            "Copy Full File",
          ),
        },
      ];
    case "copilot_cli":
      return [
        {
          id: "remote",
          label: "Preferred SSE",
          transport: "Remote SSE",
          summary:
            "Use this for the simplest Copilot CLI setup against Minder's remote endpoint.",
          steps: [
            "Open ~/.copilot/mcp-config.json or use /mcp add.",
            "If you use /mcp add, choose HTTP or SSE, paste the Minder URL, and add the X-Minder-Client-Key header.",
            "Replace <mkc_...> with the client API key shown in this dashboard if you edit JSON directly.",
            "Run /mcp show and confirm the minder server is enabled.",
          ],
          docs,
          template: formattedRemote,
          preferred: true,
          copyTargets: buildCopyTargets(
            formattedRemote,
            remoteEntry,
            "Copy Full File",
          ),
        },
        {
          id: "local",
          label: "Local stdio",
          transport: "Optional fallback",
          summary:
            "Use this when you want Copilot CLI to launch Minder locally instead of calling the remote endpoint.",
          steps: [
            "Edit ~/.copilot/mcp-config.json.",
            "Replace /absolute/path/to/minder and <mkc_...> with your local repo path and client API key.",
            "Run /mcp show and confirm the server reconnects.",
          ],
          docs,
          template: formattedLocal,
          copyTargets: buildCopyTargets(
            formattedLocal,
            localEntry,
            "Copy Full File",
          ),
        },
      ];
    case "antigravity":
      return [
        {
          id: "remote",
          label: "Preferred Remote",
          transport: "Remote URL",
          summary:
            "Start with the remote Minder endpoint in Antigravity. If your setup works better with a local process, switch to the Local stdio tab.",
          steps: [
            "Open the MCP Store, choose Manage MCP Servers, then View raw config.",
            "Replace the minder entry in ~/.gemini/antigravity/mcp_config.json with this remote configuration.",
            "Replace <mkc_...> with the client API key shown in this dashboard.",
            "Save the config and verify the server reconnects.",
          ],
          docs,
          template: formattedRemote,
          preferred: true,
          copyTargets: buildCopyTargets(
            formattedRemote,
            remoteEntry,
            "Copy Full File",
          ),
        },
        {
          id: "local",
          label: "Local stdio",
          transport: "Optional fallback",
          summary:
            "Use this when you want Antigravity to launch Minder directly on your machine.",
          steps: [
            "Open the same raw config file in ~/.gemini/antigravity/mcp_config.json.",
            "Replace /absolute/path/to/minder and <mkc_...> with your repo path and client API key.",
            "Save the config and confirm the server reconnects.",
          ],
          docs,
          template: formattedLocal,
          copyTargets: buildCopyTargets(
            formattedLocal,
            localEntry,
            "Copy Full File",
          ),
        },
      ];
    case "cursor":
      return [
        {
          id: "remote",
          label: "Preferred HTTP",
          transport: "Remote HTTP",
          summary:
            "Use Cursor's remote MCP support with Minder's streamable HTTP endpoint first. Switch to Local stdio only if you want Cursor to launch Minder directly from your machine.",
          steps: [
            "Create or edit .cursor/mcp.json in the project, or ~/.cursor/mcp.json for a global setup.",
            "Replace the minder server entry with this remote configuration.",
            "Replace <mkc_...> with the client API key shown in this dashboard.",
            "Save the file, reopen MCP settings if needed, and confirm the minder server appears in Cursor.",
          ],
          docs,
          template: formattedRemote,
          preferred: true,
          copyTargets: buildCopyTargets(
            formattedRemote,
            remoteEntry,
            "Copy Full File",
          ),
        },
        {
          id: "local",
          label: "Local stdio",
          transport: "Optional fallback",
          summary:
            "Use this when you want Cursor to start Minder locally instead of calling the remote MCP endpoint.",
          steps: [
            "Keep the config in .cursor/mcp.json or ~/.cursor/mcp.json.",
            "Replace /absolute/path/to/minder and <mkc_...> with your repo path and client API key.",
            "Save the file and verify Cursor reconnects to the local server.",
          ],
          docs,
          template: formattedLocal,
          copyTargets: buildCopyTargets(
            formattedLocal,
            localEntry,
            "Copy Full File",
          ),
        },
      ];
    case "claude_code":
      return [
        {
          id: "remote",
          label: "Preferred SSE",
          transport: "Remote SSE",
          summary:
            "Use this to connect Claude Code to Minder's remote SSE endpoint first. Switch to Local stdio if you prefer a machine-local process.",
          steps: [
            "Open or create a project .mcp.json file, or use claude mcp add-json.",
            "Paste this remote minder entry into mcpServers.",
            "Replace <mkc_...> with the client API key shown in this dashboard.",
            "Run /mcp or claude mcp list and confirm the server is available.",
          ],
          docs,
          template: formattedRemote,
          preferred: true,
          copyTargets: buildCopyTargets(
            formattedRemote,
            remoteEntry,
            "Copy Full File",
          ),
        },
        {
          id: "local",
          label: "Local stdio",
          transport: "Optional fallback",
          summary:
            "Use this when you want Claude Code to start Minder locally instead of connecting to the remote endpoint.",
          steps: [
            "Keep the config in a project .mcp.json file or add it with claude mcp add-json.",
            "Replace /absolute/path/to/minder and <mkc_...> with your repo path and client API key.",
            "Run /mcp or claude mcp list to verify the local process is registered.",
          ],
          docs,
          template: formattedLocal,
          copyTargets: buildCopyTargets(
            formattedLocal,
            localEntry,
            "Copy Full File",
          ),
        },
      ];
    default:
      return [
        {
          id: "default",
          label: "Snippet",
          transport: "Default",
          summary: "Use this configuration as shown.",
          steps: [],
          docs,
          template: formattedRemote,
          copyTargets: buildCopyTargets(formattedRemote, remoteEntry),
        },
      ];
  }
};

const renderSnippetGuide = (variant: SnippetVariant): string => {
  const docsMarkup = variant.docs
    .map(
      (doc) => `
        <a
          href="${doc.href}"
          target="_blank"
          rel="noreferrer"
          class="action-pill"
        >
          ${escapeHtml(doc.label)}
        </a>
      `,
    )
    .join("");

  const stepsMarkup = variant.steps
    .map(
      (step, index) => `
        <li class="flex gap-3 text-sm leading-6 text-stone-700">
          <span class="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber-100 text-xs font-semibold text-amber-900">${index + 1}</span>
          <span>${escapeHtml(step)}</span>
        </li>
      `,
    )
    .join("");

  return `
    <div class="mt-4 rounded-2xl border border-amber-200 bg-amber-50/60 p-4">
      <div class="flex flex-wrap items-center gap-2">
        <span class="inline-flex items-center rounded-full bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-900">${escapeHtml(variant.transport)}</span>
        <p class="text-sm leading-6 text-stone-700">${escapeHtml(variant.summary)}</p>
      </div>
      <div class="mt-4 flex flex-wrap gap-2">
        ${docsMarkup}
      </div>
      <ol class="mt-4 grid gap-3">
        ${stepsMarkup}
      </ol>
    </div>
  `;
};

const setDetailStatus = (
  message: string,
  tone: "default" | "success" | "danger" = "default",
) => {
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

const showToast = (
  message: string,
  tone: "success" | "danger" | "default" = "default",
) => {
  if (!(toastRegion instanceof HTMLElement)) return;
  const toast = document.createElement("div");
  toast.className =
    "pointer-events-auto rounded-2xl border px-4 py-3 text-sm shadow-[0_18px_40px_rgba(28,25,23,0.12)] backdrop-blur transition";
  if (tone === "success") {
    toast.classList.add(
      "border-emerald-200",
      "bg-emerald-50/95",
      "text-emerald-900",
    );
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
  if (!editClientStatus) return;
  editClientStatus.textContent = message;
  editClientStatus.className = "min-h-6 text-sm";
  if (tone === "success") editClientStatus.classList.add("text-emerald-700");
  else if (tone === "danger") editClientStatus.classList.add("text-red-700");
  else editClientStatus.classList.add("text-stone-600");
};

const renderToolCheckboxes = (tools: ToolInfo[], selected: string[]) => {
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
  if (!editToolScopes) return [];
  return Array.from(
    editToolScopes.querySelectorAll<HTMLInputElement>(
      "input[type=checkbox]:checked",
    ),
  ).map((cb) => cb.value);
};

const loadAndRenderTools = async (selectedScopes: string[] = []) => {
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

const renderClients = async () => {
  if (!registry) return;
  try {
    const payload = await listClients();
    registry.innerHTML = payload.clients.length
      ? payload.clients
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
          .join("")
      : `<article class="shell-card p-6 text-sm text-stone-600">No clients yet. Create the first one from this page.</article>`;
  } catch (error) {
    registry.innerHTML = `<article class="shell-card p-6 text-sm text-red-700">${
      error instanceof Error ? error.message : "Unable to load clients."
    }</article>`;
  }
};

const renderDetail = async () => {
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
                    data-snippet-label="${escapeHtml(title)} ${escapeHtml(variant.label)} ${escapeHtml(copyTarget.label)}"
                    data-snippet-content="${escapeHtml(copyTarget.content)}"
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
  if (!createToolScopes) return [];
  return Array.from(
    createToolScopes.querySelectorAll<HTMLInputElement>(
      "input[type=checkbox]:checked",
    ),
  ).map((cb) => cb.value);
};

const renderCreateToolCheckboxes = (tools: ToolInfo[], selected: string[]) => {
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
    const name =
      (
        document.querySelector("#client-name") as HTMLInputElement | null
      )?.value.trim() ?? "";
    const slug =
      (
        document.querySelector("#client-slug") as HTMLInputElement | null
      )?.value.trim() ?? "";
    const description =
      (
        document.querySelector(
          "#client-description",
        ) as HTMLTextAreaElement | null
      )?.value.trim() ?? "";
    const repoScopeInput =
      (
        document.querySelector("#client-repo-scopes") as HTMLInputElement | null
      )?.value.trim() ?? "";
    const repo_scopes = repoScopeInput
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    const selectedTools = getCreateCheckedScopes();

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
      if (createdKey) createdKey.textContent = created.client_api_key;
      createdResult?.classList.remove("hidden");
      if (status) status.textContent = `Created ${created.client.slug}.`;
      showToast(`Created client ${created.client.slug}.`, "success");
      await renderClients();
    } catch (error) {
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
      if (rotatedKeyValue) rotatedKeyValue.textContent = rotated.client_api_key;
      rotatedKeyResult?.classList.remove("hidden");
      setDetailStatus("Issued new client key.", "success");
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

snippets?.addEventListener("click", async (event) => {
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
    const currentScopes = getCheckedScopes();
    if (editToolScopes) {
      editToolScopes.innerHTML = `<p class="text-sm text-stone-400 px-1">Refreshing...</p>`;
    }
    await loadAndRenderTools(currentScopes);
    showToast("Tool list refreshed.", "success");
  });

// ─── Edit form — submit ───────────────────────────────────────────────────────
editClientForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedClientId) return;

  const name = editClientName?.value.trim() ?? "";
  const description = editClientDescription?.value.trim() ?? "";
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
    if (detailTitle) detailTitle.textContent = result.client.name;
    document.title = `${result.client.name} · Minder`;
    setEditStatus("Changes saved.", "success");
    showToast(`Saved ${result.client.slug}.`, "success");
    await renderClients();
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unable to save changes.";
    setEditStatus(message, "danger");
    showToast(message, "danger");
  }
});

void renderClients();
void renderDetail();
if (createToolScopes) void loadCreateTools();
