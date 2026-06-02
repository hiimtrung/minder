import { getDashboardBootstrapState, loginAdmin } from "../lib/api/admin";

const loginForm = document.querySelector("#login-form");
const usernameInput = document.querySelector(
  "#login-username",
) as HTMLInputElement | null;
const passwordInput = document.querySelector(
  "#login-password",
) as HTMLInputElement | null;
const loginStatus = document.querySelector("#login-status");

const apiKeyForm = document.querySelector("#apikey-form");
const apiKeyInput = document.querySelector(
  "#api-key",
) as HTMLInputElement | null;
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
  window.location.href = "/dashboard";
};

// ---------------------------------------------------------------------------
// Primary login: username + password
// ---------------------------------------------------------------------------

loginForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const username = usernameInput?.value.trim() ?? "";
  const password = passwordInput?.value ?? "";

  if (!username || !password) {
    if (loginStatus)
      loginStatus.textContent = "Username and password are required.";
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

// ---------------------------------------------------------------------------
// Collapsible & Diagnostics Console Implementation
// ---------------------------------------------------------------------------

const diagToggle = document.querySelector("#diagnostics-toggle");
const diagPanel = document.querySelector("#diagnostics-panel");
const diagChevron = document.querySelector("#diagnostics-chevron");
const statusDot = document.querySelector("#diagnostics-status-dot");
const summaryText = document.querySelector("#diagnostics-summary-text");

const feOrigin = document.querySelector("#diag-fe-origin");
const beUrlText = document.querySelector("#diag-be-url");
const pingText = document.querySelector("#diag-ping");
const pyEnvText = document.querySelector("#diag-py-env");

const feViewport = document.querySelector("#fe-terminal-viewport");
const beViewport = document.querySelector("#be-terminal-viewport");
const beStatusIndicator = document.querySelector("#be-status-indicator");

const clearBtn = document.querySelector("#diagnostics-clear");
const copyBtn = document.querySelector("#diagnostics-copy");

// Log Buffers for clipboard report
let frontendLogBuffer: string[] = ["[Info] Diagnostics console initialized."];
let backendLogBuffer: string[] = [];
const seenBackendLogs = new Set<string>();

// Helper to format timestamps
function getTimestamp() {
  const now = new Date();
  return now.toTimeString().split(" ")[0];
}

// Append log to viewport and scroll to bottom
function appendLog(viewport: Element | null, text: string, type: "info" | "warn" | "error" | "log" | "system" = "log") {
  if (!viewport) return;
  const line = document.createElement("div");
  const time = getTimestamp();
  
  if (type === "error") {
    line.className = "text-rose-400";
    line.textContent = `[${time}] [Error] ${text}`;
  } else if (type === "warn") {
    line.className = "text-amber-300";
    line.textContent = `[${time}] [Warn] ${text}`;
  } else if (type === "system") {
    line.className = "text-stone-500";
    line.textContent = `[${time}] [System] ${text}`;
  } else {
    line.className = "text-stone-350";
    line.textContent = `[${time}] ${text}`;
  }
  
  viewport.appendChild(line);
  viewport.scrollTop = viewport.scrollHeight;
}

// Intercept Frontend Console
const originalLog = console.log;
const originalWarn = console.warn;
const originalError = console.error;

console.log = (...args) => {
  originalLog.apply(console, args);
  const msg = args.map(a => typeof a === "object" ? JSON.stringify(a) : String(a)).join(" ");
  frontendLogBuffer.push(`[${getTimestamp()}] [Log] ${msg}`);
  appendLog(feViewport, msg, "log");
};

console.warn = (...args) => {
  originalWarn.apply(console, args);
  const msg = args.map(a => typeof a === "object" ? JSON.stringify(a) : String(a)).join(" ");
  frontendLogBuffer.push(`[${getTimestamp()}] [Warn] ${msg}`);
  appendLog(feViewport, msg, "warn");
};

console.error = (...args) => {
  originalError.apply(console, args);
  const msg = args.map(a => typeof a === "object" ? JSON.stringify(a) : String(a)).join(" ");
  frontendLogBuffer.push(`[${getTimestamp()}] [Error] ${msg}`);
  appendLog(feViewport, msg, "error");
};

// Capture uncaught window exceptions
window.addEventListener("error", (event) => {
  const errorMsg = `${event.message} at ${event.filename}:${event.lineno}:${event.colno}`;
  frontendLogBuffer.push(`[${getTimestamp()}] [Uncaught Exception] ${errorMsg}`);
  appendLog(feViewport, `Uncaught Exception: ${errorMsg}`, "error");
});

window.addEventListener("unhandledrejection", (event) => {
  const errorMsg = `Unhandled Promise Rejection: ${event.reason}`;
  frontendLogBuffer.push(`[${getTimestamp()}] [Unhandled Rejection] ${errorMsg}`);
  appendLog(feViewport, errorMsg, "error");
});

// Collapsible State Toggle
let isExpanded = false;
diagToggle?.addEventListener("click", () => {
  isExpanded = !isExpanded;
  diagToggle.setAttribute("aria-expanded", String(isExpanded));
  if (isExpanded) {
    diagPanel?.classList.remove("hidden");
    diagChevron?.classList.add("rotate-180");
  } else {
    diagPanel?.classList.add("hidden");
    diagChevron?.classList.remove("rotate-180");
  }
});

// Set static info
if (feOrigin) {
  feOrigin.textContent = window.location.origin;
}

// Polling function for unauthenticated diagnostics
async function pollDiagnostics() {
  const startTime = performance.now();
  try {
    const response = await fetch("/v1/admin/diagnostics/logs", {
      headers: { "Cache-Control": "no-cache" }
    });
    const latency = Math.round(performance.now() - startTime);

    if (!response.ok) {
      throw new Error(`Server returned HTTP ${response.status}`);
    }

    const data = await response.json() as {
      logs: Array<{ timestamp: string; level: string; logger: string; message: string }>;
      environment: {
        python_version: string;
        platform: string;
        host: string;
        port: number;
        transport: string;
      };
    };

    // Update Connection Parameters UI
    if (beUrlText) {
      beUrlText.textContent = `${window.location.protocol}//${data.environment.host}:${data.environment.port}`;
    }
    if (pingText) {
      pingText.textContent = `${latency} ms`;
    }
    if (pyEnvText) {
      pyEnvText.textContent = data.environment.python_version.split(" ")[0];
    }

    // Check for origin or port mismatches
    const fePort = window.location.port || (window.location.protocol === "https:" ? "443" : "80");
    const bePort = String(data.environment.port);
    const isPortMismatch = fePort !== bePort && window.location.hostname === "localhost" && data.environment.host === "127.0.0.1";

    if (isPortMismatch) {
      if (statusDot) {
        statusDot.className = "relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500";
      }
      if (summaryText) {
        summaryText.textContent = `Port Mismatch (FE: ${fePort}, BE: ${bePort})`;
        summaryText.className = "text-xs text-amber-600 font-semibold";
      }
      if (beStatusIndicator) {
        beStatusIndicator.className = "flex h-1.5 w-1.5 rounded-full bg-amber-500";
      }
    } else {
      if (statusDot) {
        statusDot.className = "relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500";
      }
      if (summaryText) {
        summaryText.textContent = `Connected (${latency}ms)`;
        summaryText.className = "text-xs text-emerald-600 font-semibold";
      }
      if (beStatusIndicator) {
        beStatusIndicator.className = "flex h-1.5 w-1.5 rounded-full bg-emerald-500";
      }
    }

    // Process new logs
    if (data.logs && Array.isArray(data.logs)) {
      data.logs.forEach(log => {
        const logId = `${log.timestamp}-${log.level}-${log.message}`;
        if (!seenBackendLogs.has(logId)) {
          seenBackendLogs.add(logId);
          const formatted = `[${log.level}] [${log.logger}] ${log.message}`;
          backendLogBuffer.push(`[${log.timestamp}] ${formatted}`);
          
          let logType: "info" | "warn" | "error" | "log" = "log";
          if (log.level === "ERROR" || log.level === "CRITICAL") logType = "error";
          else if (log.level === "WARNING") logType = "warn";
          
          appendLog(beViewport, formatted, logType);
        }
      });
    }

  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : "Network error";
    
    // Update UI for connection failure
    if (pingText) pingText.textContent = "Offline";
    if (beUrlText) beUrlText.textContent = "Unreachable";
    if (pyEnvText) pyEnvText.textContent = "N/A";
    
    if (statusDot) {
      statusDot.className = "relative inline-flex rounded-full h-2.5 w-2.5 bg-rose-500";
    }
    if (summaryText) {
      summaryText.textContent = `Offline - ${errorMsg}`;
      summaryText.className = "text-xs text-rose-600 font-semibold";
    }
    if (beStatusIndicator) {
      beStatusIndicator.className = "flex h-1.5 w-1.5 rounded-full bg-rose-500";
    }

    appendLog(beViewport, `Error polling backend diagnostics: ${errorMsg}`, "error");
  }
}

// Start polling immediately and then every 3 seconds
void pollDiagnostics();
window.setInterval(pollDiagnostics, 3000);

// Clear Viewports
clearBtn?.addEventListener("click", () => {
  if (feViewport) feViewport.innerHTML = '<div class="text-stone-500">[Info] Viewport cleared. Intercepting new logs...</div>';
  if (beViewport) beViewport.innerHTML = '<div class="text-stone-500">[Info] Viewport cleared. Waiting for new log stream...</div>';
  frontendLogBuffer = [];
  backendLogBuffer = [];
  seenBackendLogs.clear();
});

// Copy Diagnostics Report
copyBtn?.addEventListener("click", async () => {
  const origin = window.location.origin;
  const beUrl = beUrlText?.textContent || "N/A";
  const ping = pingText?.textContent || "N/A";
  const env = pyEnvText?.textContent || "N/A";

  const report = `# Minder Login Page Diagnostics Report
Generated at: ${new Date().toLocaleString()}

## Connection Information
- **Frontend Origin:** ${origin}
- **Backend Base URL:** ${beUrl}
- **Ping Latency:** ${ping}
- **Python Version:** ${env}

## Frontend Console Logs
\`\`\`text
${frontendLogBuffer.length > 0 ? frontendLogBuffer.join("\n") : "No frontend logs recorded."}
\`\`\`

## Python Backend Logs
\`\`\`text
${backendLogBuffer.length > 0 ? backendLogBuffer.join("\n") : "No backend logs recorded."}
\`\`\`
`;

  try {
    await navigator.clipboard.writeText(report);
    alert("Diagnostics report copied to clipboard!");
  } catch (err) {
    alert(`Failed to copy report: ${err}`);
  }
});

