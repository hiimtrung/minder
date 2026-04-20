import {
  listRepositories,
  listTools,
  listWorkflows,
  queryRuntimeStream,
  type RepositoryPayload,
  type RuntimeQueryPayload,
  type RuntimeQueryStreamEvent,
  type ToolInfo,
  type WorkflowPayload,
} from "../lib/api/admin";

const formEl = document.querySelector(
  "#runtime-chat-form",
) as HTMLFormElement | null;
const repositoryEl = document.querySelector(
  "#runtime-chat-repository",
) as HTMLSelectElement | null;
const workflowEl = document.querySelector(
  "#runtime-chat-workflow",
) as HTMLSelectElement | null;
const attemptsEl = document.querySelector(
  "#runtime-chat-max-attempts",
) as HTMLSelectElement | null;
const queryEl = document.querySelector(
  "#runtime-chat-query",
) as HTMLTextAreaElement | null;
const statusEl = document.querySelector("#runtime-chat-status");
const toolsEl = document.querySelector("#runtime-chat-tools");
const threadEl = document.querySelector("#runtime-chat-thread");
const emptyEl = document.querySelector("#runtime-chat-empty");
const sourcesEl = document.querySelector("#runtime-chat-sources");
const transitionsEl = document.querySelector("#runtime-chat-transitions");
const actionsEl = document.querySelector("#runtime-chat-actions");
const summaryEl = document.querySelector("#runtime-chat-summary");
const engineEl = document.querySelector("#runtime-chat-engine");
const warningEl = document.querySelector("#runtime-chat-warning");
const submitEl = document.querySelector(
  "#runtime-chat-submit",
) as HTMLButtonElement | null;

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  meta?: {
    provider?: string | null;
    model?: string | null;
    repositoryName?: string | null;
    warning?: string | null;
  };
};

let repositories: RepositoryPayload[] = [];
let workflows: WorkflowPayload[] = [];
let messages: ChatMessage[] = [];
let activeAssistantMessageIndex: number | null = null;
const QUERY_MIN_ROWS = 2;
const QUERY_MAX_ROWS = 4;

const syncQueryHeight = () => {
  if (!(queryEl instanceof HTMLTextAreaElement)) return;

  queryEl.style.height = "auto";
  const styles = window.getComputedStyle(queryEl);
  const lineHeight = Number.parseFloat(styles.lineHeight) || 22;
  const borderTop = Number.parseFloat(styles.borderTopWidth) || 0;
  const borderBottom = Number.parseFloat(styles.borderBottomWidth) || 0;
  const paddingTop = Number.parseFloat(styles.paddingTop) || 0;
  const paddingBottom = Number.parseFloat(styles.paddingBottom) || 0;
  const chromeHeight =
    borderTop + borderBottom + paddingTop + paddingBottom + 0.5;
  const minHeight = lineHeight * QUERY_MIN_ROWS + chromeHeight;
  const maxHeight = lineHeight * QUERY_MAX_ROWS + chromeHeight;
  const nextHeight = Math.min(
    Math.max(queryEl.scrollHeight, minHeight),
    maxHeight,
  );

  queryEl.style.height = `${nextHeight}px`;
  queryEl.style.overflowY =
    queryEl.scrollHeight > maxHeight ? "auto" : "hidden";
};

const escapeHtml = (value: string): string =>
  value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

