# Rapport Phase 2 - Dashboard Directeur des Études

Date : 26 juillet 2026  
Branche : `refactor/ui-core-foundation`

## Résumé exécutif

Le dashboard actif du Directeur des Études est migré sur UI Core sans changement
de modèle, migration, calcul académique ou règle d'accès. Il dispose d'un seul
shell interne, d'une navigation HTMX responsive, de composants UI Core pour la
présentation générique et conserve les workflows académiques spécialisés.

## Dashboard actif confirmé

```text
connexion
-> accounts.permissions.get_post_login_portal_url()
-> /portal/dashboard/ (accounts_portal:portal_dashboard)
-> accounts.access.get_user_position() == "director_of_studies"
-> portal.views.views.portal_dashboard()
-> portal.views.views._render_director_dashboard()
-> templates/portal/staff/director_dashboard.html
-> templates/portal/staff/director/partials/home.html ou workspace.html
```

`/portal/director/` reste une entrée de compatibilité. Elle redirige le Directeur
ordinaire vers l'entrée unique; le scope global explicite reste disponible pour
superutilisateur, DG et DGA selon la politique existante.

## Architecture avant / après

Avant : template de 400 lignes étendant la base publique, sidebar académique,
topbar et overlays locaux, consentement cookies public et environ 190 lignes de
JavaScript inline.

Après : template principal de moins de 100 lignes étendant `portal/app_base.html`,
un `ui_core.app_shell`, une présentation préparée côté serveur et un adaptateur
JavaScript externe. Le workspace métier historique reste encapsulé pour préserver
les workflows; son volume est une dette connue, pas une nouvelle architecture.

## Fichiers Phase 2

Ajouts principaux :

- `templates/portal/app_base.html`
- six partials d'accueil sous `templates/portal/staff/director/partials/`
- `portal/services/director_dashboard_presentation.py`
- `static/src/js/portal/director_dashboard.js`
- `portal/test_director_dashboard_phase2.py`
- audit, carte HTMX, recette et présent rapport sous `docs/ui/`

Modifications principales :

- `templates/portal/staff/director_dashboard.html` et `partials/workspace.html`
- `portal/views/views.py`, `portal/tests.py`, `accounts/tests.py`
- `ui/services/navigation.py`
- composants UI Core navigation, topbar, KPI, filtres et overlays
- `portal/services/director/calendar_mgt_service.py` pour sérialiser le contrat
  Alpine en JSON valide
- documentation d'architecture, contrats et dépréciation
- CSS source, configuration Tailwind et CSS compilé UI Core

Le worktree était déjà fortement modifié avant Phase 2. Aucun changement étranger
n'a été annulé.

## Composition UI

Composants UI Core utilisés :

- `app_shell`, `app_sidebar`, `app_topbar`
- `page_header`, `panel`
- `stat_card`, `data_table`, `empty_state`
- `filter_bar`, `alert`
- `modal`, `drawer`, `confirm_dialog`

Composants métier conservés : planning hebdomadaire, calendrier académique,
structure programme/semestre/UE/EC, enseignants et affectations, résultats,
notes, bulletins, examens, transferts et correspondances.

La sidebar reçoit huit entrées autorisées du service central de navigation. La
topbar affiche l'annexe ou le périmètre global, l'utilisateur et le compteur du
système de notifications existant. Les six KPI, actions rapides, panels et la
table de synthèse sont préparés par le service de présentation, sans ORM dans UI
Core. Le filtre enseignants utilise debounce, `hx-sync` et reset.

## HTMX, Alpine et overlays

La cartographie exhaustive se trouve dans
`DIRECTOR_DASHBOARD_HTMX_MAP.md`. Les sections remplacent uniquement
`#director-workspace`; drawers et modales ciblent leurs contenus dédiés. Les URLs
sont partageables via `hx-push-url`.

