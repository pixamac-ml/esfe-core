(function () {
  "use strict";

  const root = document.querySelector("[data-certified-dashboard-shell]");
  if (!root) return;

  const key = root.dataset.dashboardKey || "director";
  const workspaceSelector = `#${key}-workspace`;
  const loadingSelector = `#${key}-loading`;
  const modalContentSelector = `#${key}-modal-content`;
  let pendingConfirmation = null;

  function dispatchOverlay(action, id) {
    window.dispatchEvent(
      new CustomEvent(`ui-overlay-${action}`, { detail: { id } }),
    );
  }

  function workspace() {
    return document.querySelector(workspaceSelector);
  }

  function sectionFrom(target) {
    if (!target) return "";
    const explicit = target.querySelector("[data-dashboard-section]");
    if (explicit) return explicit.dataset.dashboardSection || "";
    const roleSection = target.querySelector(`[data-${key}-section]`);
    return roleSection ? roleSection.dataset[`${key}Section`] || "" : "";
  }

  function setActiveNavigation(section) {
    if (!section) return;
    document.querySelectorAll("[data-ui-nav-item][data-nav-key]").forEach((item) => {
      const active = item.dataset.navKey === section;
      item.dataset.active = active ? "true" : "false";
      if (active) item.setAttribute("aria-current", "page");
      else item.removeAttribute("aria-current");
    });
  }

  function setBusy(busy) {
    const target = workspace();
    const indicator = document.querySelector(loadingSelector);
    if (target) target.setAttribute("aria-busy", busy ? "true" : "false");
    if (indicator) indicator.classList.toggle("hidden", !busy);
  }

  const api = {
    key,
    root,
    workspace,
    workspaceSelector,
    loadingSelector,
    sectionFrom,
    setActiveNavigation,
    setBusy,
  };
  window.ESFECertifiedDashboard = api;

  document.addEventListener("click", (event) => {
    const item = event.target.closest("[data-ui-nav-item][data-nav-key]");
    if (item) {
      const section = item.dataset.navKey;
      setActiveNavigation(section);
      window.dispatchEvent(
        new CustomEvent("certified-dashboard:navigate", {
          detail: { key, section, item },
        }),
      );
    }
    if (key === "manager") {
      const confirmButton = event.target.closest(
        `[data-ui-confirm-accept="${key}-confirm"]`,
      );
      if (confirmButton && pendingConfirmation) {
        const issueRequest = pendingConfirmation;
        pendingConfirmation = null;
        dispatchOverlay("close", `${key}-confirm`);
        issueRequest();
      }
    }
  });

  if (key === "manager") {
    document.body.addEventListener("htmx:confirm", (event) => {
      if (!event.detail.question) return;
      event.preventDefault();
      const message = document.querySelector(`#${key}-confirm-message`);
      if (message) message.textContent = event.detail.question;
      pendingConfirmation = () => event.detail.issueRequest(true);
      dispatchOverlay("open", `${key}-confirm`);
    });
  }

  document.body.addEventListener("htmx:beforeRequest", (event) => {
    if (event.detail.target && event.detail.target.matches(workspaceSelector)) {
      setBusy(true);
    }
    if (
      key === "manager" &&
      event.detail.target &&
      event.detail.target.matches(modalContentSelector)
    ) {
      dispatchOverlay("open", `${key}-modal`);
    }
  });

  document.body.addEventListener("htmx:afterRequest", (event) => {
    if (event.detail.target && event.detail.target.matches(workspaceSelector)) {
      setBusy(false);
    }
  });

  document.body.addEventListener("htmx:afterSwap", (event) => {
    const target = event.detail.target;
    if (!target || !target.matches(workspaceSelector)) return;
    setBusy(false);
    setActiveNavigation(sectionFrom(target));
  });

  setActiveNavigation(sectionFrom(workspace()));
})();
