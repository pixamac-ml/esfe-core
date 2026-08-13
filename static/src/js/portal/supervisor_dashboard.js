(function () {
  "use strict";

  const WORKSPACE = "#supervisor-workspace";
  const DRAWER_CONTENT = "#supervisor-drawer-content";
  let pendingConfirmation = null;

  function dispatchOverlay(action) {
    window.dispatchEvent(
      new CustomEvent(`ui-overlay-${action}`, {
        detail: { id: "supervisor-drawer" }
      })
    );
  }

  function setBusy(busy) {
    const workspace = document.querySelector(WORKSPACE);
    const indicator = document.querySelector("#supervisor-loading");
    if (workspace) workspace.setAttribute("aria-busy", busy ? "true" : "false");
    if (indicator) indicator.classList.toggle("hidden", !busy);
  }

  function currentSection() {
    const section = document.querySelector(
      `${WORKSPACE} [data-supervisor-section]`
    );
    return section ? section.dataset.supervisorSection : "home";
  }

  function currentView() {
    const section = document.querySelector(`${WORKSPACE} [data-supervisor-section]`);
    return section ? (section.dataset.supervisorView || "overview") : "overview";
  }

  function selectedWorkspaceClass() {
    const section = document.querySelector(
      `${WORKSPACE} [data-supervisor-section]`
    );
    return section ? (section.dataset.selectedClassId || "") : "";
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

  function updateUrlAttribute(item, attribute, classId) {
    const raw = item.getAttribute(attribute);
    if (!raw) return;
    const url = new URL(raw, window.location.origin);
    if (item.dataset.navKey === "signals" || !classId) {
      url.searchParams.delete("class_id");
    } else {
      url.searchParams.set("class_id", classId);
    }
    item.setAttribute(attribute, `${url.pathname}${url.search}${url.hash}`);
  }

  function syncClassNavigation(classId) {
    document.querySelectorAll("[data-ui-nav-item][data-nav-key]").forEach((item) => {
      ["href", "hx-get", "hx-push-url"].forEach((attribute) => {
        updateUrlAttribute(item, attribute, classId);
      });
    });
  }

  function syncClassPicker(section) {
    const wrapper = document.querySelector("[data-supervisor-class-picker]");
    const selector = document.querySelector("#supervisor-class-selector");
    if (!wrapper || !selector) return;
    wrapper.hidden = section === "signals";
    const workspaceUrl = selector.dataset.workspaceUrl;
    if (workspaceUrl && section !== "signals") {
      selector.setAttribute(
        "hx-get",
        `${workspaceUrl}?section=${encodeURIComponent(section || "home")}&view=${encodeURIComponent(currentView())}`
      );
    }
  }

  function syncCanonicalUrl(classId) {
    const url = new URL(window.location.href);
    url.pathname = document.querySelector('[data-ui-nav-item][data-nav-key="home"]')
      ?.getAttribute("href")
      ?.split("?")[0] || url.pathname;
    url.search = "";
    url.hash = "";
    url.searchParams.set("section", currentSection());
    url.searchParams.set("view", currentView());
    if (classId) url.searchParams.set("class_id", classId);
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}`);
  }

  function dispatchSubview(id) {
    if (!id) return;
    window.dispatchEvent(new CustomEvent("supervisor-subview", { detail: { id } }));
    window.requestAnimationFrame(() => {
      const active = document.querySelector(`[data-supervisor-subview="${id}"]`);
      if (active) active.scrollIntoView({ block: "nearest", inline: "nearest" });
    });
  }

  function showToast(detail) {
    if (!window.ESFEUI || !window.ESFEUI.toast) return;
    const data = typeof detail === "string" ? { message: detail } : (detail || {});
    window.ESFEUI.toast({
      message: data.message || "Action effectuée.",
      tone: data.tone || (data.level === "error" ? "danger" : data.level) || "info"
    });
  }

  window.supervisorOpenDrawer = () => dispatchOverlay("open");
  window.supervisorCloseDrawer = () => dispatchOverlay("close");

  if (document.documentElement.dataset.supervisorDashboardBound === "true") return;
  document.documentElement.dataset.supervisorDashboardBound = "true";

  document.addEventListener("change", (event) => {
    if (!event.target.matches("#supervisor-class-selector")) return;
    syncClassNavigation(event.target.value);
    syncCanonicalUrl(event.target.value);
  });

  document.addEventListener("click", (event) => {
    const navigation = event.target.closest("[data-ui-nav-item][data-nav-key]");
    if (navigation) setActiveNavigation(navigation.dataset.navKey);

    const subviewLink = event.target.closest("[data-supervisor-subview]");
    if (subviewLink) dispatchSubview(subviewLink.dataset.supervisorSubview);

    const confirmButton = event.target.closest(
      '[data-ui-confirm-accept="supervisor-confirm"]'
    );
    if (confirmButton && pendingConfirmation) {
      const issueRequest = pendingConfirmation;
      pendingConfirmation = null;
      window.dispatchEvent(
        new CustomEvent("ui-overlay-close", {
          detail: { id: "supervisor-confirm" }
        })
      );
      issueRequest();
    }
  });

  document.body.addEventListener("htmx:confirm", (event) => {
    if (!event.detail.question) return;
    event.preventDefault();
    const message = document.querySelector("#supervisor-confirm-message");
    if (message) message.textContent = event.detail.question;
    pendingConfirmation = () => event.detail.issueRequest(true);
    window.dispatchEvent(
      new CustomEvent("ui-overlay-open", {
        detail: { id: "supervisor-confirm" }
      })
    );
  });

  document.body.addEventListener("htmx:beforeRequest", (event) => {
    const target = event.detail.target;
    if (!target) return;
    if (target.matches(WORKSPACE)) setBusy(true);
    if (target.matches(DRAWER_CONTENT)) window.supervisorOpenDrawer();
  });

  document.body.addEventListener("htmx:afterRequest", (event) => {
    const target = event.detail.target;
    if (target && target.matches(WORKSPACE)) setBusy(false);
  });

  document.body.addEventListener("htmx:afterSwap", (event) => {
    const target = event.detail.target;
    if (!target) return;
    if (target.matches("#supervisor-section-content")) {
      const swapped = target.querySelector("[data-supervisor-view]");
      const shell = document.querySelector(`${WORKSPACE} [data-supervisor-section]`);
      if (swapped && shell) shell.dataset.supervisorView = swapped.dataset.supervisorView;
      dispatchSubview(currentView());
      if (window.lucide) window.lucide.createIcons();
      return;
    }
    if (!target.matches(WORKSPACE)) return;
    setBusy(false);
    const section = currentSection();
    setActiveNavigation(section);
    syncClassPicker(section);
    const selector = document.querySelector("#supervisor-class-selector");
    const selectedClassId = selectedWorkspaceClass();
    if (selector) selector.value = selectedClassId;
    syncClassNavigation(selectedClassId);
    target.focus({ preventScroll: true });
  });

  window.addEventListener("supervisor-drawer-close", window.supervisorCloseDrawer);
  window.addEventListener("toast", (event) => showToast(event.detail));
  document.body.addEventListener("htmx:historyRestore", () => {
    dispatchSubview(currentView());
  });
  window.addEventListener("supervisor-attendance-updated", () => {
    window.supervisorCloseDrawer();
    const selector = document.querySelector("#supervisor-class-selector");
    const endpoint = selector?.dataset.workspaceUrl;
    if (endpoint && window.htmx) {
      const params = new URLSearchParams({ section: currentSection(), view: currentView() });
      if (selectedWorkspaceClass()) params.set("class_id", selectedWorkspaceClass());
      window.htmx.ajax("GET", `${endpoint}?${params.toString()}`, { target: WORKSPACE, swap: "innerHTML" });
    }
  });

  document.addEventListener("DOMContentLoaded", () => {
    const section = currentSection();
    setActiveNavigation(section);
    syncClassPicker(section);
    const selector = document.querySelector("#supervisor-class-selector");
    syncClassNavigation(selector ? selector.value : "");
  });
})();
