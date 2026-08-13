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

  function currentSubview() {
    return new URL(window.location.href).searchParams.get("view") || "overview";
  }

  function dispatchSubview(id) {
    if (!id) return;
    window.dispatchEvent(new CustomEvent("director-subview", { detail: { id } }));
    window.requestAnimationFrame(() => {
      const active = document.querySelector(`[data-director-subview="${id}"]`);
      if (active) active.scrollIntoView({ block: "nearest", inline: "nearest" });
    });
  }

  function syncTimetableTabs(target) {
    const region = target && (
      target.matches("#director-timetable-subcontent")
        ? target
        : target.closest("#director-timetable-subcontent")
    );
    if (!region) return;
    const classId = region.querySelector('select[name="class_id"]')?.value;
    if (!classId) return;
    document.querySelectorAll("#director-timetable-tabs [data-director-subview]").forEach((link) => {
      ["href", "hx-get", "hx-push-url"].forEach((attribute) => {
        const value = link.getAttribute(attribute);
        if (!value) return;
        const url = new URL(value, window.location.origin);
        url.searchParams.set("class_id", classId);
        link.setAttribute(attribute, `${url.pathname}${url.search}`);
      });
    });
  }

  function subwindowErrorRegion(target) {
    if (!target) return null;
    if (target.closest("#director-session-subcontent") || target.matches("#director-session-subcontent")) {
      return document.querySelector("#director-session-error");
    }
    if (target.closest("#director-results-subcontent") || target.matches("#director-results-subcontent")) {
      return document.querySelector("#director-results-error");
    }
    if (target.closest("#director-programme-subcontent") || target.matches("#director-programme-subcontent")) {
      return document.querySelector("#director-programme-error");
    }
    if (target.closest("#director-teacher-subcontent") || target.matches("#director-teacher-subcontent")) {
      return document.querySelector("#director-teacher-error");
    }
    if (target.closest("#director-document-subcontent") || target.matches("#director-document-subcontent")) {
      return document.querySelector("#director-document-error");
    }
    if (target.closest("#director-timetable-subcontent") || target.matches("#director-timetable-subcontent")) {
      return document.querySelector("#director-timetable-error");
    }
    return null;
  }

  function clearSubwindowError(target) {
    const region = subwindowErrorRegion(target);
    if (!region) return;
    region.classList.add("hidden");
    region.replaceChildren();
  }

  function showSubwindowError(target) {
    const region = subwindowErrorRegion(target);
    if (!region) return;
    region.className = "mb-4 flex items-start gap-2 rounded-ui-card border border-ui-danger/25 bg-ui-danger-soft p-4 text-sm font-semibold text-ui-danger";
    region.textContent = "Le contenu n'a pas pu être chargé. Réessayez dans quelques instants.";
  }

  window.deOpenDrawer = () => dispatchOverlay("open", "director-drawer");
  window.deCloseDrawer = () => dispatchOverlay("close", "director-drawer");
  window.deOpenModal = () => dispatchOverlay("open", "director-modal");
  window.deCloseModal = () => dispatchOverlay("close", "director-modal");
  if (document.documentElement.dataset.directorDashboardBound === "true") return;
  document.documentElement.dataset.directorDashboardBound = "true";

  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-ui-nav-item][data-nav-key]");
    if (link) setActiveNavigation(link.dataset.navKey);
    const subviewLink = event.target.closest(
      "[data-director-subview], [data-director-subview-link]"
    );
    if (subviewLink) {
      dispatchSubview(
        subviewLink.dataset.directorSubview || subviewLink.dataset.directorSubviewLink
      );
    }
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
    clearSubwindowError(target);
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
    if (
      target.matches("#director-session-subcontent, #director-results-subcontent, #director-programme-subcontent, #director-teacher-subcontent, #director-document-subcontent, #director-timetable-subcontent") ||
      target.closest("#director-session-subcontent, #director-results-subcontent, #director-programme-subcontent, #director-teacher-subcontent, #director-document-subcontent, #director-timetable-subcontent")
    ) {
      syncTimetableTabs(target);
      dispatchSubview(currentSubview());
    }
  });

  document.body.addEventListener("htmx:responseError", (event) => {
    showSubwindowError(event.detail.target);
  });
  document.body.addEventListener("htmx:sendError", (event) => {
    showSubwindowError(event.detail.target);
  });
  document.body.addEventListener("htmx:historyRestore", () => {
    dispatchSubview(currentSubview());
  });

  document.body.addEventListener("account:profile-updated", refreshTopbar);
  document.body.addEventListener("notificationsChanged", refreshTopbar);
  document.body.addEventListener("notification.read", refreshTopbar);
  document.body.addEventListener("director-modal-close", window.deCloseModal);
  document.body.addEventListener("director-drawer-close", window.deCloseDrawer);

  document.addEventListener("DOMContentLoaded", () => {
    const workspace = document.querySelector(WORKSPACE);
    if (workspace) setActiveNavigation(workspaceSection(workspace));
  });
})();
