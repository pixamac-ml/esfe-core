# Prompt Claude Code — Refonte totale du dashboard Surveillant Général (ESFé Core)

> **À coller dans Claude Code (dépôt ESFé Core).**
> **Mission : refactoring complet + refonte totale** du dashboard du **Surveillant Général** (espace « supervisor »), pour qu'il soit **instantané, fluide, propre et professionnel**.
> **Cadre qualité :** niveau production (v1), **aucun hack**, **aucune régression**, **aucune section qui s'affiche mal ou se comporte mal**. Frontières entre applications **strictement respectées**.
> **Travail incrémental** : on refait cet écran proprement, on valide, on n'éparpille pas.

---

## 0. Stack imposée (ne pas dévier)

| Brique | Décision |
|---|---|
| Tailwind | **Local / compilé uniquement.** **SUPPRIMER le Play CDN** (`<script src="https://cdn.tailwindcss.com">`). |
| Réactivité / navigation | **HTMX** (fragments + `hx-push-url` + `preload`). |
| UI locale | **Alpine.js** (drawer, dropdowns) — **état éphémère seulement**, une seule source de vérité. |
| Composants | **django-cotton** (componentiser panneaux/cartes/drawer). |
| ❌ Interdits sur ce chantier | **DaisyUI** (ne pas mélanger deux design systems), **django-components**, **Tungsten UI**, **tout CDN d'assets**. |

Assets HTMX / Alpine / Tailwind / icônes : **auto-hébergés en local**, mis en cache.

---

## 1. À faire en premier — inspecter

1. Lire le dashboard actuel : `templates/portal/staff/supervisor_dashboard.html` et tous les partials de `templates/portal/staff/supervisor/partials/`.
2. Lire les vues : `portal/views/views.py` (≈234 Ko — la vue `supervisor_workflow_workspace` y est noyée), `portal/views/supervisor_cases.py`, et `portal/urls.py` (routes `accounts_portal:supervisor_workflow_workspace`, `supervisor_cases_workspace`).
3. Repérer le shell `base_app.html` s'il a déjà été créé (chantier dashboards instantanés) ; sinon le créer selon ce prompt.
4. **Respecter les conventions du dépôt.** En cas de conflit, l'existant l'emporte — signaler.

---

## 2. Diagnostic à corriger (constaté dans le code)

- `{% extends "base.html" %}` (shell **vitrine**) avec blocs publics vidés à la main = hack.
- **Tailwind Play CDN chargé en plus du Tailwind compilé** → double Tailwind, compilation navigateur, lenteur. **À supprimer.**
- **Deux mécanismes de chargement** : `htmx.ajax(...)` pour les panneaux **vs** `fetch()` brut pour le drawer. → unifier sur HTMX.
- **État du drawer dupliqué** : manipulation DOM directe (`sgOpenDrawer/sgCloseDrawer`, `style.transform`) **et** `drawerOpen` Alpine, fonctions redéfinies deux fois. → une seule source de vérité.
- **Routeur Alpine maison** (`supervisorFlow()` : `go/reload/section/classId`) qui réinvente HTMX **sans URL** → retour navigateur et rafraîchissement cassent la vue. → remplacer par HTMX + `hx-push-url`.
- **Panneaux morts en double** : la génération `_strict` est vivante (incluse dans `workflow_workspace.html`), les anciens (`panel_attendance`, `panel_courses`, `panel_overview`, `panel_today`, `panel_alerts`…) ne sont inclus nulle part. → supprimer les morts.
- **Backend en vrac** : logique surveillant noyée dans `views.py` (234 Ko). → extraire.

---

## 3. Architecture cible

**Principe : un seul shell, un seul mécanisme, une URL qui suit.**

