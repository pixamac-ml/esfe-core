/* Grille de saisie Notes — Tabulator. Les calculs métier restent côté Django. */
(function () {
  "use strict";

  const registry = (window.ESFENotesTabulatorPayloads = window.ESFENotesTabulatorPayloads || {});
  const numeric = (value) => {
    const parsed = Number.parseFloat(String(value ?? "").replace(",", "."));
    return Number.isFinite(parsed) ? parsed : null;
  };
  const display = (value) => (value === null || value === undefined || Number.isNaN(value)
    ? "0,00"
    : Number(value).toFixed(2).replace(".", ","));

  function cellClass(cell, name) {
    cell.getElement().classList.add(name);
  }

  function clearCellState(cell) {
    const element = cell.getElement();
    element.classList.remove("notes-cell--saving", "notes-cell--saved", "notes-cell--error", "notes-cell--attention");
    element.removeAttribute("data-error");
  }

  function markCell(cell, state, message) {
    const element = cell.getElement();
    clearCellState(cell);
    cellClass(cell, `notes-cell--${state}`);
    if (message) {
      element.dataset.error = message;
      element.title = message;
    }
  }

  function responseMessage(xhr) {
    const raw = (xhr && xhr.responseText ? xhr.responseText : "").trim();
    if (!raw) return "La note n’a pas été enregistrée.";
    return new DOMParser().parseFromString(raw, "text/html").body.textContent.trim()
      || "La note n’a pas été enregistrée.";
  }

  function recalculate(row, payload) {
    const data = row.getData();
    const changes = {};
    let semesterCoefficient = 0;
    let semesterWeighted = 0;
    let requiredCredits = 0;
    let obtainedCredits = 0;
    let missing = false;

    payload.structure.forEach((ue) => {
      let ueCoefficient = 0;
      let ueWeighted = 0;
      let ueCredits = 0;
      let ueMissing = false;

      ue.ecs.forEach((ec) => {
        const note = numeric(data[`note_${ec.id}`]);
        const valid = note !== null && note >= 0 && note <= 20;
        const threshold = ec.coefficient <= 1 ? 8 : (ec.coefficient <= 2 ? 10 : 12);
        const noteCoefficient = valid ? note * ec.coefficient : 0;
        const credits = valid && note >= threshold ? ec.creditRequired : 0;
        changes[`notecoef_${ec.id}`] = display(noteCoefficient);
        changes[`credit_${ec.id}`] = display(credits);
        ueCoefficient += ec.coefficient;
        ueWeighted += noteCoefficient;
        ueCredits += credits;
        if (!valid) ueMissing = true;
      });

      const average = !ueMissing && ueCoefficient > 0 ? ueWeighted / ueCoefficient : null;
      changes[`ueavg_${ue.id}`] = average === null ? "—" : display(average);
      changes[`uenotecoef_${ue.id}`] = display(ueWeighted);
      changes[`uecredit_${ue.id}`] = display(ueCredits);
      semesterCoefficient += ue.coefficient;
      requiredCredits += ue.creditRequired;
      obtainedCredits += ueCredits;
      if (average === null) missing = true;
      else semesterWeighted += average * ue.coefficient;
    });

    changes.semavg = missing || semesterCoefficient === 0 ? "—" : display(semesterWeighted / semesterCoefficient);
    changes.sempct = display(requiredCredits ? (obtainedCredits / requiredCredits) * 100 : 0) + "%";
    changes.semcredit = display(obtainedCredits);
    row.update(changes);
  }

  function saveCell(root, payload, cell, ecId) {
    const row = cell.getRow();
    const data = row.getData();
    markCell(cell, "saving");
    const proxy = document.createElement("button");
    proxy.type = "button";
    proxy.hidden = true;
    proxy.className = "score-input";
    proxy.dataset.rowIndex = data.rowIndex;
    proxy.dataset.ecId = ecId;
    root.appendChild(proxy);

    const finish = (event) => {
      if (event.detail.elt !== proxy) return;
      proxy.remove();
      const xhr = event.detail.xhr;
      const body = (xhr && xhr.responseText ? xhr.responseText : "").trim();
      const otpRequired = body.includes("otp_request_id") || body.includes("grade_otp_modal");
      if (event.detail.successful && !otpRequired) {
        markCell(cell, "saved");
        window.setTimeout(() => {
          if (cell.getElement().isConnected) clearCellState(cell);
        }, 420);
      }
      else if (otpRequired) markCell(cell, "attention", "Validation OTP requise pour modifier cette note.");
      else markCell(cell, "error", responseMessage(xhr));
    };
    proxy.addEventListener("htmx:afterRequest", finish);
    proxy.addEventListener("htmx:sendError", (event) => {
      if (event.detail.elt !== proxy) return;
      proxy.remove();
      markCell(cell, "error", "Erreur réseau : la note n’a pas été enregistrée.");
    });
    window.htmx.ajax("POST", payload.saveUrl, {
      source: proxy,
      target: proxy,
      swap: "none",
      values: {
        enrollment_id: data.enrollmentId,
        ec_id: ecId,
        session_type: payload.sessionType,
        note: data[`note_${ecId}`] ?? "",
        live: "1",
      },
    });
  }

  function scheduleCellSave(root, payload, cell, ecId) {
    const row = cell.getRow();
    const key = `${row.getData().enrollmentId}:${ecId}`;
    root._notesSaveTimers = root._notesSaveTimers || new Map();
    const previousTimer = root._notesSaveTimers.get(key);
    if (previousTimer) window.clearTimeout(previousTimer);

    root._notesSaveTimers.set(key, window.setTimeout(() => {
      root._notesSaveTimers.delete(key);
      saveCell(root, payload, cell, ecId);
    }, 140));
  }

  function gradeColumn(payload, ec) {
    const field = `note_${ec.id}`;
    return {
      title: "Note",
      field,
      width: 84,
      hozAlign: "center",
      headerHozAlign: "center",
      editor: "number",
      editorParams: { min: 0, max: 20, step: 0.01, elementAttributes: { inputmode: "decimal", class: "notes-tabulator-input" } },
      editable: (cell) => payload.canEdit && cell.getRow().getData()[`editable_${ec.id}`] !== false,
      cellEdited: (cell) => {
        recalculate(cell.getRow(), payload);
        scheduleCellSave(cell.getTable().element.closest("[data-notes-tabulator-root]"), payload, cell, ec.id);
      },
    };
  }

  function readOnlyColumn(title, field, width, tone) {
    return { title, field, width, hozAlign: "center", headerHozAlign: "center", cssClass: tone || "" };
  }

  function buildColumns(payload) {
    const columns = [
      { title: "N°", field: "sequence", frozen: true, width: 54, hozAlign: "center", headerHozAlign: "center" },
      { title: "Nom", field: "lastName", frozen: true, minWidth: 160, widthGrow: 1.4, headerHozAlign: "left" },
      { title: "Prénoms", field: "firstName", frozen: true, minWidth: 160, widthGrow: 1.4, headerHozAlign: "left" },
    ];
    payload.structure.forEach((ue) => {
      const ecColumns = ue.ecs.map((ec) => ({
        title: ec.title,
        columns: [
          gradeColumn(payload, ec),
          readOnlyColumn("Note coef.", `notecoef_${ec.id}`, 68),
          readOnlyColumn("Crédits", `credit_${ec.id}`, 78),
        ],
      }));
      ecColumns.push({
        title: "Unité",
        columns: [
          readOnlyColumn("Moyenne", `ueavg_${ue.id}`, 88, "notes-unit"),
          readOnlyColumn("Note coef.", `uenotecoef_${ue.id}`, 88, "notes-unit"),
          readOnlyColumn("Crédits", `uecredit_${ue.id}`, 78, "notes-unit"),
        ],
      });
      columns.push({
        title: `${ue.code} — ${ue.title}`,
        columns: ecColumns,
      });
    });
    columns.push({
      title: "Résultat du semestre",
      columns: [
      readOnlyColumn("Moyenne", "semavg", 100, "notes-result"),
      readOnlyColumn("%", "sempct", 86, "notes-result"),
      readOnlyColumn("Crédits", "semcredit", 92, "notes-result"),
      ],
    });
    return columns;
  }

  function makeHeaderCell(track, className, columnStart, columnEnd, rowStart, rowEnd, label, value) {
    const cell = document.createElement("div");
    cell.className = `notes-academic-cell ${className}`;
    cell.style.gridColumn = `${columnStart} / ${columnEnd}`;
    cell.style.gridRow = `${rowStart} / ${rowEnd}`;
    if (label) {
      const text = document.createElement("span");
      text.textContent = label;
      cell.appendChild(text);
    }
    if (value !== undefined && value !== null) {
      const number = document.createElement("strong");
      number.textContent = value;
      cell.appendChild(number);
    }
    track.appendChild(cell);
  }

  function leafWidth(table, field, fallback) {
    const column = table.getColumn(field);
    return Math.round(column ? column.getWidth() : fallback);
  }

  function renderAcademicHeader(root, payload, table) {
    const students = root.querySelector("[data-notes-academic-students]");
    const track = root.querySelector("[data-notes-academic-track]");
    if (!students || !track) return;

    const studentWidths = [
      leafWidth(table, "sequence", 54),
      leafWidth(table, "lastName", 160),
      leafWidth(table, "firstName", 160),
    ];
    const studentsWidth = studentWidths.reduce((total, width) => total + width, 0);
    root.style.setProperty("--notes-students-width", `${studentsWidth}px`);
    students.replaceChildren();
    const studentsTrack = document.createElement("div");
    studentsTrack.className = "notes-academic-track";
    studentsTrack.style.gridTemplateColumns = studentWidths.map((width) => `${width}px`).join(" ");
    students.appendChild(studentsTrack);
    makeHeaderCell(studentsTrack, "notes-academic-cell--students-top", 1, 4, 1, 2, "UNITÉS / COMPÉTENCES");
    makeHeaderCell(studentsTrack, "notes-academic-cell--students-label", 1, 4, 2, 3, "MATIÈRES");
    makeHeaderCell(studentsTrack, "notes-academic-cell--students-label", 1, 4, 3, 4, "crédits requis");
    makeHeaderCell(studentsTrack, "notes-academic-cell--students-label", 1, 4, 4, 5, "coefficients");
    ["N°", "NOM", "PRÉNOMS"].forEach((label, index) => {
      makeHeaderCell(studentsTrack, "notes-academic-cell--student-leaf", index + 1, index + 2, 5, 6, label);
    });

    const widths = [];
    const blocks = [];
    payload.structure.forEach((ue) => {
      const subjects = ue.ecs.map((ec) => ({
        kind: "ec",
        title: ec.title,
        creditRequired: ec.creditRequired,
        coefficient: ec.coefficient,
        leaves: [
          { label: "Note", field: `note_${ec.id}`, fallback: 84 },
          { label: "Note coef.", field: `notecoef_${ec.id}`, fallback: 88 },
          { label: "Crédits obtenus", field: `credit_${ec.id}`, fallback: 78 },
        ],
      }));
      subjects.push({
        kind: "unit",
        title: "Unité",
        creditRequired: ue.creditRequired,
        coefficient: ue.coefficient,
        leaves: [
          { label: "Moyenne", field: `ueavg_${ue.id}`, fallback: 88 },
          { label: "Note coef.", field: `uenotecoef_${ue.id}`, fallback: 88 },
          { label: "Crédits obtenus", field: `uecredit_${ue.id}`, fallback: 78 },
        ],
      });
      blocks.push({ kind: "ue", title: `${ue.code} – ${ue.title}`, subjects });
    });
    const result = {
      kind: "result",
      title: "RÉSULTAT DU SEMESTRE",
      creditRequired: payload.structure.reduce((total, ue) => total + numeric(ue.creditRequired), 0),
      coefficient: payload.structure.reduce((total, ue) => total + numeric(ue.coefficient), 0),
      leaves: [
        { label: "MOYENNE", field: "semavg", fallback: 100 },
        { label: "POURCENTAGE", field: "sempct", fallback: 86 },
        { label: "CRÉDITS", field: "semcredit", fallback: 92 },
      ],
    };

    blocks.forEach((block) => block.subjects.forEach((subject) => subject.leaves.forEach((leaf) => widths.push(leafWidth(table, leaf.field, leaf.fallback)))));
    result.leaves.forEach((leaf) => widths.push(leafWidth(table, leaf.field, leaf.fallback)));
    track.replaceChildren();
    track.style.gridTemplateColumns = widths.map((width) => `${width}px`).join(" ");

    let position = 1;
    blocks.forEach((block) => {
      const blockStart = position;
      const blockEnd = position + (block.subjects.length * 3);
      makeHeaderCell(track, "notes-academic-cell--ue", blockStart, blockEnd, 1, 2, block.title);
      block.subjects.forEach((subject) => {
        const subjectStart = position;
        const subjectEnd = position + 3;
        makeHeaderCell(track, `notes-academic-cell--${subject.kind}`, subjectStart, subjectEnd, 2, 3, subject.title);
        makeHeaderCell(track, "notes-academic-cell--metric", subjectStart, subjectEnd, 3, 4, "", subject.creditRequired);
        makeHeaderCell(track, "notes-academic-cell--metric", subjectStart, subjectEnd, 4, 5, "", subject.coefficient);
        subject.leaves.forEach((leaf, index) => makeHeaderCell(track, "notes-academic-cell--leaf", subjectStart + index, subjectStart + index + 1, 5, 6, leaf.label));
        position = subjectEnd;
      });
    });
    const resultStart = position;
    const resultEnd = position + 3;
    makeHeaderCell(track, "notes-academic-cell--result", resultStart, resultEnd, 1, 3, result.title);
    makeHeaderCell(track, "notes-academic-cell--metric", resultStart, resultEnd, 3, 4, "", result.creditRequired);
    makeHeaderCell(track, "notes-academic-cell--metric", resultStart, resultEnd, 4, 5, "", result.coefficient);
    result.leaves.forEach((leaf, index) => makeHeaderCell(track, "notes-academic-cell--leaf", resultStart + index, resultStart + index + 1, 5, 6, leaf.label));

    const holder = root.querySelector(".tabulator-tableholder");
    if (!holder || holder.dataset.notesHeaderBound === "true") return;
    holder.dataset.notesHeaderBound = "true";
    holder.addEventListener("scroll", () => {
      track.style.transform = `translateX(${-holder.scrollLeft}px)`;
    }, { passive: true });
  }

  function mount(root) {
    if (!root || !window.Tabulator) return;
    const grid = root.querySelector("[data-notes-tabulator]");
    const payload = registry[root.dataset.notesTabulatorKey];
    if (!grid || !payload) return;
    if (root._notesTabulator) root._notesTabulator.destroy();
    root._notesTabulator = new window.Tabulator(grid, {
      data: payload.rows,
      columns: buildColumns(payload),
      index: "rowIndex",
      layout: "fitDataStretch",
      height: "100%",
      movableColumns: false,
      resizableRows: false,
      reactiveData: false,
      virtualDom: true,
      placeholder: "Aucun étudiant dans cette classe.",
      editTriggerEvent: "click",
    });
    root._notesTabulator.on("tableBuilt", () => {
      root._notesTabulator.getRows().forEach((row) => recalculate(row, payload));
      renderAcademicHeader(root, payload, root._notesTabulator);
    });
  }

  window.ESFENotesTabulator = { mount };
  document.addEventListener("DOMContentLoaded", () => document.querySelectorAll("[data-notes-tabulator-root]").forEach(mount));
  document.body.addEventListener("htmx:load", (event) => {
    const root = event.detail.elt.closest && event.detail.elt.closest("[data-notes-tabulator-root]");
    if (root) mount(root);
    event.detail.elt.querySelectorAll?.("[data-notes-tabulator-root]").forEach(mount);
  });
}());
