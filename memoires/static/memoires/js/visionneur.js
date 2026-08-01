(function () {
  "use strict";

  const conteneur = document.getElementById("memoire-visionneur");
  if (!conteneur) return;

  const nbPages = parseInt(conteneur.dataset.nbPages || "0", 10);
  const urlTemplate = conteneur.dataset.pageUrlTemplate;
  if (!nbPages || !urlTemplate) return;

  // --- Éléments DOM ---
  const image = document.getElementById("visionneur-image");
  const chargement = document.getElementById("visionneur-chargement");
  const erreur = document.getElementById("visionneur-erreur");
  const retryBtn = document.getElementById("retry-btn");
  const viewport = document.getElementById("visionneur-viewport");
  const pageInput = document.getElementById("page-input");
  const pageTotale = document.getElementById("page-totale");
  const boutonPrecedent = document.getElementById("page-precedente");
  const boutonSuivant = document.getElementById("page-suivante");
  const zoomIn = document.getElementById("zoom-in");
  const zoomOut = document.getElementById("zoom-out");
  const zoomReset = document.getElementById("zoom-reset");
  const zoomLevel = document.getElementById("zoom-level");
  const progressBar = document.getElementById("visionneur-progress-bar");
  const fullscreenBtn = document.getElementById("fullscreen-btn");
  const toggleThumbnails = document.getElementById("toggle-thumbnails");
  const toggleThumbnailsDesktop = document.getElementById("toggle-thumbnails-desktop");
  const thumbnailsSidebar = document.getElementById("thumbnails-sidebar");
  const thumbnailsContainer = document.getElementById("thumbnails-container");
  const thumbnailsMobilePanel = document.getElementById("thumbnails-mobile-panel");
  const thumbnailsMobileContainer = document.getElementById("thumbnails-mobile-container");
  const closeThumbnailsMobile = document.getElementById("close-thumbnails-mobile");

  // --- État ---
  let pageActuelle = 1;
  let zoomActuel = 100;
  const ZOOM_MIN = 50;
  const ZOOM_MAX = 250;
  const ZOOM_STEP = 10;
  const cachePreload = new Set();
  let thumbnailsVisible = true;
  let chargementEnCours = false;
  let dernierePageChargee = 0;

  // --- Utilitaires ---
  function urlPage(numero) {
    return urlTemplate.replace("999999", String(numero));
  }

  function clampZoom(val) {
    return Math.min(Math.max(val, ZOOM_MIN), ZOOM_MAX);
  }

  function majProgression() {
    const pct = Math.round((pageActuelle / nbPages) * 100);
    progressBar.style.width = pct + "%";
    progressBar.setAttribute("aria-valuenow", pageActuelle);
  }

  function majBoutons() {
    boutonPrecedent.disabled = pageActuelle <= 1;
    boutonSuivant.disabled = pageActuelle >= nbPages;
    pageInput.value = pageActuelle;
    pageInput.max = nbPages;
    zoomIn.disabled = zoomActuel >= ZOOM_MAX;
    zoomOut.disabled = zoomActuel <= ZOOM_MIN;
    zoomLevel.textContent = zoomActuel + "%";
  }

  function majImageZoom() {
    const scale = zoomActuel / 100;
    image.style.transform = "scale(" + scale + ")";
  }

  function majThumbnailActive() {
    // Desktop
    thumbnailsContainer.querySelectorAll("[data-thumb-page]").forEach(function (el) {
      const isActive = parseInt(el.dataset.thumbPage) === pageActuelle;
      el.classList.toggle("ring-2", isActive);
      el.classList.toggle("ring-primary-500", isActive);
      el.classList.toggle("ring-offset-1", isActive);
    });
    // Mobile
    thumbnailsMobileContainer.querySelectorAll("[data-thumb-page]").forEach(function (el) {
      const isActive = parseInt(el.dataset.thumbPage) === pageActuelle;
      el.classList.toggle("ring-2", isActive);
      el.classList.toggle("ring-primary-500", isActive);
      el.classList.toggle("ring-offset-1", isActive);
    });
    // Scroll thumbnail active into view
    var activeThumb = thumbnailsContainer.querySelector("[data-thumb-page='" + pageActuelle + "']");
    if (activeThumb) {
      activeThumb.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }

  // --- Chargement de page ---
  function afficherPage(numero, force) {
    if (chargementEnCours && !force) return;
    var target = Math.min(Math.max(numero, 1), nbPages);
    if (target === dernierePageChargee && !force) {
      return;
    }

    pageActuelle = target;
    chargementEnCours = true;

    chargement.classList.remove("hidden");
    erreur.classList.add("hidden");
    image.classList.add("hidden");

    var nouvelleImage = new Image();
    nouvelleImage.onload = function () {
      image.src = nouvelleImage.src;
      image.classList.remove("hidden");
      chargement.classList.add("hidden");
      chargementEnCours = false;
      dernierePageChargee = pageActuelle;
      majBoutons();
      majProgression();
      majThumbnailActive();
      precharger(pageActuelle + 1);
      if (pageActuelle > 1) precharger(pageActuelle - 1);
    };
    nouvelleImage.onerror = function () {
      chargement.classList.add("hidden");
      erreur.classList.remove("hidden");
      chargementEnCours = false;
    };
    nouvelleImage.src = urlPage(pageActuelle);
  }

  // --- Préchargement ---
  function precharger(numero) {
    if (numero < 1 || numero > nbPages || cachePreload.has(numero)) return;
    cachePreload.add(numero);
    var img = new Image();
    img.src = urlPage(numero);
  }

  // --- Miniatures ---
  function creerThumbnail(numero, target) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.dataset.thumbPage = numero;
    btn.setAttribute("aria-label", "Page " + numero);
    btn.className = "relative w-full aspect-[3/4] rounded-lg overflow-hidden border border-slate-200 bg-white transition-all duration-200 hover:border-primary-300 hover:shadow-sm focus:outline-none focus:ring-2 focus:ring-primary-300";

    var img = document.createElement("img");
    img.src = urlPage(numero);
    img.alt = "Miniature page " + numero;
    img.loading = "lazy";
    img.className = "w-full h-full object-cover";
    btn.appendChild(img);

    var label = document.createElement("span");
    label.className = "absolute bottom-0 inset-x-0 text-[9px] font-medium text-center bg-gradient-to-t from-black/50 to-transparent text-white py-0.5";
    label.textContent = numero;
    btn.appendChild(label);

    btn.addEventListener("click", function () {
      afficherPage(numero, true);
    });

    return btn;
  }

  function genererThumbnails() {
    thumbnailsContainer.innerHTML = "";
    thumbnailsMobileContainer.innerHTML = "";
    for (var i = 1; i <= nbPages; i++) {
      thumbnailsContainer.appendChild(creerThumbnail(i));
      thumbnailsMobileContainer.appendChild(creerThumbnail(i));
    }
  }

  // --- Zoom ---
  function setZoom(val) {
    zoomActuel = clampZoom(val);
    majImageZoom();
    majBoutons();
  }

  // --- Événements ---
  boutonPrecedent.addEventListener("click", function () {
    if (pageActuelle > 1) afficherPage(pageActuelle - 1, true);
  });

  boutonSuivant.addEventListener("click", function () {
    if (pageActuelle < nbPages) afficherPage(pageActuelle + 1, true);
  });

  pageInput.addEventListener("change", function () {
    var val = parseInt(this.value, 10);
    if (!isNaN(val) && val >= 1 && val <= nbPages) {
      afficherPage(val, true);
    } else {
      this.value = pageActuelle;
    }
  });

  pageInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      var val = parseInt(this.value, 10);
      if (!isNaN(val) && val >= 1 && val <= nbPages) {
        afficherPage(val, true);
      } else {
        this.value = pageActuelle;
      }
    }
  });

  zoomIn.addEventListener("click", function () {
    setZoom(zoomActuel + ZOOM_STEP);
  });

  zoomOut.addEventListener("click", function () {
    setZoom(zoomActuel - ZOOM_STEP);
  });

  zoomReset.addEventListener("click", function () {
    setZoom(100);
  });

  // Zoom molette
  viewport.addEventListener("wheel", function (e) {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      var delta = e.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP;
      setZoom(zoomActuel + delta);
    }
  }, { passive: false });

  // Plein écran
  fullscreenBtn.addEventListener("click", function () {
    if (!document.fullscreenElement) {
      conteneur.requestFullscreen().catch(function () {});
    } else {
      document.exitFullscreen();
    }
  });

  document.addEventListener("fullscreenchange", function () {
    var icon = fullscreenBtn.querySelector("[data-lucide]");
    if (document.fullscreenElement) {
      icon.setAttribute("data-lucide", "minimize");
    } else {
      icon.setAttribute("data-lucide", "maximize");
    }
    if (typeof lucide !== "undefined") lucide.createIcons();
  });

  // Miniatures desktop toggle
  function toggleSidebar() {
    thumbnailsVisible = !thumbnailsVisible;
    thumbnailsSidebar.classList.toggle("hidden", !thumbnailsVisible);
    thumbnailsSidebar.classList.toggle("flex", thumbnailsVisible);
  }

  if (toggleThumbnailsDesktop) {
    toggleThumbnailsDesktop.addEventListener("click", toggleSidebar);
  }

  // Miniatures mobile toggle
  if (toggleThumbnails) {
    toggleThumbnails.addEventListener("click", function () {
      thumbnailsMobilePanel.classList.remove("hidden");
    });
  }

  if (closeThumbnailsMobile) {
    closeThumbnailsMobile.addEventListener("click", function () {
      thumbnailsMobilePanel.classList.add("hidden");
    });
  }

  thumbnailsMobilePanel.addEventListener("click", function (e) {
    if (e.target === thumbnailsMobilePanel) {
      thumbnailsMobilePanel.classList.add("hidden");
    }
  });

  // Retry
  if (retryBtn) {
    retryBtn.addEventListener("click", function () {
      afficherPage(pageActuelle, true);
    });
  }

  // --- Navigation clavier ---
  function isInputFocused() {
    var el = document.activeElement;
    if (!el) return false;
    var tag = el.tagName.toLowerCase();
    return tag === "input" || tag === "textarea" || tag === "select" || el.isContentEditable;
  }

  document.addEventListener("keydown", function (e) {
    if (isInputFocused()) return;

    switch (e.key) {
      case "ArrowLeft":
        e.preventDefault();
        if (pageActuelle > 1) afficherPage(pageActuelle - 1, true);
        break;
      case "ArrowRight":
        e.preventDefault();
        if (pageActuelle < nbPages) afficherPage(pageActuelle + 1, true);
        break;
      case " ":
        e.preventDefault();
        if (pageActuelle < nbPages) afficherPage(pageActuelle + 1, true);
        break;
      case "Escape":
        if (document.fullscreenElement) {
          document.exitFullscreen();
        }
        if (!thumbnailsMobilePanel.classList.contains("hidden")) {
          thumbnailsMobilePanel.classList.add("hidden");
        }
        break;
      case "Home":
        e.preventDefault();
        afficherPage(1, true);
        break;
      case "End":
        e.preventDefault();
        afficherPage(nbPages, true);
        break;
      case "+":
      case "=":
        if (e.ctrlKey || e.metaKey) {
          e.preventDefault();
          setZoom(zoomActuel + ZOOM_STEP);
        }
        break;
      case "-":
        if (e.ctrlKey || e.metaKey) {
          e.preventDefault();
          setZoom(zoomActuel - ZOOM_STEP);
        }
        break;
      case "0":
        if (e.ctrlKey || e.metaKey) {
          e.preventDefault();
          setZoom(100);
        }
        break;
    }
  });

  // --- Anti-copie ---
  ["contextmenu", "copy", "dragstart", "selectstart"].forEach(function (evt) {
    conteneur.addEventListener(evt, function (e) {
      e.preventDefault();
    });
  });

  // --- Initialisation ---
  genererThumbnails();
  setZoom(100);
  afficherPage(1, true);
})();
