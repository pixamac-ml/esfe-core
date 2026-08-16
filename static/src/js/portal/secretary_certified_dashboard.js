(function () {
  "use strict";

  const drawerId = "sg-drawer";
  const modalId = "sg-modal";

  function overlay(action, id) {
    window.dispatchEvent(
      new CustomEvent(`ui-overlay-${action}`, { detail: { id } }),
    );
  }

  window.sgOpenDrawer = function () {
    overlay("open", drawerId);
  };
  window.sgCloseDrawer = function () {
    overlay("close", drawerId);
  };
  window.sgClose = function () {
    overlay("close", modalId);
  };

  document.body.addEventListener("htmx:beforeRequest", function (event) {
    const target = event.detail.elt?.getAttribute?.("hx-target");
    if (target === "#sg-drawer-content") window.sgOpenDrawer();
    if (target === "#sg-modal-content") overlay("open", modalId);
  });

  document.body.addEventListener("htmx:afterSwap", function (event) {
    const target = event.detail.target;
    if (!target) return;
    if (target.id === "sg-drawer-content" && target.innerHTML.trim()) {
      window.sgOpenDrawer();
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
      if (triggers["secretary-drawer-close"]) window.sgCloseDrawer();
    } catch (_) {
      // A non-JSON trigger belongs to another feature.
    }
  });
})();
