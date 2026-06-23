(function () {
  "use strict";

  const conteneur = document.getElementById("memoire-visionneur");
  if (!conteneur) return;

  const nbPages = parseInt(conteneur.dataset.nbPages || "0", 10);
  const urlTemplate = conteneur.dataset.pageUrlTemplate;
  if (!nbPages || !urlTemplate) return;

  const image = document.getElementById("visionneur-image");
  const chargement = document.getElementById("visionneur-chargement");
  const compteur = document.getElementById("page-courante");
  const boutonPrecedent = document.getElementById("page-precedente");
  const boutonSuivant = document.getElementById("page-suivante");

  let pageActuelle = 1;
  const cachePreload = new Set();

  function urlPage(numero) {
    return urlTemplate.replace("999999", String(numero));
  }

  function precharger(numero) {
    if (numero < 1 || numero > nbPages || cachePreload.has(numero)) return;
    cachePreload.add(numero);
    const img = new Image();
    img.src = urlPage(numero);
  }

  function afficherPage(numero) {
    pageActuelle = Math.min(Math.max(numero, 1), nbPages);

    chargement.classList.remove("hidden");
    image.classList.add("hidden");

    const nouvelleImage = new Image();
    nouvelleImage.onload = function () {
      image.src = nouvelleImage.src;
      image.classList.remove("hidden");
      chargement.classList.add("hidden");
    };
    nouvelleImage.src = urlPage(pageActuelle);

    compteur.textContent = String(pageActuelle);
    boutonPrecedent.disabled = pageActuelle <= 1;
    boutonSuivant.disabled = pageActuelle >= nbPages;

    precharger(pageActuelle + 1);
  }

  boutonPrecedent.addEventListener("click", function () {
    afficherPage(pageActuelle - 1);
  });
  boutonSuivant.addEventListener("click", function () {
    afficherPage(pageActuelle + 1);
  });

  // Anti-copie : on dissuade, sans prétendre bloquer une capture d'écran.
  ["contextmenu", "copy", "dragstart", "selectstart"].forEach(function (evt) {
    conteneur.addEventListener(evt, function (e) {
      e.preventDefault();
    });
  });

  afficherPage(1);
})();