`director_dashboard.js` synchronise l'item actif, le chargement et le focus,
adapte les anciens appels d'overlay et intercepte `htmx:confirm`. UI Core conserve
le contrôleur unique de focus, Escape, trap et retour du focus. Le formulaire
d'évaluation Alpine est désormais défini dans le document persistant; les
métadonnées calendrier sont du JSON valide.

## Notifications

La cloche réutilise le compteur, le centre de notifications et le script temps
réel existants. Aucun modèle, endpoint ou canal concurrent n'a été créé. La
réception WebSocket distante n'a pas été déclenchée pendant la recette.

## Permissions et isolation par annexe

Les décorateurs, `require_director_branch_scope()`, `can_access()` et
`get_user_scope()` restent responsables des autorisations. Les querysets et
services métier reçoivent toujours l'annexe résolue. Les tests couvrent Directeur
avec annexe, sans annexe, accès inter-annexes, utilisateur non autorisé,
superutilisateur global et données absentes. UI Core ne calcule aucune permission
et n'accède à aucun modèle.

## Responsive et accessibilité

Les formats 1440 x 900, 1024 x 768, 900 x 1024 et 390 x 844 sont validés, ainsi
qu'un reflow équivalent à 200 %. La navigation devient hors-canvas, les KPI passent
de trois à deux puis une colonne et les tables restent scrollables. Aucun
débordement horizontal n'a été détecté.

Checklist accessibilité : skip link, structure de titres, contrôles natifs,
labels, focus visible, clavier, Escape, focus trap, retour du focus,
`aria-current`, `aria-expanded`, `aria-controls`, régions live et information non
portée par la couleur sont PASS. Le lecteur d'écran natif est NON TESTÉ.

## Tests

| Commande | Résultat |
|---|---|
| `python manage.py check` | PASS |
| `python manage.py makemigrations --check --dry-run` | PASS, aucun changement |
| tests ciblés Phase 2 + UI | PASS, 72/72 |
| `python manage.py test ui ...` | PASS, 58/58 |
| `python manage.py test portal ...` | PASS, 41/41 |
| `python manage.py test academics ...` | 102 tests, 1 échec et 11 erreurs préexistants |
| suite `ui core accounts portal academics` | 456 tests, 5 échecs et 12 erreurs préexistants |
| `npm run build:css` | PASS |

Les défauts globaux restants concernent : sérialisation du formulaire contact,
rapport annuel Gestionnaire, progression semestre Étudiant, préférences/profil,
chevauchement de calendrier, fixtures d'emploi du temps, publication annuelle,
champ d'audit de planning et fixtures de notifications de cours. Aucun traceback
ne vise les fichiers du pilote. Deux tests historiques Directeur ont été adaptés
et passent.

## Recette et comparaison

La matrice détaillée est dans
`DIRECTOR_DASHBOARD_PHASE2_MANUAL_QA.md`. Le parcours navigateur des huit sections
reste dans un seul document (`PerformanceNavigation` stable à 1), sans erreur
console/page ni réponse HTTP en échec. Modal, drawer, confirmation, toast, filtre,
mobile et focus ont été exercés.

Les captures avant/après sont dans `_audit/director_dashboard_before/` et
`_audit/director_dashboard_after/`. La version après supprime les éléments publics,
corrige le mobile et normalise shell, KPI, panels et table.

## Risques restants

- Le workspace métier historique reste volumineux et pourra être découpé lors
  d'une phase distincte, avec tests de chaque workflow.
- Pagination multi-page, action destructive réelle, lecteur d'écran et livraison
  WebSocket distante sont documentés `NON TESTÉ`.
- Les suites globales comportent des défauts antérieurs non liés au pilote.
- `git diff --check` signale des espaces dans un fichier Secrétaire préexistant et
  une fin de fichier du CSS compilé; aucun signalement ne concerne un fichier
  source du dashboard Phase 2.

## État Git

Branche `refactor/ui-core-foundation`, worktree sale avant et après la mission.
Aucun commit et aucun push. Aucun modèle ni fichier de migration n'a été ajouté ou
modifié par Phase 2.

## Verdict

**DASHBOARD PILOTE VALIDÉ**