1. **Shell `base_app.html`** (épuré, zéro vitrine, Tailwind compilé local, HTMX + Alpine + icônes en local). Le dashboard surveillant l'étend.
2. **Layout conservé (il est sain)** : sidebar persistante + sélecteur de classe + zone de contenu unique `#supervisor-workspace` + drawer de détail. Sidebar/topbar **hors** de la zone échangée.
3. **Navigation 100 % HTMX** : chaque entrée de la sidebar = lien `hx-get="{% url 'accounts_portal:supervisor_workflow_workspace' %}?section=…&class_id=…"`, `hx-target="#supervisor-workspace"`, `hx-push-url="true"`, `preload`, `hx-indicator`. **Supprimer** le routeur Alpine `go/reload`.
4. **Sélecteur de classe** : déclenche `hx-get` (via `hx-trigger="change"` + `hx-include`), met à jour l'URL (`class_id`).
5. **Drawer unifié** : contenu chargé en **HTMX** (`hx-target="#supervisor-drawer-content"`) ; **Alpine gère uniquement l'ouverture/fermeture** (`x-data="{ open:false }"`, `x-show`, transitions). Le serveur peut l'ouvrir via en-tête **`HX-Trigger`**. Supprimer le `fetch()` brut et la manipulation DOM directe.
6. **Routage serveur propre** : la vue lit `section` + `class_id`. Requête complète → shell + bon panneau ; requête HTMX (`request.htmx`) → **panneau seul**. Plus aucune dépendance à l'état JS pour savoir quoi afficher.

---

## 4. Intégration inter-applications — FRONTIÈRES PROPRES (point critique)

> Le dashboard surveillant est un **consommateur / une vue**, **pas un propriétaire** des données qui viennent d'ailleurs. Il **affiche**, il ne **réimplémente pas**.

Règles strictes :
- **Emploi du temps / calendrier / sessions** = propriété de l'app **`academics`** (`academics/services/schedule_service.py`, `timetable_service.py`, `session_service.py`). Le dashboard surveillant doit **lire via ces services**, **sans** dupliquer les requêtes ni la logique métier dans `portal`. Source de vérité unique : `academics`.
- **Cas / discipline / suivi terrain** = domaine **propre** du surveillant (`portal` / `supervisor_cases`).
- **Assiduité, classes, étudiants** : **identifier l'app propriétaire** de chaque donnée et la consommer via **sa** couche de services. Ne pas refaire ses requêtes dans `portal`.
- **Adaptateur fin** : si un panneau agrège des données de plusieurs apps, encapsuler cet appel dans `portal/services/supervisor_service.py` (un adaptateur), pour que **le template reste « bête »** (aucune logique métier dans le HTML).
- **Dégradation gracieuse obligatoire** : si une app externe ne renvoie rien ou change, le panneau affiche un **état vide propre**, **il ne casse pas** la mise en page. (C'est exactement le « section qui s'affiche mal » à bannir.)

➡️ Objectif : un dashboard qui **intègre proprement** ce qui vient des autres apps, sans s'approprier leur logique, et sans jamais se briser si la source évolue.

---

## 5. Componentisation avec django-cotton

Transformer le markup répété en **composants réutilisables** (slots + props, sans build) :
- `<c-supervisor-panel>` : enveloppe commune des panneaux (titre, actions, slot contenu, états vide/chargement/erreur intégrés).
- `<c-stat-card>` : cartes de statistiques (assiduité, cas ouverts, etc.).
- `<c-drawer>` : le tiroir de détail (ouverture pilotée par Alpine, contenu par HTMX).
- `<c-class-picker>` : le sélecteur de classe.
- `<c-empty-state>` : état vide standard (réutilisé partout pour la dégradation gracieuse).

> Le **même composant** sert la page complète et la réponse HTMX → DRY garanti.
> **Migration incrémentale** : componentiser **dans le cadre de cette refonte uniquement** ; ne pas semer du Cotton à moitié posé ailleurs.

---

## 6. Nettoyage (supprimer le « mélangé »)

