import { escapeHtml } from "./ui-utils";

export const snippetTitles: Record<string, string> = {
  codex: "OpenAI Codex",
  vscode: "VS Code / GitHub Copilot",
  copilot_cli: "GitHub Copilot CLI",
  antigravity: "Google Antigravity",
  cursor: "Cursor",
  claude_code: "Claude Code",
};

export type SnippetDoc = {
  label: string;
  href: string;
};

export type SnippetVariant = {
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
          tools: ["*"],
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

export const buildSnippetVariants = (
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
          docs: docsByTarget["antigravity"] ?? [],
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
          docs: docsByTarget["antigravity"] ?? [],
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

export const renderSnippetGuide = (variant: SnippetVariant): string => {
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

export const ideInstructions: Array<{
  id: string;
  title: string;
  filename: string;
  content: string;
}> = [
  {
    id: "claude_code",
    title: "Claude Code",
    filename: "CLAUDE.md",
    content: [
      "## Minder MCP Integration",
      "",
      "This project uses Minder for persistent AI context. Minder MCP tools are available in this workspace.",
      "",
      "### Session continuity",
      "Create a named session at the start of each significant task and save state before /compact:",
      "- `minder_session_create` — create a named session",
      "- `minder_session_save` — checkpoint work state (run before /compact)",
      "- `minder_session_restore` — load a session by ID",
      "- `minder_session_find` — find a session by name (primary recovery tool)",
      "- `minder_session_context` — update branch and open-file context",
      "",
      "### Memory",
      "- `minder_memory_store` — store a persistent fact or decision",
      "- `minder_memory_recall` — retrieve a stored fact",
      "- `minder_memory_list` — list stored memories",
      "",
      "### Code intelligence",
      "- `minder_search_code` — search code by symbol or concept",
      "- `minder_search_errors` — look up past error patterns",
      "- `minder_query` — query the repository knowledge graph",
      "- `minder_find_impact` — find what a change might affect",
      "",
      "Always create a session at the start of a significant task. Save state before /compact or switching machines.",
    ].join("\n"),
  },
  {
    id: "vscode",
    title: "VS Code / GitHub Copilot",
    filename: ".github/copilot-instructions.md",
    content: [
      "## Minder MCP Integration",
      "",
      "This project uses Minder for persistent AI context. Minder MCP tools are available when connected.",
      "",
      "### Session continuity",
      "- minder_session_create — create a named session at the start of each project",
      "- minder_session_save — checkpoint work after each significant task",
      "- minder_session_restore — load a session by ID",
      "- minder_session_find — find a session by name",
      "",
      "### Memory",
      "- minder_memory_store / minder_memory_recall / minder_memory_list — persistent facts",
      "",
      "### Code intelligence",
      "- minder_search_code — search code by symbol or concept",
      "- minder_search_errors — look up past error patterns",
      "- minder_query — query the repository knowledge graph",
      "- minder_find_impact — find what a change might affect",
    ].join("\n"),
  },
  {
    id: "cursor",
    title: "Cursor",
    filename: ".cursorrules",
    content: [
      "# Minder MCP Integration",
      "",
      "This project uses Minder for persistent AI context. Available MCP tools:",
      "",
      "Session continuity:",
      "- minder_session_create / minder_session_save / minder_session_restore — checkpoint work",
      "- minder_session_find — recover a session by name",
      "",
      "Memory:",
      "- minder_memory_store / minder_memory_recall / minder_memory_list",
      "",
      "Code intelligence:",
      "- minder_search_code / minder_search_errors / minder_query / minder_find_impact",
      "",
      "Always create a named session at the start of a significant task.",
    ].join("\n"),
  },
];
