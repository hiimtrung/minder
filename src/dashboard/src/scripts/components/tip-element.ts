// Client-side reusable tip component that portals the tooltip panel into
// `document.body` to avoid being clipped by ancestor overflow.

class MinderTip extends HTMLElement {
  connectedCallback() {
    if ((this as any)._initialized) return;
    (this as any)._initialized = true;

    // Prefer explicit `description` attribute (server-rendered), fall back
    // to textContent if present. Avoid consuming full HTML fallback markup.
    const attrDesc = String(this.getAttribute("description") || "").trim();
    const textDesc = (this.textContent || "").trim();
    const raw = attrDesc || textDesc || "";

    if (!raw) {
      this.remove();
      return;
    }

    this.innerHTML = "";

    const wrapper = document.createElement("div");
    wrapper.className = "u-tip-host";

    const span = document.createElement("span");
    span.className = "u-tip";

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "u-tip-btn";
    btn.tabIndex = 0;
    btn.setAttribute("aria-label", "More info");
    btn.textContent = "i";

    span.appendChild(btn);
    wrapper.appendChild(span);
    this.appendChild(wrapper);

    const panel = document.createElement("div");
    const panelId = "u-tip-" + Math.random().toString(36).slice(2, 9);
    panel.id = panelId;
    panel.className = "u-tip-panel u-tip-panel-floating";
    panel.setAttribute("role", "tooltip");
    panel.textContent = raw;
    document.body.appendChild(panel);

    btn.setAttribute("aria-describedby", panelId);

    const positionPanel = () => {
      const rect = btn.getBoundingClientRect();
      const pad = 8;
      const panelRect = panel.getBoundingClientRect();
      let left = rect.left;
      let top = rect.bottom + pad;

      if (left + panelRect.width > window.innerWidth - 8) {
        left = Math.max(8, window.innerWidth - panelRect.width - 8);
      }
      if (top + panelRect.height > window.innerHeight - 8) {
        top = rect.top - panelRect.height - pad;
      }
      left = Math.max(8, left);
      top = Math.max(8, top);

      panel.style.left = `${Math.round(left)}px`;
      panel.style.top = `${Math.round(top)}px`;
    };

    const show = () => {
      // compute highest z-index on the page for positioned elements and
      // place tooltip above it to avoid being visually covered by headers
      try {
        let maxZ = 0;
        const els = Array.from(
          document.querySelectorAll<HTMLElement>("body *"),
        );
        for (const el of els) {
          const s = window.getComputedStyle(el);
          if (!s) continue;
          const pos = s.position;
          if (
            pos === "fixed" ||
            pos === "sticky" ||
            pos === "absolute" ||
            pos === "relative"
          ) {
            const z = parseInt(s.zIndex || "0", 10);
            if (!Number.isNaN(z)) maxZ = Math.max(maxZ, z);
          }
        }
        panel.style.zIndex = String(Math.max(2147483647, maxZ + 1));
      } catch (e) {
        panel.style.zIndex = "2147483647";
      }
      panel.style.display = "block";
      panel.style.visibility = "visible";
      panel.style.opacity = "1";
      panel.style.pointerEvents = "auto";
      positionPanel();
    };
    const hide = () => {
      panel.style.display = "none";
      panel.style.visibility = "hidden";
      panel.style.opacity = "0";
      panel.style.pointerEvents = "none";
    };

    btn.addEventListener("mouseenter", show);
    btn.addEventListener("focus", show);
    btn.addEventListener("mouseleave", hide);
    btn.addEventListener("blur", hide);

    const onScrollResize = () => {
      if (panel.style.display === "block") positionPanel();
    };
    window.addEventListener("scroll", onScrollResize, true);
    window.addEventListener("resize", onScrollResize);

    (this as any)._cleanup = () => {
      try {
        panel.remove();
      } catch {}
      window.removeEventListener("scroll", onScrollResize, true);
      window.removeEventListener("resize", onScrollResize);
    };
  }

  disconnectedCallback() {
    if ((this as any)._cleanup) (this as any)._cleanup();
  }
}

if (!customElements.get("minder-tip")) {
  customElements.define("minder-tip", MinderTip);
}

export {};
