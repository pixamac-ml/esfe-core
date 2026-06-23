# Prompt Claude Code — Rendre les dashboards back-office d'ESFé Core instantanés

> **À coller dans Claude Code, travail dans le dépôt ESFé Core.**
> **Objectif :** rendre **uniquement les dashboards back-office** instantanés (navigation sans rechargement de page). **NE PAS toucher à la vitrine** (pages publiques / marketing).
> **Cadre qualité :** refactorisation propre, niveau production (v1), **aucun hack**, **aucune régression**. Travail **incrémental** : un dashboard pilote validé, puis déploiement aux autres.
> **Important :** la vitesse vient de la **séparation du shell + `hx-boost`**, PAS d'une nouvelle librairie. **Ne pas introduire Django Cotton ni Tungsten UI** dans cette tâche.

---

## 0. Contexte déjà constaté (à vérifier dans le dépôt, mais c'est l'état actuel)

- HTMX 1.9.10, Alpine 3.13.5 (+ intersect) et `django_htmx` (middleware actif) sont **déjà en place et très utilisés**.
- Le **CSRF est déjà géré** globalement via `hx-headers='{"X-CSRFToken": "..."}'` sur le `<body>` de `templates/base.html`. **À conserver.**
- Il existe déjà un « **ESFE OPTIMISTIC ENGINE** » (overlays, spinners, toasts, désactivation des boutons) + un système de toast + des events HTMX globaux dans `templates/base.html`. **À conserver** (réutiliser dans le nouveau shell).
- **Problèmes identifiés (causes de la lenteur) :**
  1. **Aucun `hx-boost`** dans le projet → chaque clic = rechargement complet de page.
  2. **Les dashboards back-office étendent `templates/base.html`**, le **shell vitrine**. Ils re-chargent donc à chaque navigation : AOS, les FAB sociaux/assistant flottants, la navbar publique, le footer, le consent cookies, et **~9 ressources externes en CDN** (unpkg, cdnjs, Google Fonts).
  3. **`<meta name="htmx-config" content='{"historyCacheSize": 0}'>`** → même le bouton retour refait tout.
  4. **AOS** auto-tague et anime tout le `main` à chaque chargement (sélecteur `[class*="rounded-"]`, etc.) → fondus de 360–520 ms qui donnent une impression de lenteur.
- **Contrainte réseau (Mali) :** chaque appel CDN par page est une vraie taxe de latence. Les libs doivent être **auto-hébergées et mises en cache**.

---

## 1. Périmètre EXACT (ne pas déborder)

**À migrer (dashboards back-office uniquement)** — repérer les templates de ces espaces et eux seuls :
- `accounts/templates/accounts/dashboard/…`
- `superadmin/templates/superadmin/…`
- `academic_cycle/templates/academic_cycle/{dg,it,manager,staff,student}/…`
- `students/…`, `secretary/…`, `portal/…` (parties back-office)
- `ui/templates/informaticien/…` (panneaux IT)
- tout autre dashboard de rôle (directeur des études, enseignant, étudiant, secrétaire, manager, IT, superadmin).

**À NE PAS toucher (vitrine) :** `core`, `marketing`, `news`, `blog`, `formations`, `community`, page d'accueil, et toutes les pages publiques qui étendent `templates/base.html`. Elles **restent** sur `base.html` inchangé.

> Méthode de repérage : `grep -rln 'extends "base.html"'` puis **ne migrer que les templates de dashboard** de la liste ci-dessus. En cas de doute sur un template, **demander avant de migrer**.

---

## 2. Étape 1 — Créer un shell applicatif épuré `templates/base_app.html`

Nouveau layout dédié aux dashboards, **séparé** de `base.html`.

**À CONSERVER (repris de base.html) :**
- `<meta htmx-config>` mais avec **`historyCacheSize` ≥ 10** (et non 0).
- Le `hx-headers` CSRF sur le `<body>`.
- L'**ESFE OPTIMISTIC ENGINE**, le système de **toast**, les events HTMX globaux (loader), l'init Lucide.
- La connexion **WebSocket notifications** (mais voir §3 : elle vivra dans le shell persistant et se connectera **une seule fois**).
- Les blocs Django (`title`, `extra_head`, `content`, `extra_scripts`…) avec **les mêmes noms** que dans `base.html`, pour minimiser les changements dans les templates enfants.

