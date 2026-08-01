(function () {
  "use strict";

  if (typeof window.sidebarCollapsed === "undefined") {
    window.sidebarCollapsed = false;
  }

  const UI = window.ESFEUI = window.ESFEUI || {};
  UI.instances = UI.instances || { charts: new Map() };

  UI.toast = function (detail) {
    const data = typeof detail === "string" ? { message: detail } : (detail || {});
    const region = document.getElementById("ui-toast-region");
    if (!region || !data.message) return;
    const tone = ["info", "success", "warning", "danger"].includes(data.tone) ? data.tone : "info";
    const colors = {
      info: ["border-ui-info/30", "bg-ui-info"],
      success: ["border-ui-success/30", "bg-ui-success"],
      warning: ["border-ui-warning/30", "bg-ui-warning"],
      danger: ["border-ui-danger/30", "bg-ui-danger"]
    };
    const toast = document.createElement("div");
    toast.className = `pointer-events-auto flex items-start gap-3 rounded-ui-card border ${colors[tone][0]} bg-ui-surface p-4 shadow-ui-dropdown`;
    toast.setAttribute("role", tone === "danger" ? "alert" : "status");
    toast.innerHTML = `<span class="mt-1 h-2.5 w-2.5 shrink-0 rounded-ui-badge ${colors[tone][1]}"></span><p class="min-w-0 flex-1 break-words text-sm text-ui-text"></p><button type="button" class="grid h-8 w-8 place-items-center rounded-ui-button hover:bg-ui-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ui-focus" aria-label="Fermer"><span aria-hidden="true">&times;</span></button>`;
    toast.querySelector("p").textContent = data.message;
    const remove = () => toast.remove();
    toast.querySelector("button").addEventListener("click", remove);
    let timer = window.setTimeout(remove, Number(data.duration) || 4500);
    toast.addEventListener("mouseenter", () => window.clearTimeout(timer));
    toast.addEventListener("mouseleave", () => { timer = window.setTimeout(remove, 1800); });
    region.prepend(toast);
  };

  UI.charts = UI.charts || {};
  UI.charts.render = function (root) {
    if (!window.Chart) return;
    (root || document).querySelectorAll("[data-ui-chart]").forEach((canvas) => {
      const existing = UI.instances.charts.get(canvas.id);
      if (existing) existing.destroy();
      try {
        const config = JSON.parse(canvas.dataset.uiChart || "{}");
        const styles = getComputedStyle(document.documentElement);
        const chartColors = {
          "ui-primary": styles.getPropertyValue("--ui-chart-primary").trim() || styles.color,
          "ui-primary-soft": styles.getPropertyValue("--ui-chart-primary-soft").trim() || "transparent"
        };
        (config.data.datasets || []).forEach((dataset) => {
          dataset.borderColor = chartColors[dataset.borderColor] || dataset.borderColor;
          dataset.backgroundColor = chartColors[dataset.backgroundColor] || dataset.backgroundColor;
        });
        config.options = Object.assign({ responsive: true, maintainAspectRatio: false }, config.options || {});
        UI.instances.charts.set(canvas.id, new window.Chart(canvas, config));
      } catch (error) {
        canvas.replaceWith(Object.assign(document.createElement("p"), {
          className: "text-sm text-ui-danger",
          textContent: "Configuration du graphique invalide."
        }));
      }
    });
  };

  UI.init = function (root) {
    const scope = root || document;
    if (window.lucide) window.lucide.createIcons();
    UI.charts.render(scope);
    scope.querySelectorAll("[data-ui-clear-input]:not([data-ui-bound])").forEach((button) => {
      button.dataset.uiBound = "true";
      button.addEventListener("click", () => {
        const input = button.closest("label").querySelector("input");
        if (!input) return;
        input.value = "";
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.focus();
      });
    });
    scope.querySelectorAll("[data-ui-copy]:not([data-ui-bound])").forEach((button) => {
      button.dataset.uiBound = "true";
      button.addEventListener("click", async () => {
        await navigator.clipboard.writeText(button.dataset.uiCopy || "");
        UI.toast({ message: "Copié dans le presse-papiers.", tone: "success" });
      });
    });
  };

  document.addEventListener("alpine:init", () => {
    window.Alpine.data("uiOverlay", (initiallyOpen) => ({
      open: Boolean(initiallyOpen),
      opener: null,
      show() {
        this.opener = document.activeElement;
        this.open = true;
        document.documentElement.classList.add("overflow-hidden");
        this.$nextTick(() => this.$refs.dialog && this.$refs.dialog.focus());
      },
      close() {
        this.open = false;
        document.documentElement.classList.remove("overflow-hidden");
        this.$nextTick(() => this.opener && this.opener.focus());
      },
      trap(event) {
        const nodes = [...this.$refs.dialog.querySelectorAll("a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])")];
        if (!nodes.length) return;
        const first = nodes[0];
        const last = nodes[nodes.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    }));
  });

  document.addEventListener("DOMContentLoaded", () => UI.init(document));
  document.addEventListener("ui:toast", (event) => UI.toast(event.detail));
  document.body.addEventListener("htmx:configRequest", (event) => {
    const token = document.cookie.split("; ").find((item) => item.startsWith("csrftoken="));
    if (token) event.detail.headers["X-CSRFToken"] = decodeURIComponent(token.split("=").slice(1).join("="));
  });
  document.body.addEventListener("htmx:afterSwap", (event) => UI.init(event.detail.target));
  document.body.addEventListener("htmx:afterRequest", (event) => {
    const trigger = event.detail.xhr.getResponseHeader("HX-Trigger");
    if (!trigger) return;
    try {
      const events = JSON.parse(trigger);
      if (events["ui:toast"]) UI.toast(events["ui:toast"]);
    } catch (_) {}
  });
  document.body.addEventListener("htmx:responseError", () => {
    UI.toast({ message: "La requête n'a pas pu aboutir.", tone: "danger" });
  });
})();
