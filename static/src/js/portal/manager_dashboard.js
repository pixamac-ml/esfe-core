(function () {
  "use strict";

  const api = window.ESFECertifiedDashboard;
  if (!api || api.key !== "manager") return;
  if (document.documentElement.dataset.managerDashboardBound === "true") return;
  document.documentElement.dataset.managerDashboardBound = "true";

  function currentSubview() {
    return new URL(window.location.href).searchParams.get("view") || "overview";
  }

  function dispatchSubview(id) {
    if (!id) return;
    window.dispatchEvent(new CustomEvent("manager-subview", { detail: { id } }));
    window.requestAnimationFrame(() => {
      const active = document.querySelector(`[data-manager-subview="${id}"]`);
      if (active) active.scrollIntoView({ block: "nearest", inline: "nearest" });
    });
  }

  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-manager-subview]");
    if (link) dispatchSubview(link.dataset.managerSubview);
  });

  document.body.addEventListener("htmx:afterSwap", (event) => {
    const target = event.detail.target;
    if (!target || !target.id || !/^manager-.+-subcontent$/.test(target.id)) return;
    dispatchSubview(currentSubview());
    target.focus({ preventScroll: true });
    if (window.lucide) window.lucide.createIcons({ nodes: [target] });
    if (window.htmx) window.htmx.process(target);
  });

  document.body.addEventListener("htmx:historyRestore", () => {
    dispatchSubview(currentSubview());
  });
})();