**À RETIRER (poids vitrine, inutile en back-office) :**
- AOS (CSS + JS + script d'auto-tagging).
- Les FAB sociaux + bouton assistant flottant + bouton scroll-top.
- La navbar publique (`{% component "navbar" %}`) et le footer public (`{% component "footer" %}`).
- Le bandeau cookies public (le back-office connecté n'en a pas besoin).

**Assets :** charger HTMX, Alpine (+intersect), Lucide et Font Awesome **depuis `static/` auto-hébergé**, pas depuis les CDN (cf. §4).

---

## 3. Étape 2 — Shell persistant + navigation boostée

1. **Structure persistante** dans `base_app.html` : la **sidebar** et la **topbar** sont DANS le shell, **hors** de la zone qui change. Une seule zone de contenu :
   ```html
   <main id="app-main">{% block content %}{% endblock %}</main>
   ```
2. **Boost de la navigation interne** : sur le conteneur de navigation du dashboard (sidebar/topbar), activer :
   ```html
   hx-boost="true"
   hx-target="#app-main"
   hx-select="#app-main"
   hx-swap="innerHTML show:window:top"
   hx-push-url="true"
   ```
   → seul `#app-main` est échangé ; sidebar, topbar, assets, WebSocket **persistent**. Navigation instantanée.
3. **Gestion du `<title>`/`<head>`** lors des swaps boostés : utiliser l'extension HTMX **`head-support`** (ou, à défaut, mettre à jour le `<title>` via le contenu renvoyé), pour que le titre de page change correctement.
4. **Historique** : `historyCacheSize` ≥ 10 → retour/avance instantanés.

> **Approche recommandée pour la v1 (faible risque, déploiement rapide) :** `hx-boost` + `hx-select="#app-main"` extrait la zone de contenu de la **page complète** renvoyée → **aucun changement de vue nécessaire**, on gagne déjà tout (pas de reload document, pas de re-fetch des assets, pas de re-scan AOS, pas de reconnexion WebSocket).
> **Optimisation ultérieure (vues lourdes uniquement) :** renvoyer un **fragment** quand `request.htmx` est vrai (django-htmx est déjà là) — `{% if request.htmx %}` rendre seulement le bloc contenu, sinon la page complète. À faire seulement là où le rendu serveur est coûteux.

---

## 4. Étape 3 — Auto-héberger les libs + cache long

- Rapatrier dans `static/` : **HTMX, Alpine + intersect, Lucide, Font Awesome**, et les **polices** (ou au minimum mettre des en-têtes de cache lointains + `preconnect` si on garde Google Fonts).
- Servir via **WhiteNoise** (ou la config statique du projet) avec **hashing/versioning** et cache long.
- Résultat : avec le boost, ces fichiers se chargent **une fois par session**, plus à chaque navigation. Gain majeur en latence (important au Mali).

---

## 5. Étape 4 — Préchargement + ré-inits scopées

- Ajouter l'extension HTMX **`preload`** et mettre `preload` sur les **liens de la sidebar** → la page suivante est récupérée au survol/`mousedown` (clic perçu comme instantané).
- **Scoper les ré-initialisations** au fragment échangé : sur `htmx:afterSwap`, ré-initialiser Lucide (et tout widget) **uniquement sur `evt.detail.target`**, pas sur tout le document.
- Ne PAS réintroduire AOS dans les dashboards.

---

## 6. Garde-fous (à respecter impérativement)

- Mettre **`hx-boost="false"`** sur : liens externes, téléchargements, et le **visionneur de mémoires** (sinon on casse ces comportements).
- Ne pas dupliquer le HTML : si on passe au rendu de fragments (§3 optimisation), le **même partial** sert la page complète et la réponse HTMX (`{% include %}`).
- **Sécurité inchangée** : chaque vue/endpoint garde ses contrôles d'auth/permissions. Le boost ne contourne rien.
- **Ne pas** ajouter de nouvelle dépendance UI (Cotton/Tungsten) pour cette tâche.
- **Ne pas** modifier le comportement des pages publiques.

---

## 7. Étape 5 — Backend (pour que l'instantané soit réel)

Sur le dashboard pilote choisi :
- Profiler la vue ; corriger les **N+1** avec `select_related` / `prefetch_related`.
- Mettre du **cache de fragments** sur les blocs stables (cartes de stats) si pertinent.
- Un front instantané ne compense pas une vue lente : valider que la réponse serveur est rapide.

---

## 8. Méthode de travail (incrémentale, obligatoire)

1. Créer `base_app.html` + auto-hébergement des libs.
2. **Migrer UN dashboard pilote** (le plus simple, ou celui qui gêne le plus) : changer `{% extends "base.html" %}` → `{% extends "base_app.html" %}`, mettre le contenu dans `#app-main`, activer boost + preload.
3. **Valider** : navigation instantanée, aucune régression, WebSocket/notifs OK, titres OK, pas d'erreur console.
4. **Décliner** ensuite aux autres dashboards (un par un, ou par lot homogène), puis au superadmin.
5. À chaque étape : expliquer l'impact technique avant de modifier, garder le code cohérent avec l'existant.

---

## 9. Critères d'acceptation (definition of done)

- [ ] `base_app.html` épuré créé, séparé de `base.html` (vitrine intacte).
- [ ] Dashboards back-office migrés vers `base_app.html`.
- [ ] Navigation entre écrans de dashboard **sans rechargement** (seul `#app-main` change).
- [ ] Sidebar/topbar/WebSocket **persistants** (pas de reconnexion à chaque clic).
- [ ] Libs **auto-hébergées** et mises en cache (plus de CDN par page).
- [ ] AOS retiré des dashboards ; ré-inits scopées au fragment.
- [ ] `historyCacheSize` ≥ 10 ; retour/avance instantanés.
- [ ] `preload` actif sur la navigation.
- [ ] Garde-fous respectés (boost désactivé sur liens externes/téléchargements/visionneur mémoires ; titres de page corrects).
- [ ] CSRF + optimistic engine + toasts toujours fonctionnels.
- [ ] **Zéro régression** sur la vitrine.

---

## 10. Note pour plus tard (hors périmètre de cette tâche)

Pour la **v1**, une fois l'instantané en place, **Django Cotton** pourra servir à factoriser proprement les composants des dashboards (maintenabilité / DRY) — c'est une amélioration **de structure**, pas de vitesse, et **optionnelle**. **Tungsten UI : à éviter** (paquet immature). Aucune de ces deux libs ne participe à l'instantanéité.
