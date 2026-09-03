(function () {
  "use strict";

  const workspace = document.querySelector("[data-dg-dashboard]");
  if (!workspace || !window.htmx) return;

  const shellRoot = document.querySelector("[data-certified-dashboard-shell]");
  const sectionBase = workspace.dataset.dgSectionUrl.replace(/overview\/?$/, "");
  const dashboardUrl = workspace.dataset.dgDashboardUrl;
  const modalUrl = workspace.dataset.dgModalUrl;
  const drawerTarget = "#executive-drawer-content";
  const modalTarget = "#executive-modal-content";
  const workspaceTarget = "#executive-workspace";
  const domainBySection = {
    overview: "commandement",
    annexes: "annexes",
    branch_list: "annexes",
    branch_comparison: "annexes",
    branch_managers: "annexes",
    branch_activity: "annexes",
    alerts: "annexes",
    finance: "finance",
    payments: "finance",
    expenses: "finance",
    receivables: "finance",
    cash_movements: "finance",
    closures: "finance",
    bank_transfers: "finance",
    finance_reports: "finance",
    coupons: "finance",
    academic_overview: "academique",
    formations: "academique",
    academic_calendar: "academique",
    classes: "academique",
    schedule: "academique",
    evaluations: "academique",
    results: "academique",
    progression: "academique",
    diplomas: "academique",
    students_overview: "etudiants",
    students: "etudiants",
    enrollments: "etudiants",
    reenrollments: "etudiants",
    workflows: "etudiants",
    student_cases: "etudiants",
    staff_overview: "personnel",
    rh: "personnel",
    recruitment: "personnel",
    assignments: "personnel",
    staff_contracts: "personnel",
    staff_access: "personnel",
    staff_history: "personnel",
    documents: "gouvernance",
    analytics: "gouvernance",
    realtime: "gouvernance",
    audit: "gouvernance",
    exports: "gouvernance",
    messaging: "mon_espace",
    settings: "mon_espace",
  };
  const defaultSectionByDomain = {
    commandement: "overview",
    annexes: "branch_list",
    finance: "finance",
    academique: "schedule",
    etudiants: "workflows",
    personnel: "rh",
    gouvernance: "analytics",
    mon_espace: "messaging",
  };
  const dgSections = new Set(Object.keys(domainBySection));
  const dgDomains = new Set(Object.keys(defaultSectionByDomain));
  let workspaceRequestSequence = 0;

  function currentSection() {
    return workspace.dataset.executiveSection || workspace.dataset.dashboardSection || "overview";
  }

  function domainForSection(section) {
    return domainBySection[String(section || "").toLowerCase()] || "commandement";
  }

  function currentDomain() {
    return workspace.dataset.dgDomain || domainForSection(currentSection());
  }

  function scopedUrl(rawUrl, params) {
    const url = new URL(rawUrl, window.location.origin);
    const source = new URL(window.location.href);
    ["academic_year_id", "scope_branch_id", "period", "week_start", "class_id"].forEach((key) => {
      if (!url.searchParams.has(key) && source.searchParams.has(key)) {
        url.searchParams.set(key, source.searchParams.get(key));
      }
    });
    Object.entries(params || {}).forEach(([key, value]) => {
      // An empty branch scope is meaningful: it explicitly switches the DG
      // back to the global view.  Removing the parameter made the backend
      // reuse the former branch stored in session, leaving the dashboard
      // apparently stuck on that annexe.
      if (value === null || value === undefined || value === "") {
        if (key === "scope_branch_id") url.searchParams.set(key, "");
        else url.searchParams.delete(key);
      }
      else url.searchParams.set(key, value);
    });
    return url;
  }

  function setSection(section) {
    const normalized = String(section || "overview").toLowerCase();
    const domain = domainForSection(normalized);
    workspace.dataset.executiveSection = normalized;
    workspace.dataset.dashboardSection = normalized;
    workspace.dataset.dgDomain = domain;
    if (window.ESFECertifiedDashboard) window.ESFECertifiedDashboard.setActiveNavigation(domain);
    return normalized;
  }

  function refreshIcons() {
    if (window.lucide && typeof window.lucide.createIcons === "function") window.lucide.createIcons();
  }

  function showNotice(message, isError) {
    if (window.ESFEUI && typeof window.ESFEUI.toast === "function") {
      window.ESFEUI.toast({
        message: message || (isError ? "Action impossible." : "Action effectuée."),
        tone: isError ? "danger" : "success",
      });
      return;
    }
    const notice = document.createElement("div");
    notice.className = "fixed bottom-4 right-4 z-[70] max-w-sm rounded-ui-card border px-4 py-3 text-sm font-semibold shadow-ui-dropdown " + (isError ? "border-ui-danger/40 bg-ui-danger-soft text-ui-danger" : "border-ui-success/40 bg-ui-success-soft text-ui-success");
    notice.setAttribute("role", "status");
    notice.textContent = message || (isError ? "Action impossible." : "Action effectuée.");
    document.body.appendChild(notice);
    window.setTimeout(() => notice.remove(), 3600);
  }

  function syncContextLabel(branchId) {
    const select = document.getElementById("dg-branch-select");
    const option = select && Array.from(select.options).find((item) => item.value === String(branchId || ""));
    const label = branchId && option
      ? `Mode annexe — ${option.textContent.trim()}`
      : "Mode global — Toutes les annexes";
    document.dispatchEvent(new CustomEvent("esfe:dashboard-context-changed", { detail: { label } }));
  }

  function syncBranchOption(branch) {
    if (!branch || !branch.id || !branch.name) return;
    document.querySelectorAll("#dg-branch-select").forEach((select) => {
      let option = Array.from(select.options).find((item) => item.value === String(branch.id));
      if (branch.is_active === false) {
        if (option) option.remove();
        return;
      }
      if (!option) {
        option = new Option(branch.name, String(branch.id));
        select.add(option);
      } else {
        option.textContent = branch.name;
      }
      const globalOption = select.options[0];
      const ordered = Array.from(select.options).slice(1).sort((left, right) => left.text.localeCompare(right.text, "fr"));
      select.replaceChildren(globalOption, ...ordered);
    });
  }

  function emitDgDataChanged(topic) {
    document.body.dispatchEvent(new CustomEvent("esfe:data-changed", { bubbles: true, detail: { source: "dg", topic } }));
    if (topic) document.body.dispatchEvent(new CustomEvent(`esfe:${topic}-changed`, { bubbles: true, detail: { source: "dg" } }));
  }

  function requestSection(section, pushUrl, params) {
    const normalized = setSection(section);
    const domain = (params && params.domain) || domainForSection(normalized);
    const requestId = String(++workspaceRequestSequence);
    const requestParams = { ...(params || {}), domain, _workspace_request: requestId };
    const url = scopedUrl(sectionBase + normalized + "/", requestParams);
    workspace.dataset.workspaceRequestId = requestId;
    workspace.setAttribute("aria-busy", "true");
    if (pushUrl !== false) {
      const historyUrl = scopedUrl(dashboardUrl, { section: normalized, domain, ...(params || {}) });
      window.history.pushState({ section: normalized, domain }, "", historyUrl);
    }
    window.htmx.ajax("GET", url.toString(), { target: workspaceTarget, swap: "innerHTML" });
  }

  function requestDomain(domain) {
    const normalized = String(domain || "").toLowerCase();
    const section = defaultSectionByDomain[normalized] || "overview";
    requestSection(section, true, { domain: normalized });
  }

  function requestIdFrom(event) {
    const responseUrl = event.detail && event.detail.xhr && event.detail.xhr.responseURL;
    if (!responseUrl) return "";
    try {
      return new URL(responseUrl, window.location.origin).searchParams.get("_workspace_request") || "";
    } catch (_error) {
      return "";
    }
  }

  function isCurrentWorkspaceResponse(event) {
    const requestId = requestIdFrom(event);
    return !requestId || requestId === workspace.dataset.workspaceRequestId;
  }

  function dispatchOverlay(action, id) {
    window.dispatchEvent(new CustomEvent(`ui-overlay-${action}`, { detail: { id } }));
  }

  function prepareOverlay(target, title, label) {
    const content = document.querySelector(target);
    const heading = document.getElementById(`${title}-title`);
    if (heading) heading.textContent = label;
    if (content) {
      content.innerHTML = '<div class="grid min-h-40 place-items-center" role="status" aria-live="polite"><span class="inline-flex items-center gap-3 text-sm font-semibold text-ui-text-muted"><span class="h-5 w-5 animate-spin rounded-full border-2 border-ui-primary border-r-transparent" aria-hidden="true"></span>Chargement…</span></div>';
    }
  }

  function requestOverlay(rawUrl, target, overlayId, loadingLabel) {
    prepareOverlay(target, overlayId, loadingLabel);
    dispatchOverlay("open", overlayId);
    window.htmx.ajax("GET", scopedUrl(rawUrl).toString(), { target, swap: "innerHTML" });
  }

  function syncOverlayTitle(target, overlayId, fallback) {
    const title = target.querySelector("[data-overlay-title]");
    const heading = document.getElementById(`${overlayId}-title`);
    if (heading) heading.textContent = (title && title.dataset.overlayTitle) || fallback;
  }

  function canCloseOverlay(target) {
    const form = document.querySelector(`${target} form[data-dg-interactive-form]`);
    if (!form || form.dataset.dirty !== "true") return true;
    const discard = window.confirm("Des modifications non enregistrées seront perdues. Voulez-vous continuer ?");
    if (discard) form.dataset.dirty = "false";
    return discard;
  }

  window.dgShowSection = function (section) { requestSection(section, true); };
  window.dgOpenScopedSection = function (section, branchId) {
    if (!canCloseOverlay(drawerTarget) || !canCloseOverlay(modalTarget)) return;
    dispatchOverlay("close", "executive-drawer");
    dispatchOverlay("close", "executive-modal");
    syncContextLabel(branchId);
    requestSection(section, true, { scope_branch_id: branchId || null });
  };
  window.dgLoadSection = function (section) { requestSection(section, true); };
  window.dgShowDomain = requestDomain;
  window.dgRefreshSection = function (section) { requestSection(section || currentSection(), false); };
  window.dgRefreshCurrentSection = function () { requestSection(currentSection(), false); };
  window.dgOpenDrawer = function (rawUrl) {
    // A drawer is a drill-down surface, never a second layer above a modal.
    // Closing the modal first prevents stale focus traps and mixed content when
    // a user follows a detail link from a modal table.
    if (!canCloseOverlay(modalTarget)) return;
    dispatchOverlay("close", "executive-modal");
    requestOverlay(rawUrl, drawerTarget, "executive-drawer", "Chargement du détail");
  };
  window.dgCloseDrawer = function () {
    if (canCloseOverlay(drawerTarget)) dispatchOverlay("close", "executive-drawer");
  };
  window.dgOpenModal = function (rawUrl) {
    if (!canCloseOverlay(drawerTarget)) return;
    dispatchOverlay("close", "executive-drawer");
    requestOverlay(rawUrl, modalTarget, "executive-modal", "Chargement du formulaire");
  };
  window.dgCloseModal = function () {
    if (canCloseOverlay(modalTarget)) dispatchOverlay("close", "executive-modal");
  };
  window.dgShowNotice = showNotice;
  window.dgBuildScopedUrl = function (rawUrl, params) { return scopedUrl(rawUrl, params || {}); };
  window.dgGetCurrentSection = currentSection;

  window.dgHandleBranchChange = function (branchId) {
    syncContextLabel(branchId);
    requestSection(currentSection(), true, {
      domain: currentDomain(),
      scope_branch_id: branchId || null,
    });
  };
  window.dgHandleAcademicYearChange = function (yearId) {
    requestSection(currentSection(), true, {
      domain: currentDomain(),
      academic_year_id: yearId || null,
    });
  };
  window.dgHandlePeriodChange = function (period) {
    requestSection(currentSection(), true, {
      domain: currentDomain(),
      period: period || null,
    });
  };
  window.dgScheduleBranchChange = window.dgHandleBranchChange;
  window.dgScheduleClassChange = function (classId) {
    requestSection("schedule", true, { class_id: classId || null });
  };
  window.dgLoadScheduleWeek = function (weekStart) {
    requestSection("schedule", true, { week_start: weekStart || null });
  };
  window.dgExportCurrentSection = function () { window.location.assign(scopedUrl("/portal/dg/export/", { kind: currentSection() }).toString()); };

  function setFormSubmitting(form, submitting) {
    form.dataset.dgSubmitting = submitting ? "true" : "false";
    form.setAttribute("aria-busy", submitting ? "true" : "false");
    form.querySelectorAll('button[type="submit"]').forEach((button) => {
      if (submitting) {
        button.dataset.dgOriginalHtml = button.innerHTML;
        button.disabled = true;
        button.setAttribute("aria-disabled", "true");
        button.innerHTML = '<span class="inline-flex items-center gap-2"><span class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-r-transparent" aria-hidden="true"></span>Traitement…</span>';
      } else if (button.dataset.dgOriginalHtml) {
        button.disabled = false;
        button.removeAttribute("aria-disabled");
        button.innerHTML = button.dataset.dgOriginalHtml;
        delete button.dataset.dgOriginalHtml;
      }
    });
  }

  function setProgrammeStep(form, step) {
    const normalized = String(step) === "2" ? "2" : "1";
    form.querySelectorAll("[data-dg-programme-step]").forEach((panel) => {
      panel.classList.toggle("hidden", panel.dataset.dgProgrammeStep !== normalized);
    });
    form.querySelectorAll("[data-dg-programme-progress]").forEach((item) => {
      const active = item.dataset.dgProgrammeProgress === normalized;
      item.classList.toggle("border-ui-primary", active);
      item.classList.toggle("bg-ui-primary-soft", active);
      item.classList.toggle("text-ui-primary", active);
      item.classList.toggle("border-ui-border", !active);
      item.classList.toggle("bg-ui-surface", !active);
      item.classList.toggle("text-ui-text-muted", !active);
    });
    const currentStep = form.querySelector('input[name="form_step"]');
    if (currentStep) currentStep.value = normalized;
    refreshIcons();
  }

  window.dgProgrammeGoToStep = function (form, step) {
    if (!form) return;
    if (String(step) === "2") {
      const identityPanel = form.querySelector('[data-dg-programme-step="1"]');
      const invalidField = Array.from(identityPanel.querySelectorAll("input, select, textarea"))
        .find((field) => !field.disabled && !field.checkValidity());
      if (invalidField) {
        invalidField.reportValidity();
        return;
      }
    }
    setProgrammeStep(form, step);
  };

  window.dgSubmitProgrammeForm = function (form) {
    if (form.dataset.dgSubmitting === "true") return false;
    setFormSubmitting(form, true);
    fetch(scopedUrl(form.action).toString(), {
      method: "POST",
      body: new FormData(form),
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(async (response) => {
        const contentType = response.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
          return { response, data: await response.json() };
        }
        return { response, html: await response.text() };
      })
      .then(({ response, data, html }) => {
        if (html !== undefined) {
          const modal = document.querySelector(modalTarget);
          if (modal) {
            modal.innerHTML = html;
            syncOverlayTitle(modal, "executive-modal", "Formation institutionnelle");
            refreshIcons();
          }
          return;
        }
        showNotice(data.message, !response.ok || !data.ok);
        if (response.ok && data.ok) {
          form.dataset.dirty = "false";
          emitDgDataChanged(data.topic);
          if (data.close_modal) window.dgCloseModal();
          requestSection(currentSection(), false);
        }
      })
      .catch(() => showNotice("Impossible d’enregistrer la formation.", true))
      .finally(() => setFormSubmitting(form, false));
    return false;
  };

  let pendingProgrammeReference = null;

  function snapshotProgrammeForm(form) {
    const fields = {};
    Array.from(form.elements).forEach((field) => {
      if (!field.name || field.type === "file") return;
      fields[field.name] = field.type === "checkbox" ? field.checked : field.value;
    });
    return { fields, step: fields.form_step || "1" };
  }

  function restoreProgrammeForm(form, pending, reference) {
    Object.entries(pending.fields).forEach(([name, value]) => {
      const field = form.elements.namedItem(name);
      if (!field || typeof field === "object" && field.length) return;
      if (field.type === "checkbox") field.checked = Boolean(value);
      else field.value = value;
    });
    if (reference) {
      const target = form.elements.namedItem(reference.field);
      if (target) target.value = String(reference.id);
    }
    setProgrammeStep(form, pending.step);
  }

  function returnToProgrammeForm(reference) {
    if (!pendingProgrammeReference) return;
    const pending = pendingProgrammeReference;
    const params = new URLSearchParams({ modal: "programme_admin" });
    if (pending.fields.programme_id) params.set("programme_id", pending.fields.programme_id);
    fetch(scopedUrl(`${modalUrl}?${params.toString()}`).toString(), {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then((response) => response.text().then((html) => ({ response, html })))
      .then(({ response, html }) => {
        if (!response.ok) throw new Error();
        const modal = document.querySelector(modalTarget);
        if (!modal) return;
        modal.innerHTML = html;
        const programmeForm = modal.querySelector("form[data-dg-programme-form]");
        if (programmeForm) restoreProgrammeForm(programmeForm, pending, reference);
        pendingProgrammeReference = null;
        syncOverlayTitle(modal, "executive-modal", "Formation institutionnelle");
        refreshIcons();
      })
      .catch(() => showNotice("Impossible de revenir au formulaire de formation.", true));
  }

  window.dgOpenProgrammeReferenceForm = function (kind, form) {
    if (!form) return;
    pendingProgrammeReference = snapshotProgrammeForm(form);
    fetch(scopedUrl(`${modalUrl}?modal=programme_reference&kind=${encodeURIComponent(kind)}`).toString(), {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then((response) => response.text().then((html) => ({ response, html })))
      .then(({ response, html }) => {
        if (!response.ok) throw new Error();
        const modal = document.querySelector(modalTarget);
        if (!modal) return;
        modal.innerHTML = html;
        syncOverlayTitle(modal, "executive-modal", "Référentiel institutionnel");
        refreshIcons();
      })
      .catch(() => showNotice("Impossible d’ouvrir ce référentiel.", true));
  };

  window.dgReturnToProgrammeForm = function () {
    returnToProgrammeForm(null);
  };

  window.dgSubmitProgrammeReferenceForm = function (form) {
    if (form.dataset.dgSubmitting === "true") return false;
    setFormSubmitting(form, true);
    fetch(scopedUrl(form.action).toString(), {
      method: "POST",
      body: new FormData(form),
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(async (response) => {
        const contentType = response.headers.get("content-type") || "";
        return contentType.includes("application/json")
          ? { response, data: await response.json() }
          : { response, html: await response.text() };
      })
      .then(({ response, data, html }) => {
        if (html !== undefined) {
          const modal = document.querySelector(modalTarget);
          if (modal) {
            modal.innerHTML = html;
            refreshIcons();
          }
          return;
        }
        if (!response.ok || !data.ok) {
          showNotice(data.message || "Impossible de créer ce référentiel.", true);
          return;
        }
        showNotice(data.message, false);
        returnToProgrammeForm(data.reference);
      })
      .catch(() => showNotice("Impossible de créer ce référentiel.", true))
      .finally(() => setFormSubmitting(form, false));
    return false;
  };

  window.dgSubmitAction = function (form) {
    if (form.dataset.dgSubmitting === "true") return false;
    setFormSubmitting(form, true);
    fetch(scopedUrl(form.action).toString(), { method: "POST", body: new FormData(form), headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then((response) => response.json().then((data) => ({ response, data })))
      .then(({ response, data }) => {
        showNotice(data.message, !response.ok || !data.ok);
        if (response.ok && data.ok) {
          form.dataset.dirty = "false";
          syncBranchOption(data.branch);
          emitDgDataChanged(data.topic);
          if (data.close_modal) window.dgCloseModal();
          if (data.close_drawer || form.closest(drawerTarget)) window.dgCloseDrawer();
          requestSection(currentSection(), false);
        }
      })
      .catch(() => showNotice("Action impossible.", true))
      .finally(() => setFormSubmitting(form, false));
    return false;
  };
  window.dgConfirmExecutiveAction = function (form) {
    const params = new URLSearchParams(new FormData(form));
    params.set("modal", "executive_action");
    window.dgOpenModal(`${modalUrl}?${params.toString()}`);
    return false;
  };
  window.dgSubmitModalForm = function (form) {
    if (form.dataset.dgSubmitting === "true") return false;
    setFormSubmitting(form, true);
    fetch(scopedUrl(form.action).toString(), { method: form.method || "POST", body: new FormData(form), headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then((response) => response.text().then((html) => ({ response, html })))
      .then(({ response, html }) => {
        document.querySelector(modalTarget).innerHTML = html;
        syncOverlayTitle(document.querySelector(modalTarget), "executive-modal", "Décision exécutive");
        refreshIcons();
        if (response.ok) {
          form.dataset.dirty = "false";
          requestSection(currentSection(), false);
        }
      })
      .catch(() => showNotice("Impossible de soumettre le formulaire.", true))
      .finally(() => setFormSubmitting(form, false));
    return false;
  };
  window.dgSubmitCouponToggle = function (form) {
    if (form.dataset.dgSubmitting === "true") return false;
    setFormSubmitting(form, true);
    fetch(scopedUrl(form.action).toString(), { method: "POST", body: new FormData(form), headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then((response) => response.text().then((html) => ({ response, html })))
      .then(({ response, html }) => {
        if (!response.ok) throw new Error();
        requestSection("coupons", false);
        showNotice("Coupon mis à jour.");
      })
      .catch(() => showNotice("Action impossible.", true))
      .finally(() => setFormSubmitting(form, false));
    return false;
  };

  function renderDgCharts(root) {
    const scope = root || document;
    const charts = scope.querySelectorAll("[data-dg-chart]");
    if (!charts.length) return;
    if (window.Chart && window.ESFEUI && window.ESFEUI.charts) {
      window.ESFEUI.charts.render(scope);
      return;
    }
    charts.forEach((canvas) => {
      const fallback = document.createElement("p");
      fallback.className = "rounded-ui-button bg-ui-warning-soft p-3 text-sm font-semibold text-ui-warning";
      fallback.setAttribute("role", "status");
      fallback.textContent = "Le graphique est indisponible. Les données détaillées restent accessibles ci-dessous.";
      canvas.replaceWith(fallback);
    });
  }

  if (shellRoot) {
    shellRoot.addEventListener("click", (event) => {
      const item = event.target.closest("[data-ui-nav-item][data-nav-key]");
      if (!item || !dgDomains.has(item.dataset.navKey)) return;
      event.preventDefault();
      event.stopPropagation();
      requestDomain(item.dataset.navKey);
    }, true);
  }

  document.body.addEventListener("click", (event) => {
    const card = event.target.closest('[data-ui-core-action="stat-card"]');
    if (!card) return;
    const url = new URL(card.href, window.location.origin);
    const section = url.searchParams.get("section");
    if (url.pathname !== new URL(dashboardUrl, window.location.origin).pathname || !dgSections.has(section)) return;
    event.preventDefault();
    requestSection(section, true, { domain: url.searchParams.get("domain") || undefined });
  });

  document.body.addEventListener("htmx:beforeSwap", (event) => {
    if (event.detail.target !== workspace || isCurrentWorkspaceResponse(event)) return;
    // A fast second navigation wins. An older response must not overwrite it.
    event.preventDefault();
  });

  document.body.addEventListener("htmx:afterSwap", (event) => {
    if (event.detail.target === workspace) {
      if (!isCurrentWorkspaceResponse(event)) return;
      workspace.setAttribute("aria-busy", "false");
      const section = workspace.querySelector("[data-executive-section]");
      if (section) setSection(section.dataset.executiveSection);
    }
    if (event.detail.target && event.detail.target.matches(drawerTarget)) {
      syncOverlayTitle(event.detail.target, "executive-drawer", "Détail exécutif");
    }
    if (event.detail.target && event.detail.target.matches(modalTarget)) {
      syncOverlayTitle(event.detail.target, "executive-modal", "Décision exécutive");
    }
    refreshIcons();
    renderDgCharts(event.detail.target);
  });
  document.body.addEventListener("htmx:afterRequest", (event) => {
    if (event.detail.target !== workspace || !isCurrentWorkspaceResponse(event)) return;
    workspace.setAttribute("aria-busy", "false");
  });
  document.body.addEventListener("htmx:responseError", (event) => {
    if (event.detail.target === workspace) {
      if (!isCurrentWorkspaceResponse(event)) return;
      workspace.setAttribute("aria-busy", "false");
      showNotice("Le chargement de cette section a échoué.", true);
    }
    if (event.detail.target && (event.detail.target.matches(drawerTarget) || event.detail.target.matches(modalTarget))) {
      event.detail.target.innerHTML = '<div class="rounded-ui-card border border-ui-danger/40 bg-ui-danger-soft p-4 text-sm font-semibold text-ui-danger" role="alert">Le contenu demandé est indisponible. Fermez cette fenêtre puis réessayez.</div>';
      showNotice("Impossible de charger ce contenu.", true);
    }
  });
  document.body.addEventListener("input", (event) => {
    const form = event.target.closest("form[data-dg-interactive-form]");
    if (form) form.dataset.dirty = "true";
  });
  document.body.addEventListener("change", (event) => {
    const form = event.target.closest("form[data-dg-interactive-form]");
    if (form) form.dataset.dirty = "true";
  });
  window.addEventListener("popstate", () => {
    const params = new URL(window.location.href).searchParams;
    requestSection(params.get("section") || "overview", false, { domain: params.get("domain") || undefined });
  });

  requestSection(workspace.dataset.dgInitialSection || "overview", false);
})();
