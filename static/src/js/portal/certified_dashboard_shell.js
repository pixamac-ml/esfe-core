(function () {
  "use strict";

  const root = document.querySelector("[data-certified-dashboard-shell]");
  if (!root) return;

  const key = root.dataset.dashboardKey || "director";
  const workspaceSelector = `#${key}-workspace`;
  const loadingSelector = `#${key}-loading`;
  const modalContentSelector = `#${key}-modal-content`;
  const drawerContentSelector = `#${key}-drawer-content`;
  // Teacher and secretary workflows predate the certified shell and still
  // target the shared SG containers. Keep this adapter until their fragments
  // are migrated, while opening the same certified overlays as every role.
  const legacyOverlayContentSelector =
    key === "teacher" || key === "secretary" ? "#sg-drawer-content" : "";
  const legacyModalContentSelector =
    key === "teacher" || key === "secretary" ? "#sg-modal-content" : "";
  let pendingConfirmation = null;
  let workspaceRequestSequence = 0;

  function dispatchOverlay(action, id) {
    window.dispatchEvent(
      new CustomEvent(`ui-overlay-${action}`, { detail: { id } }),
    );
  }

  function workspace() {
    return document.querySelector(workspaceSelector);
  }

  function requestTargets(event, selector) {
    const detail = event.detail || {};
    const target = detail.target;
    if (target && typeof target.matches === "function" && target.matches(selector)) {
      return true;
    }
    const elt = detail.elt;
    return !!(
      elt &&
      typeof elt.getAttribute === "function" &&
      elt.getAttribute("hx-target") === selector
    );
  }

  function openRequestedOverlay(event) {
    if (requestTargets(event, modalContentSelector)) {
      dispatchOverlay("open", `${key}-modal`);
    }
    if (requestTargets(event, drawerContentSelector)) {
      dispatchOverlay("open", `${key}-drawer`);
    }
    if (legacyOverlayContentSelector && requestTargets(event, legacyOverlayContentSelector)) {
      dispatchOverlay("open", `${key}-drawer`);
    }
    if (legacyModalContentSelector && requestTargets(event, legacyModalContentSelector)) {
      dispatchOverlay("open", `${key}-modal`);
    }
  }

  function syncItNotesDrawerMode(target) {
    if (key !== "it-dashboard" || !target || !target.matches(drawerContentSelector)) {
      return;
    }
    const drawer = target.closest('[data-ui-core="drawer"]');
    if (drawer) {
      drawer.classList.toggle(
        "it-notes-entry-mode",
        Boolean(target.querySelector("[data-it-notes-entry]")),
      );
    }
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

  function workspaceRequestId(event) {
    const responseUrl = event.detail && event.detail.xhr && event.detail.xhr.responseURL;
    if (!responseUrl) return "";
    try {
      return new URL(responseUrl, window.location.origin).searchParams.get("_workspace_request") || "";
    } catch (_error) {
      return "";
    }
  }

  function isCurrentWorkspaceRequest(event) {
    const target = workspace();
    const responseUrl = event.detail && event.detail.xhr && event.detail.xhr.responseURL;
    if (!target || !responseUrl) return true;
    try {
      const requestId = new URL(responseUrl, window.location.origin).searchParams.get("_workspace_request");
      return !requestId || !target.dataset.workspaceRequestId || target.dataset.workspaceRequestId === requestId;
    } catch (_error) {
      return true;
    }
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

  // Generic staff endpoints (messaging compose, ...) ask the shell to close
  // its modal after a successful HTMX exchange. This listener must be
  // registered once, not once per document click.
  document.body.addEventListener("certified-dashboard:close-modal", () => {
    dispatchOverlay("close", `${key}-modal`);
  });

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
    if (requestTargets(event, workspaceSelector)) {
      setBusy(true);
    }
    openRequestedOverlay(event);
  });

  document.body.addEventListener("htmx:configRequest", (event) => {
    if (!requestTargets(event, workspaceSelector)) return;
    const target = workspace();
    if (!target) return;
    // The DG controller owns its request token and places it directly in the
    // section URL. Replacing that token here made its own stale-response guard
    // reject the initial response, leaving the workspace visually blank.
    if (key === "executive" && target.matches("[data-dg-dashboard]")) return;
    const requestId = `${Date.now()}-${++workspaceRequestSequence}`;
    event.detail.parameters = event.detail.parameters || {};
    event.detail.parameters._workspace_request = requestId;
    target.dataset.workspaceRequestId = requestId;
  });

  // IT workflow actions already publish this event after a successful save.
  // Keeping the bridge in the certified shell lets their content use the
  // shared UI Core modal without owning a second overlay implementation.
  if (key === "it-dashboard") {
    document.body.addEventListener("it-modal-close", () => {
      dispatchOverlay("close", `${key}-modal`);
    });
    document.body.addEventListener("it-temporary-password-ready", () => {
      dispatchOverlay("open", `${key}-modal`);
    });
    window.addEventListener("ui-overlay-close", (event) => {
      if (event.detail && event.detail.id === `${key}-drawer`) {
        const drawer = document.querySelector('[data-ui-core="drawer"].it-notes-entry-mode');
        if (drawer) drawer.classList.remove("it-notes-entry-mode");
      }
    });
  }

  document.body.addEventListener("htmx:afterRequest", (event) => {
    if (requestTargets(event, workspaceSelector)) {
      if (!isCurrentWorkspaceRequest(event)) return;
      setBusy(false);
    }
  });

  document.body.addEventListener("htmx:beforeSwap", (event) => {
    if (!requestTargets(event, workspaceSelector) || isCurrentWorkspaceRequest(event)) return;
    // Une réponse plus ancienne ne doit jamais remplacer la section choisie
    // après elle : même contrat de fluidité que le cockpit DG.
    event.preventDefault();
  });

  document.body.addEventListener("htmx:afterSwap", (event) => {
    const target = event.detail.target;
    openRequestedOverlay(event);
    syncItNotesDrawerMode(target);
    if (!target || !target.matches(workspaceSelector)) return;
    if (!isCurrentWorkspaceRequest(event)) return;
    setBusy(false);
    setActiveNavigation(sectionFrom(target));
  });

  document.body.addEventListener("htmx:responseError", (event) => {
    const target = event.detail && event.detail.target;
    if (!target) return;
    if (target.matches(workspaceSelector)) {
      if (!isCurrentWorkspaceRequest(event)) return;
      setBusy(false);
      return;
    }
    const overlayTargets = [modalContentSelector, drawerContentSelector, legacyModalContentSelector, legacyOverlayContentSelector]
      .filter(Boolean);
    if (!overlayTargets.some((selector) => target.matches(selector))) return;
    target.innerHTML = '<div class="rounded-ui-card border border-ui-danger/40 bg-ui-danger-soft p-4 text-sm font-semibold text-ui-danger" role="alert">Le contenu demandé est indisponible. Fermez cette fenêtre puis réessayez.</div>';
  });

  setActiveNavigation(sectionFrom(workspace()));
})();
