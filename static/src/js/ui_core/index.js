(function () {
  "use strict";

  if (typeof window.sidebarCollapsed === "undefined") {
    window.sidebarCollapsed = false;
  }

  const UI = window.ESFEUI = window.ESFEUI || {};
  if (UI.coreInitialized) return;
  UI.coreInitialized = true;
  UI.instances = UI.instances || { charts: new Map() };
  UI.toastRecent = UI.toastRecent || new Map();

  // The component is registered inline before Alpine boots, but focus
  // restoration is shared here so every UI Core overlay has one contract.
  UI.overlay = UI.overlay || {
    lockPage() {
      document.documentElement.classList.add("overflow-hidden");
    },
    unlockPage() {
      document.documentElement.classList.remove("overflow-hidden");
    },
    restoreFocus() {
      if (this.opener) this.opener.focus();
    }
  };

  UI.toast = function (detail, fallbackTone = "info") {
    const raw = typeof detail === "string" ? { message: detail } : (detail || {});
    const region = document.getElementById("ui-toast-region");
    const message = String(raw.message || raw.text || "").trim();
    if (!region || !message) return;
    const toneAliases = { error: "danger", neutral: "info" };
    const requestedTone = raw.tone || raw.type || fallbackTone;
    const tone = toneAliases[requestedTone] || requestedTone;
    const normalizedTone = ["info", "success", "warning", "danger"].includes(tone) ? tone : "info";
    const key = `${normalizedTone}:${message}`;
    const now = Date.now();
    const previous = UI.toastRecent.get(key) || 0;
    if (now - previous < 2500) return;
    UI.toastRecent.set(key, now);
    if (UI.toastRecent.size > 80) {
      UI.toastRecent.forEach((seenAt, seenKey) => {
        if (now - seenAt > 10000) UI.toastRecent.delete(seenKey);
      });
    }
    const colors = {
      info: ["border-ui-info/30", "bg-ui-info"],
      success: ["border-ui-success/30", "bg-ui-success"],
      warning: ["border-ui-warning/30", "bg-ui-warning"],
      danger: ["border-ui-danger/30", "bg-ui-danger"]
    };
    const toast = document.createElement("div");
    toast.dataset.uiToast = "true";
    toast.className = `pointer-events-auto flex items-start gap-3 rounded-ui-card border ${colors[normalizedTone][0]} bg-ui-surface p-4 shadow-ui-dropdown`;
    toast.setAttribute("role", normalizedTone === "danger" ? "alert" : "status");
    toast.innerHTML = `<span class="mt-1 h-2.5 w-2.5 shrink-0 rounded-ui-badge ${colors[normalizedTone][1]}"></span><p class="min-w-0 flex-1 break-words text-sm text-ui-text"></p><button type="button" class="grid h-8 w-8 place-items-center rounded-ui-button hover:bg-ui-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ui-focus" aria-label="Fermer"><span aria-hidden="true">&times;</span></button>`;
    toast.querySelector("p").textContent = message;
    const visibleToasts = region.querySelectorAll("[data-ui-toast]");
    if (visibleToasts.length >= 3) visibleToasts[visibleToasts.length - 1].remove();
    const remove = () => toast.remove();
    toast.querySelector("button").addEventListener("click", remove);
    let timer = window.setTimeout(remove, Number(raw.duration) || 4500);
    toast.addEventListener("mouseenter", () => window.clearTimeout(timer));
    toast.addEventListener("mouseleave", () => { timer = window.setTimeout(remove, 1800); });
    region.prepend(toast);
  };

  // Compatibility only: legacy endpoints and templates may still send
  // ``showToast`` / ``esfe:toast``. They now use the one UI Core renderer.
  window.esfeToast = function (messageOrDetail, type = "info", options = {}) {
    const detail = typeof messageOrDetail === "object" && messageOrDetail !== null
      ? messageOrDetail
      : { message: messageOrDetail, type, ...options };
    UI.toast(detail, type);
  };
  window.showToast = window.esfeToast;

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

  UI.emitDataChanged = function (requestPath = "") {
    document.body.dispatchEvent(new CustomEvent("esfe:data-changed", { bubbles: true }));
    const topics = {
      paiement: "payments", payment: "payments",
      candidature: "candidatures", candidat: "candidatures",
      caisse: "session", cash: "session", session: "session",
      depense: "expenses", expense: "expenses",
      boutique: "shop", shop: "shop",
      salaire: "salaries", salary: "salaries",
      inscription: "inscriptions", secretaire: "secretary", secretary: "secretary",
      enseignant: "teachers", teacher: "teachers"
    };
    Object.entries(topics).forEach(([term, topic]) => {
      if (requestPath.includes(term)) {
        document.body.dispatchEvent(new CustomEvent(`esfe:${topic}-changed`, { bubbles: true }));
      }
    });
  };

  UI.bootstrapToasts = function () {
    const bootstrap = document.getElementById("ui-toast-bootstrap");
    if (!bootstrap || bootstrap.dataset.loaded === "true") return;
    bootstrap.dataset.loaded = "true";
    try {
      JSON.parse(bootstrap.textContent || "[]").forEach((detail) => UI.toast(detail));
    } catch (_) {}
  };

  // The certified top bar is shared by every dashboard. Keep its clock alive
  // in the browser instead of making a server request for a visual-only value.
  UI.refreshLiveClocks = function (root) {
    (root || document).querySelectorAll("[data-ui-live-clock]").forEach((clock) => {
      const now = new Date();
      clock.dateTime = now.toISOString();
      clock.textContent = new Intl.DateTimeFormat("fr-FR", {
        weekday: "short",
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      }).format(now).replace(",", " ·");
    });
  };

  UI.setContextLabel = function (label) {
    if (!label) return;
    document.querySelectorAll("[data-ui-context-label]").forEach((node) => {
      node.textContent = label;
    });
  };

  const initialize = () => {
    UI.init(document);
    UI.bootstrapToasts();
    UI.refreshLiveClocks(document);
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize);
  else initialize();

  document.addEventListener("ui:toast", (event) => UI.toast(event.detail));
  document.addEventListener("esfe:toast", (event) => UI.toast(event.detail));
  document.addEventListener("toast", (event) => UI.toast(event.detail));
  document.addEventListener("showToast", (event) => UI.toast(event.detail, "success"));
  document.body.addEventListener("htmx:configRequest", (event) => {
    const token = document.cookie.split("; ").find((item) => item.startsWith("csrftoken="));
    if (token) event.detail.headers["X-CSRFToken"] = decodeURIComponent(token.split("=").slice(1).join("="));
  });
  document.body.addEventListener("htmx:afterSwap", (event) => UI.init(event.detail.target));
  document.addEventListener("esfe:dashboard-context-changed", (event) => {
    UI.setContextLabel(event.detail && event.detail.label);
  });
  if (!UI.liveClockTimer) {
    UI.liveClockTimer = window.setInterval(() => UI.refreshLiveClocks(document), 30000);
  }
  function hasToastTrigger(xhr) {
    const trigger = xhr && xhr.getResponseHeader("HX-Trigger");
    if (!trigger) return false;
    try {
      const events = JSON.parse(trigger);
      return Boolean(events["ui:toast"] || events.toast || events.showToast);
    } catch (_) {
      return false;
    }
  }

  document.body.addEventListener("htmx:afterRequest", (event) => {
    const xhr = event.detail.xhr;
    const trigger = xhr && xhr.getResponseHeader("HX-Trigger");
    const requestPath = (event.detail.pathInfo && event.detail.pathInfo.requestPath) || "";
    if (event.detail.successful) UI.emitDataChanged(requestPath);
    if (!trigger) return;
    try {
      const events = JSON.parse(trigger);
      if (events["ui:toast"]) UI.toast(events["ui:toast"]);
      if (events.toast) UI.toast(events.toast);
      if (events.showToast) UI.toast(events.showToast, "success");
    } catch (_) {}
  });
  document.body.addEventListener("htmx:responseError", (event) => {
    if (hasToastTrigger(event.detail && event.detail.xhr)) return;
    UI.toast({ message: "La requête n'a pas pu aboutir.", tone: "danger" });
  });
})();
