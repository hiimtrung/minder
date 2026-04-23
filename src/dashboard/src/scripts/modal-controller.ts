
type ModalOptions = {
  title?: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  showPrompt?: boolean;
  defaultValue?: string;
  isDanger?: boolean;
};

type ModalResolver = (value: string | boolean | null) => void;

let currentResolver: ModalResolver | null = null;

export function initModalController() {
  const backdrop = document.getElementById("common-modal-backdrop");
  const container = document.getElementById("common-modal-container");
  const cancelBtn = document.getElementById("common-modal-cancel");
  const confirmBtn = document.getElementById("common-modal-confirm");
  const input = document.getElementById("common-modal-input") as HTMLInputElement;

  if (!backdrop || !container || !cancelBtn || !confirmBtn || !input) return;

  const close = (value: string | boolean | null) => {
    backdrop.classList.remove("flex");
    backdrop.classList.add("hidden");
    backdrop.classList.remove("opacity-100");
    backdrop.classList.add("opacity-0");
    container.classList.remove("scale-100", "opacity-100");
    container.classList.add("scale-95", "opacity-0");
    
    if (currentResolver) {
      currentResolver(value);
      currentResolver = null;
    }
  };

  cancelBtn.onclick = () => close(null);
  confirmBtn.onclick = () => {
    const promptArea = document.getElementById("common-modal-prompt-area");
    if (promptArea && !promptArea.classList.contains("hidden")) {
      close(input.value);
    } else {
      close(true);
    }
  };

  // Close on ESC
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !backdrop.classList.contains("hidden")) {
      close(null);
    }
  });
}

export async function showConfirm(message: string, title = "Confirm Action", confirmText = "Confirm"): Promise<boolean> {
  return (await openModal({ message, title, confirmText, showPrompt: false })) === true;
}

export async function showPrompt(message: string, defaultValue = "", title = "Input Required"): Promise<string | null> {
  const result = await openModal({ message, title, showPrompt: true, defaultValue });
  return typeof result === "string" ? result : null;
}

export async function showDangerConfirm(message: string, title = "Danger Zone", confirmText = "Delete"): Promise<boolean> {
  return (await openModal({ message, title, confirmText, isDanger: true, showPrompt: false })) === true;
}

async function openModal(options: ModalOptions): Promise<string | boolean | null> {
  const backdrop = document.getElementById("common-modal-backdrop");
  const container = document.getElementById("common-modal-container");
  const titleEl = document.getElementById("common-modal-title");
  const msgEl = document.getElementById("common-modal-message");
  const promptArea = document.getElementById("common-modal-prompt-area");
  const input = document.getElementById("common-modal-input") as HTMLInputElement;
  const confirmBtn = document.getElementById("common-modal-confirm");
  const cancelBtn = document.getElementById("common-modal-cancel");

  if (!backdrop || !container || !titleEl || !msgEl || !promptArea || !input || !confirmBtn || !cancelBtn) {
    // Fallback to native if modal not in DOM
    if (options.showPrompt) return window.prompt(options.message, options.defaultValue);
    return window.confirm(options.message);
  }

  titleEl.textContent = options.title || "Modal";
  msgEl.textContent = options.message;
  confirmBtn.textContent = options.confirmText || "Confirm";
  cancelBtn.textContent = options.cancelText || "Cancel";

  if (options.showPrompt) {
    promptArea.classList.remove("hidden");
    input.value = options.defaultValue || "";
    setTimeout(() => input.focus(), 100);
  } else {
    promptArea.classList.add("hidden");
  }

  if (options.isDanger) {
    confirmBtn.classList.remove("bg-stone-900", "hover:bg-stone-800");
    confirmBtn.classList.add("bg-red-600", "hover:bg-red-700");
  } else {
    confirmBtn.classList.add("bg-stone-900", "hover:bg-stone-800");
    confirmBtn.classList.remove("bg-red-600", "hover:bg-red-700");
  }

  backdrop.classList.remove("hidden");
  backdrop.classList.add("flex");
  
  // Force reflow for transitions
  void backdrop.offsetWidth;
  
  backdrop.classList.remove("opacity-0");
  backdrop.classList.add("opacity-100");
  container.classList.remove("scale-95", "opacity-0");
  container.classList.add("scale-100", "opacity-100");

  return new Promise((resolve) => {
    currentResolver = resolve;
  });
}
