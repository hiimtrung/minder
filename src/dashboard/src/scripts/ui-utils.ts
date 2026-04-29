/**
 * Shared UI utilities for the Minder dashboard.
 */

/** Get element by ID with type safety */
export function getEl<T extends HTMLElement>(id: string): T | null {
  return document.getElementById(id) as T | null;
}

/** Set text content of an element safely */
export function setText(el: Element | null, text: string): void {
  if (el) el.textContent = text;
}

/** Escape HTML strings for safe insertion into templates */
export function escapeHtml(v: string): string {
  if (!v) return "";
  const div = document.createElement("div");
  div.textContent = v;
  return div.innerHTML;
}

/** Toggle full-width layout for graph-heavy tabs */
export function setGraphFullWidth(enabled: boolean): void {
  const shell = document.querySelector(".shell-main-grid");
  if (!shell) return;
  if (enabled) {
    shell.classList.add("shell-main-grid-wide");
  } else {
    shell.classList.remove("shell-main-grid-wide");
  }
}

/** Generic tab switcher logic */
export function switchTab(
  tabId: string,
  options?: {
    onSwitch?: (id: string) => void;
    isWide?: (id: string) => boolean;
  }
): void {
  document.querySelectorAll("[data-tab-btn]").forEach((b) => {
    b.classList.remove("tab-btn-active");
  });
  document.querySelectorAll("[data-tab-panel]").forEach((p) => {
    p.classList.add("hidden");
  });

  const btn = document.querySelector(`[data-tab-btn="${tabId}"]`);
  if (btn) btn.classList.add("tab-btn-active");

  const panel = document.querySelector(`[data-tab-panel="${tabId}"]`);
  if (panel) panel.classList.remove("hidden");

  // Handle wide layout if applicable
  if (options?.isWide) {
    setGraphFullWidth(options.isWide(tabId));
  }

  // Trigger optional callback (e.g. for resizing renderers)
  if (options?.onSwitch) {
    options.onSwitch(tabId);
  }
}

/** Show a temporary toast message */
export function showToast(
  message: string,
  tone: "success" | "danger" | "default" = "default"
): void {
  const toastRegion = document.querySelector("#dashboard-toast-region");
  if (!(toastRegion instanceof HTMLElement)) return;

  const toast = document.createElement("div");
  toast.className =
    "pointer-events-auto rounded-2xl border px-4 py-3 text-sm shadow-[0_18px_40px_rgba(28,25,23,0.12)] backdrop-blur transition";

  if (tone === "success") {
    toast.classList.add(
      "border-emerald-200",
      "bg-emerald-50/95",
      "text-emerald-900"
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
}
