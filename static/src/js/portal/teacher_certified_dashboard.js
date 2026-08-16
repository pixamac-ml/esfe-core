(function () {
  "use strict";

  const drawerId = "teacher-drawer";
  const modalId = "teacher-modal";

  function overlay(action, id) {
    window.dispatchEvent(
      new CustomEvent(`ui-overlay-${action}`, { detail: { id } }),
    );
  }

  window.teacherOpenDrawer = function () {
    overlay("open", drawerId);
  };
  window.teacherCloseDrawer = function () {
    overlay("close", drawerId);
  };
  window.sgClose = function () {
    overlay("close", modalId);
  };

  function refreshWorkspace() {
    if (!window.htmx) return;
    window.htmx.ajax("GET", window.location.href, {
      target: "#teacher-workspace",
      swap: "innerHTML",
    });
  }

  document.body.addEventListener("htmx:beforeRequest", function (event) {
    const target = event.detail.elt?.getAttribute?.("hx-target");
    if (target === "#sg-drawer-content") window.teacherOpenDrawer();
    if (target === "#sg-modal-content") overlay("open", modalId);
  });

  document.body.addEventListener("htmx:afterSwap", function (event) {
    const target = event.detail.target;
    if (!target) return;
    if (target.id === "sg-drawer-content" && target.innerHTML.trim()) {
      window.teacherOpenDrawer();
    }
    if (target.id === "sg-modal-content" && target.innerHTML.trim()) {
      overlay("open", modalId);
    }
  });

  document.body.addEventListener("htmx:afterRequest", function (event) {
    const raw = event.detail.xhr?.getResponseHeader?.("HX-Trigger") || "";
    if (!raw) return;
    try {
      const triggers = JSON.parse(raw);
      if (triggers["teacher-drawer-close"]) window.teacherCloseDrawer();
      if (triggers["teacher-dashboard-refresh"]) refreshWorkspace();
    } catch (_) {
      // A non-JSON trigger does not belong to the teacher workspace.
    }
  });
})();