- **Supprimer les panneaux morts** : `panel_attendance.html`, `panel_courses.html`, `panel_overview.html`, `panel_today.html`, `panel_alerts.html` (vérifier qu'ils ne sont inclus nulle part avant suppression).
- **Garder la génération `_strict`** comme base, puis **retirer le suffixe `_strict`** une fois les anciens supprimés (noms propres : `panel_attendance.html`, etc.).
- Supprimer le JS mort (routeur Alpine, doubles définitions `sgOpenDrawer/sgCloseDrawer`, `fetch()` drawer).

---

## 7. Backend — extraction & propreté

- **Extraire** toute la logique surveillant de `portal/views/views.py` vers **`portal/views/supervisor.py`**.
- **Routage des sections par dictionnaire de dispatch** `{ "attendance": render_attendance, "schedule": render_schedule, ... }` au lieu d'un `if/elif`.
- **Données dans `portal/services/supervisor_service.py`** (adaptateurs vers `academics` & co — cf. §4).
- **Audit N+1** des panneaux (assiduité/classes/étudiants bouclent probablement sur les étudiants) : `select_related`/`prefetch_related`, requêtes groupées. Un dashboard ne peut pas être « instantané » avec des vues lentes.

---

## 8. États & fluidité (rendu professionnel)

Chaque panneau gère explicitement :
- **état de chargement** (`hx-indicator`, squelette ou spinner discret),
- **état vide** propre (`<c-empty-state>`),
- **état d'erreur** propre (message clair, pas de page cassée),
- **boutons désactivés** pendant les requêtes (`hx-disabled-elt`).
Transitions douces sur l'ouverture du drawer et le changement de panneau (pas d'animations lourdes type AOS).

---

## 9. Sécurité (non négociable)

- Le gating « classe obligatoire » doit être **validé côté serveur**, pas seulement via les boutons désactivés Alpine.
- Chaque endpoint (panneaux + drawer) garde ses **contrôles d'auth/permissions** (rôle Surveillant Général). Un fragment ne contourne aucune autorisation.
- CSRF conservé (déjà géré globalement via `hx-headers`).

---

## 10. Garde-fous

- `hx-boost="false"` / exclusions sur liens externes et téléchargements éventuels.
- Gestion du `<title>` lors des swaps (extension `head-support` ou title dans le contenu).
- **Ne pas** introduire DaisyUI / components / Tungsten / CDN.
- **Ne pas** toucher la logique métier des autres apps (academics…) : seulement les consommer.
- **Ne pas** toucher la vitrine ni les autres dashboards dans ce chantier.

---

## 11. Méthode de travail (obligatoire)

1. Créer/valider `base_app.html` + assets locaux.
2. Reconstruire le shell surveillant (sidebar + topbar + `#supervisor-workspace` + drawer) avec les composants Cotton.
3. Brancher la navigation HTMX + `hx-push-url` + `preload` ; supprimer le routeur Alpine.
4. Refaire les panneaux un par un (classes → assiduité → emploi du temps → cours → étudiants → cas), chacun via son adaptateur `supervisor_service.py`, avec états vide/chargement/erreur.
5. Extraire le backend, supprimer les doublons morts.
6. Valider : instantané, fluide, URL/retour/refresh OK, aucune section cassée, données externes intégrées proprement.

---

## 12. Critères d'acceptation (definition of done)

- [ ] Plus aucun Play CDN ; un seul Tailwind (compilé local).
- [ ] Dashboard surveillant sur `base_app.html` (zéro vitrine).
- [ ] Navigation entre sections **instantanée**, **URL mise à jour**, retour/refresh fonctionnels.
- [ ] Un seul mécanisme de chargement (HTMX) ; drawer unifié, état géré uniquement par Alpine.
- [ ] Panneaux componentisés en Cotton ; aucun doublon mort restant.
- [ ] Emploi du temps & co **consommés via les services de leur app propriétaire** (academics), zéro logique dupliquée dans `portal`.
- [ ] Chaque panneau gère **vide / chargement / erreur** sans jamais casser la mise en page.
- [ ] Backend surveillant extrait dans `portal/views/supervisor.py` + `portal/services/supervisor_service.py` ; dispatch par dictionnaire ; N+1 corrigés.
- [ ] Permissions vérifiées sur chaque endpoint ; gating classe validé serveur.
- [ ] **Zéro régression** ailleurs.
