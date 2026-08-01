(function () {
  "use strict";

  const WORKSPACE = "#director-workspace";
  const DRAWER_CONTENT = "#director-drawer-content";
  const MODAL_CONTENT = "#director-modal-content";
  let pendingConfirmation = null;

  function dispatchOverlay(action, id) {
    window.dispatchEvent(
      new CustomEvent(`ui-overlay-${action}`, { detail: { id } })
    );
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

  function workspaceSection(root) {
    const section = root.querySelector("[data-director-section]");
    return section ? section.dataset.directorSection : "";
  }

  function setBusy(busy) {
    const workspace = document.querySelector(WORKSPACE);
    const indicator = document.querySelector("#director-loading");
    if (workspace) workspace.setAttribute("aria-busy", busy ? "true" : "false");
    if (indicator) indicator.classList.toggle("hidden", !busy);
  }

  function refreshTopbar() {
    const button = document.getElementById("director-topbar-refresh");
    if (button) button.click();
  }

  window.deOpenDrawer = () => dispatchOverlay("open", "director-drawer");
  window.deCloseDrawer = () => dispatchOverlay("close", "director-drawer");
  window.deOpenModal = () => dispatchOverlay("open", "director-modal");
  window.deCloseModal = () => dispatchOverlay("close", "director-modal");
  window.deEvalForm = () => ({
    open: false,
    selectedClass: "",
    ecsByClass: {},
    init() {
      try {
        const data = document.getElementById("de-ecs-by-class-data");
        this.ecsByClass = data ? JSON.parse(data.textContent) : {};
      } catch (_error) {
        this.ecsByClass = {};
      }
    },
  });

  if (document.documentElement.dataset.directorDashboardBound === "true") return;
  document.documentElement.dataset.directorDashboardBound = "true";

  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-ui-nav-item][data-nav-key]");
    if (link) setActiveNavigation(link.dataset.navKey);
    const confirmButton = event.target.closest(
      '[data-ui-confirm-accept="director-confirm"]'
    );
    if (confirmButton && pendingConfirmation) {
      const issueRequest = pendingConfirmation;
      pendingConfirmation = null;
      dispatchOverlay("close", "director-confirm");
      issueRequest();
    }
  });

  document.body.addEventListener("htmx:confirm", (event) => {
    if (!event.detail.question) return;
    event.preventDefault();
    const message = document.querySelector("#director-confirm-message");
    if (message) message.textContent = event.detail.question;
    pendingConfirmation = () => event.detail.issueRequest(true);
    dispatchOverlay("open", "director-confirm");
  });

  document.body.addEventListener("htmx:beforeRequest", (event) => {
    const target = event.detail.target;
    if (!target) return;
    if (target.matches(WORKSPACE)) setBusy(true);
    if (target.matches(DRAWER_CONTENT)) window.deOpenDrawer();
    if (target.matches(MODAL_CONTENT)) window.deOpenModal();
  });

  document.body.addEventListener("htmx:afterRequest", (event) => {
    const target = event.detail.target;
    if (target && target.matches(WORKSPACE)) setBusy(false);
  });

  document.body.addEventListener("htmx:afterSwap", (event) => {
    const target = event.detail.target;
    if (!target) return;
    if (target.matches(WORKSPACE)) {
      setBusy(false);
      setActiveNavigation(workspaceSection(target));
      target.focus({ preventScroll: true });
    }
  });

  document.body.addEventListener("account:profile-updated", refreshTopbar);
  document.body.addEventListener("notificationsChanged", refreshTopbar);
  document.body.addEventListener("notification.read", refreshTopbar);

  document.addEventListener("DOMContentLoaded", () => {
    const workspace = document.querySelector(WORKSPACE);
    if (workspace) setActiveNavigation(workspaceSection(workspace));
  });
})();