const jsonPreview = (value: unknown): string => {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

const setStatus = (
  message: string,
  tone: "default" | "success" | "danger" = "default",
) => {
  if (!(statusEl instanceof HTMLElement)) return;
  statusEl.textContent = message;
  statusEl.className = "u-status";
  if (tone === "success") statusEl.classList.add("u-status-success");
  if (tone === "danger") statusEl.classList.add("u-status-danger");
};

const renderThread = () => {
  if (!(threadEl instanceof HTMLElement)) return;
  if (!messages.length) {
    emptyEl?.classList.remove("hidden");
    return;
  }

  emptyEl?.classList.add("hidden");
  threadEl.innerHTML = messages
    .map((message) => {
      const isAssistant = message.role === "assistant";
      const meta = [
        message.meta?.repositoryName,
        message.meta?.provider,
        message.meta?.model,
      ]
        .filter((item): item is string => Boolean(item && item.trim()))
        .join(" · ");
      return `
        <article class="runtime-chat-bubble ${isAssistant ? "assistant" : "user"}">
          <div class="runtime-chat-bubble-label">${isAssistant ? "Minder runtime" : "You"}</div>
          <div class="runtime-chat-bubble-body">${escapeHtml(message.content)}</div>
          ${meta ? `<div class="runtime-chat-bubble-meta">${escapeHtml(meta)}</div>` : ""}
          ${message.meta?.warning ? `<div class="runtime-chat-bubble-warning">${escapeHtml(message.meta.warning)}</div>` : ""}
        </article>
      `;
    })
    .join("");

  threadEl.scrollTop = threadEl.scrollHeight;
};

const setWarning = (message: string | null) => {
  if (!(warningEl instanceof HTMLElement)) return;
  if (!message) {
    warningEl.textContent = "";
    warningEl.classList.add("hidden");
    return;
  }
  warningEl.textContent = message;
  warningEl.classList.remove("hidden");
};

const renderTools = (tools: ToolInfo[]) => {
  if (!(toolsEl instanceof HTMLElement)) return;
  if (!tools.length) {
    toolsEl.innerHTML =
      '<div class="u-placeholder-card">No tools available.</div>';
    return;
  }
  toolsEl.innerHTML = tools
    .map(
      (tool) => `
        <article class="rounded-2xl border border-stone-200 bg-white px-4 py-3">
          <p class="text-sm font-medium text-stone-900">${escapeHtml(tool.name)}</p>
          <p class="mt-1 text-sm leading-6 text-stone-600">${escapeHtml(tool.description)}</p>
        </article>
      `,
    )
    .join("");
};

const renderRepositoryOptions = (items: RepositoryPayload[]) => {
  if (!(repositoryEl instanceof HTMLSelectElement)) return;
  repositoryEl.innerHTML = [
    '<option value="">No repository scope</option>',
    ...items.map(
      (repository) =>
        `<option value="${escapeHtml(repository.id)}">${escapeHtml(repository.name)}${repository.path ? ` · ${escapeHtml(repository.path)}` : ""}</option>`,
    ),
  ].join("");
};

const renderWorkflowOptions = (items: WorkflowPayload[]) => {
  if (!(workflowEl instanceof HTMLSelectElement)) return;
  workflowEl.innerHTML = [
    '<option value="">Use repository workflow</option>',
    ...items.map(
      (workflow) =>
        `<option value="${escapeHtml(workflow.name)}">${escapeHtml(workflow.name)}</option>`,
    ),
  ].join("");
};

const renderResult = (payload: RuntimeQueryPayload) => {
  if (typeof activeAssistantMessageIndex === "number") {
    messages[activeAssistantMessageIndex] = {
      role: "assistant",
      content: payload.answer || "No answer returned.",
      meta: {
        provider: payload.provider,
        model: payload.model,
        repositoryName: payload.repository.name,
        warning: payload.answer_warning,
      },
    };
    activeAssistantMessageIndex = null;
  } else {
    messages.push({
      role: "assistant",
      content: payload.answer || "No answer returned.",
      meta: {
        provider: payload.provider,
        model: payload.model,
        repositoryName: payload.repository.name,
        warning: payload.answer_warning,
      },
    });
  }
  renderThread();
  setWarning(payload.answer_warning);

  if (engineEl instanceof HTMLElement) {
    const parts = [payload.provider, payload.model, payload.runtime]
      .filter((item): item is string => Boolean(item && String(item).trim()))
      .join(" · ");
    engineEl.textContent = parts;
  }

  if (sourcesEl instanceof HTMLElement) {
    if (!payload.sources?.length) {
      sourcesEl.innerHTML =
        '<div class="text-sm text-stone-500">No sources returned.</div>';
    } else {
      sourcesEl.innerHTML = payload.sources
        .map((source) => {
          const path = String(source.path ?? source.title ?? "Unknown source");
          const score =
            typeof source.score === "number" ? source.score.toFixed(2) : null;
          return `
            <article class="rounded-2xl border border-stone-200 bg-stone-50 px-4 py-3">
              <p class="text-sm font-medium text-stone-900 break-words">${escapeHtml(path)}</p>
              ${score ? `<p class="mt-1 text-xs text-stone-500">score ${escapeHtml(score)}</p>` : ""}
              <pre class="snippet-pre mt-3 text-xs">${escapeHtml(jsonPreview(source))}</pre>
            </article>
          `;
        })
        .join("");
    }
  }

  if (transitionsEl instanceof HTMLElement) {
    if (!payload.transition_log?.length) {
      transitionsEl.innerHTML =
        '<div class="text-sm text-stone-500">No transition log returned.</div>';
    } else {
      transitionsEl.innerHTML = payload.transition_log
        .map(
          (item) => `
            <article class="rounded-2xl border border-stone-200 bg-white px-4 py-3">
              <pre class="snippet-pre text-xs">${escapeHtml(jsonPreview(item))}</pre>
            </article>
          `,
        )
        .join("");
    }
  }

  if (actionsEl instanceof HTMLElement) {
    if (!payload.agent_actions?.length) {
      actionsEl.innerHTML =
        '<div class="text-sm text-stone-500">No tool actions executed.</div>';
    } else {
      actionsEl.innerHTML = payload.agent_actions
        .map(
          (action) => `
            <article class="rounded-2xl border border-stone-200 bg-white px-4 py-3">
              <p class="text-sm font-medium text-stone-900">${escapeHtml(String(action.tool ?? "unknown_tool"))}</p>
              <p class="mt-1 text-xs text-stone-500">${escapeHtml(String(action.mode ?? "unknown"))} · ${escapeHtml(String(action.status ?? "unknown"))}</p>
              <pre class="snippet-pre mt-3 text-xs">${escapeHtml(jsonPreview(action))}</pre>
            </article>
          `,
        )
        .join("");
    }
  }

  if (summaryEl instanceof HTMLElement) {
    summaryEl.innerHTML = [
      ["Repository", payload.repository.name || payload.repository.id],
      ["Repository scope", payload.repository.id ? "selected" : "none"],
      ["Path", payload.repository.path || "-"],
      ["Orchestration", payload.orchestration_runtime || "-"],
      ["Edge", payload.edge || "-"],
      ["Agent actions", payload.agent_actions?.length ?? 0],
      ["Answer sanitized", payload.answer_sanitized ? "yes" : "no"],
      ["Guard", payload.guard_result ? "returned" : "-"],
      ["Verification", payload.verification_result ? "returned" : "-"],
      ["Cross repo graph", payload.cross_repo_graph ? "returned" : "-"],
    ]
      .map(
        ([label, value]) => `
          <div class="rounded-2xl border border-stone-200 bg-white px-3 py-2">
            <p class="text-[11px] font-semibold uppercase tracking-[0.16em] text-stone-500">${escapeHtml(String(label))}</p>
            <p class="mt-1 break-words text-sm text-stone-800">${escapeHtml(String(value))}</p>
          </div>
        `,
      )
      .join("");
  }
};

const beginAssistantStream = (repositoryName: string | null) => {
  messages.push({
    role: "assistant",
    content: "",
    meta: {
      repositoryName,
    },
  });
  activeAssistantMessageIndex = messages.length - 1;
  renderThread();
};

const appendAssistantDelta = (delta: string) => {
  if (typeof activeAssistantMessageIndex !== "number") return;
  const current = messages[activeAssistantMessageIndex];
  messages[activeAssistantMessageIndex] = {
    ...current,
    content: `${current.content}${delta}`,
  };
  renderThread();
};

const markRetry = (reason: string) => {
  if (typeof activeAssistantMessageIndex !== "number") return;
  const current = messages[activeAssistantMessageIndex];
  messages[activeAssistantMessageIndex] = {
    ...current,
    content: "",
    meta: {
      ...current.meta,
      warning: `Retrying answer generation: ${reason}`,
    },
  };
  renderThread();
};

const setSubmitting = (isSubmitting: boolean) => {
  if (submitEl instanceof HTMLButtonElement) {
    submitEl.disabled = isSubmitting;
    submitEl.textContent = isSubmitting
      ? "Streaming answer..."
      : "Ask local runtime";
  }
  if (queryEl instanceof HTMLTextAreaElement) {
    queryEl.disabled = isSubmitting;
  }
};

const handleStreamEvent = (event: RuntimeQueryStreamEvent) => {
  if (event.type === "attempt") {
    setStatus(`Generating answer (attempt ${event.attempt})...`);
    return;
  }
  if (event.type === "chunk") {
    appendAssistantDelta(event.delta);
    return;
  }
  if (event.type === "retry") {
    setStatus(`Retrying answer after ${event.edge}...`);
    markRetry(event.reason);
    return;
  }
  if (event.type === "final") {
    renderResult(event.payload);
    setStatus("Runtime query completed.", "success");
    return;
  }
  if (event.type === "error") {
    throw new Error(event.error);
  }
};

const loadBootstrap = async () => {
  const [repositoryPayload, toolPayload, workflowPayload] = await Promise.all([
    listRepositories(),
    listTools(),
    listWorkflows(),
  ]);
  repositories = repositoryPayload.repositories;
  workflows = workflowPayload.workflows;
  renderRepositoryOptions(repositories);
  renderWorkflowOptions(workflows);
  renderTools(toolPayload.tools);
};

repositoryEl?.addEventListener("change", () => {
  if (!(workflowEl instanceof HTMLSelectElement)) return;
  const selectedRepository =
    repositories.find((item) => item.id === (repositoryEl.value || "")) ?? null;
  if (!selectedRepository?.workflow_name) {
    workflowEl.value = "";
    return;
  }
  const matched = workflows.find(
    (item) => item.name === selectedRepository.workflow_name,
  );
  workflowEl.value = matched?.name ?? "";
});

formEl?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const repoId = repositoryEl?.value?.trim() ?? "";
  const query = queryEl?.value?.trim() ?? "";
  const maxAttempts = Number(attemptsEl?.value ?? "2") || 2;
  const workflowName = workflowEl?.value.trim() || undefined;
  const selectedRepository =
    repositories.find((item) => item.id === repoId) ?? null;
  if (!query) {
    setStatus("Question is required.", "danger");
    return;
  }

  messages.push({
    role: "user",
    content: query,
    meta: {
      repositoryName: selectedRepository?.name ?? null,
    },
  });
  renderThread();
  beginAssistantStream(selectedRepository?.name ?? null);
  setSubmitting(true);
  setStatus("Querying local runtime...");
  try {
    await queryRuntimeStream(
      {
        query,
        repo_id: repoId || undefined,
        workflow_name: workflowName,
        max_attempts: maxAttempts,
      },
      handleStreamEvent,
    );
    if (queryEl instanceof HTMLTextAreaElement) {
      queryEl.value = "";
      syncQueryHeight();
      queryEl.focus();
    }
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Runtime query failed.";
    setStatus(message, "danger");
    setWarning(message);
    if (typeof activeAssistantMessageIndex === "number") {
      const current = messages[activeAssistantMessageIndex];
      messages[activeAssistantMessageIndex] = {
        ...current,
        content: current.content || "Unable to stream a response.",
        meta: {
          ...current.meta,
          warning: message,
        },
      };
      activeAssistantMessageIndex = null;
      renderThread();
    }
  } finally {
    setSubmitting(false);
  }
});

queryEl?.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
    event.preventDefault();
    formEl?.requestSubmit();
  }
});

queryEl?.addEventListener("input", () => {
  syncQueryHeight();
});

document
  .querySelectorAll<HTMLElement>("[data-runtime-chat-suggestion]")
  .forEach((button) => {
    button.addEventListener("click", () => {
      if (!(queryEl instanceof HTMLTextAreaElement)) return;
      queryEl.value = button.dataset.runtimeChatSuggestion ?? "";
      syncQueryHeight();
      queryEl.focus();
    });
  });

void loadBootstrap()
  .then(() => {
    renderThread();
    setStatus("Ask a question. Repository scope is optional.");
    syncQueryHeight();
  })
  .catch((error) => {
    const message =
      error instanceof Error
        ? error.message
        : "Unable to load runtime chat context.";
    setStatus(message, "danger");
    setWarning(message);
    if (toolsEl instanceof HTMLElement) {
      toolsEl.innerHTML = `<div class="u-placeholder-card text-red-700">${escapeHtml(message)}</div>`;
    }
  });
