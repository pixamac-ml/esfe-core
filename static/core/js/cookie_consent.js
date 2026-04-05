(function () {
  "use strict";

  var COOKIE_NAME = "esfe_cookie_consent";
  var CONSENT_KEY = "cookie_consent";
  var ACCEPTED_COOKIE_NAME = "cookie_consent_accepted";
  var ACCEPTED_STORAGE_KEY = "cookie_consent_accepted";
  var INTERACTED_STORAGE_KEY = "cookie_interacted";

  function getCookie(name) {
    var prefix = name + "=";
    var parts = document.cookie ? document.cookie.split(";") : [];
    for (var i = 0; i < parts.length; i += 1) {
      var item = parts[i].trim();
      if (item.indexOf(prefix) === 0) {
        return decodeURIComponent(item.substring(prefix.length));
      }
    }
    return null;
  }

  function setCookie(name, value, days) {
    var expires = new Date();
    expires.setTime(expires.getTime() + days * 24 * 60 * 60 * 1000);
    document.cookie =
      name +
      "=" +
      encodeURIComponent(value) +
      ";expires=" +
      expires.toUTCString() +
      ";path=/;SameSite=Lax";
  }

  function parseConsent() {
    var raw = getCookie(COOKIE_NAME);
    if (!raw) {
      return null;
    }
    try {
      return JSON.parse(raw);
    } catch (e) {
      return null;
    }
  }

  function hasAcceptedFlag() {
    var storageValue = null;
    try {
      var explicitConsent = window.localStorage.getItem(CONSENT_KEY);
      if (explicitConsent === "true") {
        return true;
      }
      storageValue = window.localStorage.getItem(ACCEPTED_STORAGE_KEY);
    } catch (e) {
      storageValue = null;
    }

    var cookieValue = getCookie(ACCEPTED_COOKIE_NAME);
    return storageValue === "true" || cookieValue === "true";
  }

  function hasInteractedFlag() {
    try {
      return window.localStorage.getItem(INTERACTED_STORAGE_KEY) === "true";
    } catch (e) {
      return false;
    }
  }

  function setAcceptedFlag(value) {
    var normalized = value ? "true" : "false";
    try {
      if (value) {
        window.localStorage.setItem(CONSENT_KEY, "true");
      } else {
        window.localStorage.removeItem(CONSENT_KEY);
      }
      window.localStorage.setItem(ACCEPTED_STORAGE_KEY, normalized);
    } catch (e) {
      // Ignore localStorage failures.
    }
    setCookie(ACCEPTED_COOKIE_NAME, normalized, 180);
  }

  function activateDeferredScripts(consent) {
    var scripts = document.querySelectorAll("script[type='text/plain'][data-cookie-category]");
    for (var i = 0; i < scripts.length; i += 1) {
      var source = scripts[i];
      if (source.dataset.activated === "1") {
        continue;
      }
      var category = source.dataset.cookieCategory;
      if (!consent || !consent[category]) {
        continue;
      }

      var active = document.createElement("script");
      if (source.src) {
        active.src = source.src;
      } else {
        active.text = source.text || source.textContent || "";
      }
      if (source.async) {
        active.async = true;
      }
      if (source.defer) {
        active.defer = true;
      }

      source.dataset.activated = "1";
      source.parentNode.insertBefore(active, source.nextSibling);
    }
  }

  function init() {
    var root = document.getElementById("cookie-consent-root");
    if (!root) {
      return;
    }

    var endpoint = root.dataset.endpoint;
    var csrfToken = root.dataset.csrfToken;

    var banner = document.getElementById("cookie-banner");
    var modal = document.getElementById("cookie-modal");
    var manageButton = document.getElementById("cookie-manage-button");

    var acceptBtn = document.getElementById("cookie-accept-all");
    var rejectBtn = document.getElementById("cookie-reject-all");
    var customizeBtn = document.getElementById("cookie-open-customize");
    var saveBtn = document.getElementById("cookie-save-selection");
    var closeModalBtn = document.getElementById("cookie-close-modal");

    var analyticsInput = document.getElementById("cookie-analytics");
    var marketingInput = document.getElementById("cookie-marketing");

    function setBodyScrollLocked(locked) {
      if (!document.body) {
        return;
      }
      document.body.style.overflow = locked ? "hidden" : "";
    }

    function showBanner() {
      if (banner) {
        banner.classList.remove("hidden");
      }
    }

    function hideBanner() {
      if (banner) {
        banner.classList.add("hidden");
      }
    }

    function openModal() {
      if (!modal) {
        return;
      }
      modal.classList.remove("hidden");
      modal.setAttribute("aria-hidden", "false");
      setBodyScrollLocked(true);
    }

    function closeModal() {
      if (!modal) {
        return;
      }
      modal.classList.add("hidden");
      modal.setAttribute("aria-hidden", "true");
      setBodyScrollLocked(false);
    }

    function normalizeConsent(consent) {
      return {
        version: 1,
        necessary: true,
        analytics: !!(consent && consent.analytics),
        marketing: !!(consent && consent.marketing),
        status: (consent && consent.status) || "customized",
        timestamp: new Date().toISOString()
      };
    }

    function updateUIFromConsent(consent) {
      if (analyticsInput) {
        analyticsInput.checked = !!consent.analytics;
      }
      if (marketingInput) {
        marketingInput.checked = !!consent.marketing;
      }
      if (manageButton) {
        manageButton.classList.remove("hidden");
      }
      activateDeferredScripts(consent);
      document.dispatchEvent(new CustomEvent("cookies:updated", { detail: consent }));
    }

    function persistConsent(consent) {
      var safeConsent = normalizeConsent(consent);
      setCookie(COOKIE_NAME, JSON.stringify(safeConsent), 180);
      setAcceptedFlag(safeConsent.status === "accepted");
      try {
        window.localStorage.setItem(INTERACTED_STORAGE_KEY, "true");
      } catch (e) {
        // Ignore localStorage failures.
      }
      updateUIFromConsent(safeConsent);
      hideBanner();
      closeModal();

      if (!endpoint) {
        return Promise.resolve();
      }

      return fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken || "",
          "X-Requested-With": "XMLHttpRequest"
        },
        body: JSON.stringify(safeConsent),
        credentials: "same-origin"
      }).catch(function () {
        // Le cookie local sert de fallback si l'endpoint n'est pas joignable.
      });
    }

    if (acceptBtn) {
      acceptBtn.addEventListener("click", function () {
        persistConsent({ analytics: true, marketing: true, status: "accepted" });
      });
    }

    if (rejectBtn) {
      rejectBtn.addEventListener("click", function () {
        persistConsent({ analytics: false, marketing: false, status: "rejected" });
      });
    }

    if (customizeBtn) {
      customizeBtn.addEventListener("click", function () {
        openModal();
      });
    }

    if (saveBtn) {
      saveBtn.addEventListener("click", function () {
        persistConsent({
          analytics: !!(analyticsInput && analyticsInput.checked),
          marketing: !!(marketingInput && marketingInput.checked),
          status: "customized"
        });
      });
    }

    if (closeModalBtn) {
      closeModalBtn.addEventListener("click", closeModal);
    }

    if (modal) {
      modal.addEventListener("click", function (event) {
        if (event.target === modal) {
          closeModal();
        }
      });
    }

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        closeModal();
      }
    });

    if (manageButton) {
      manageButton.addEventListener("click", function () {
        var existing = parseConsent();
        if (existing) {
          updateUIFromConsent(existing);
        }
        openModal();
      });
    }

    window.openCookieSettings = function () {
      var existing = parseConsent();
      if (existing) {
        updateUIFromConsent(existing);
      }
      openModal();
    };

    var currentConsent = parseConsent();
    if (currentConsent) {
      hideBanner();
      updateUIFromConsent(normalizeConsent(currentConsent));
    } else if (hasAcceptedFlag()) {
      hideBanner();
      updateUIFromConsent(
        normalizeConsent({ analytics: true, marketing: true, status: "accepted" })
      );
    } else if (hasInteractedFlag()) {
      hideBanner();
    } else {
      showBanner();
      if (manageButton) {
        manageButton.classList.add("hidden");
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

