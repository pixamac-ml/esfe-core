# Audit pré-migration du dashboard Directeur des Études

Date : 26 juillet 2026  
Branche : `refactor/ui-core-foundation`

## Dashboard actif confirmé

Chaîne réellement utilisée :

```text
connexion
-> accounts.permissions.get_post_login_portal_url()
-> /portal/dashboard/ (`accounts_portal:portal_dashboard`)
-> accounts.access.get_user_position() == "director_of_studies"
-> portal.views.views.portal_dashboard()
-> portal.views.views._render_director_dashboard()
-> templates/portal/staff/director_dashboard.html
-> templates/portal/staff/director/partials/workspace.html
```

La route historique `/portal/director/` (`accounts_portal:portal_director`) reste
active, mais ne rend aucun ancien dashboard : elle redirige vers l'entrée unique
`/portal/dashboard/`. Aucun template v2 concurrent n'est utilisé.

## Template principal

`templates/portal/staff/director_dashboard.html` compte 400 lignes avant migration.
Il étend `base.html` en neutralisant les blocs navbar, footer et widget flottant
publics. Le bandeau cookies public reste toutefois injecté par la base.

Le template contient :

- la coque complète ;
- `academic_sidebar` ;
- une topbar écrite directement dans le template ;
- l'accueil et ses six KPI ;
- les actions rapides ;
- la table des classes et l'activité récente ;
- `academic_drawer` et `academic_modal` ;
- environ 190 lignes de JavaScript inline.

## Partials

Le dashboard consomme 21 fichiers sous `templates/portal/staff/director/`.
Les principaux sont :

| Fichier | Lignes | Responsabilité |
|---|---:|---|
| `partials/workspace.html` | 1917 | huit espaces métier et formulaires HTMX |
| `partials/director_weekly_slots_workspace.html` | 236 | grille horaire spécialisée |
| `partials/drawers/programme_drawer.html` | 300 | structure semestre/UE/EC |
| `partials/drawers/teacher_profile_drawer.html` | 230 | dossier enseignant |
| `partials/drawers/evaluations_drawer.html` | 170 | actions résultats/bulletins |
| `modals/teacher_assign_modal.html` | 162 | affectation enseignant |
| autres modales, drawers et panels | 8 à 127 | workflows spécialisés |

Le très grand `workspace.html` est un composant métier existant. Il sera conservé
pendant le pilote pour éviter de réécrire les workflows, puis encapsulé dans la
nouvelle coque. L'accueil et le script de coque peuvent être séparés sans toucher à
ce contrat métier.

## Composants utilisés avant migration

- `academic_sidebar`
- `academic_card`
- `academic_stat_card`
- `academic_table`
- `academic_alert`
- `academic_empty_state`
- `academic_button`
- `academic_drawer`
- `academic_modal`
- composants de formulaire et cellules spécialisées dans les partials métier

Les composants académiques de calendrier, notes, bulletins, planning, enseignants
et structure de programme doivent rester spécialisés.

## Endpoints et interactions HTMX

Le périmètre expose les routes `director_workspace`, `director_drawer`, les
workflows enseignants, programme, correspondances, transferts, résultats,
bulletins, sessions, évaluations, calendrier, rapports et planification hebdomadaire.

145 occurrences d'attributs HTMX ont été relevées. Les cibles principales sont :

- `#director-workspace` pour une section métier ;
- `#director-drawer-content` pour un détail ;
- `#director-modal-content` pour un formulaire ou une confirmation.

Les swaps sont principalement `innerHTML`; les paginations ciblent des grilles en
`outerHTML`. Les formulaires POST incluent le token CSRF. Plusieurs actions utilisent
encore `hx-confirm`, qui sera conservé si le remplacement par le dialogue UI Core
risque de modifier le workflow.

## Scripts

Le contrôleur inline `deDashboard()` gère :

- l'état de module actif ;
- les actions rapides ;
- les chargements de workspace ;
- des skeletons construits en chaînes HTML ;
- l'ouverture des anciens overlays ;
- les hooks `htmx:beforeRequest`, `afterRequest` et `afterSwap` ;
- la réinitialisation Lucide.

Il duplique des fonctions désormais disponibles dans
`static/src/js/ui_core/index.js`. La migration doit conserver seulement le petit
adaptateur de navigation métier et réutiliser `window.ESFEUI`.

## Permissions et isolation d'annexe

- Entrée principale : `login_required`, puis sélection stricte de la position.
- Endpoints Directeur : `_position_required(DIRECTOR_DASHBOARD_POSITIONS)`.
- Scope : `academics.permissions.require_director_branch_scope()`.
- Directeur d'annexe : annexe obligatoire, sinon `PermissionDenied`.
- Superutilisateur, DG et DGA : scope global autorisé par la politique existante.
- Querysets et services reçoivent l'annexe résolue.
- Les actions sensibles revérifient l'objet ou la classe dans cette annexe.

UI Core ne calcule aucune permission et ne reçoit aucun queryset.

## Données affichées

- annexe et année académique ;
- classes, effectifs et semestres ;
- enseignants, affectations et documents ;
- planning, créneaux et journaux de cours ;
- évaluations, notes, anomalies et bulletins ;
- sessions d'examen ;
- calendrier académique ;
- correspondances et transferts ;
- compteurs de tâches et notifications.

## Dépendances

- modèles et services `academics`, `academic_cycle`, `portal`, `accounts`,
  `notification_center` ;
- HTMX, Alpine, Lucide et Chart.js ;
- composants académiques historiques ;
- politique `accounts.access` et permissions `academics.permissions`.

## Comportements à conserver

- entrée unique et redirection historique ;
- huit sections et leurs alias d'URL ;
- tous les formulaires et actions HTMX ;
- pagination, recherche et filtres existants ;
- drawers et modales de détail ;
- notifications existantes ;
- contrôles de rôle et d'annexe ;
- exports et workflows notes/bulletins inchangés.

## Problèmes fonctionnels préexistants

- La suite `portal` échoue avant migration dans
  `DirectorDashboardRenderTests.setUp` : `create_user` est appelé sur la classe
  utilisateur plutôt que sur son manager.
- Le test cite un nom de route `director_dashboard` qui n'existe pas dans les URLs
  réelles ; la route active est `portal_dashboard`.
- Le script de coque installe plusieurs listeners globaux dans le template.
- Les liens de navigation ne fournissent pas de fallback complet cohérent pour
  toutes les sections.

## Problèmes visuels préexistants

- À 390 x 844, la sidebar desktop reste visible et réduit le contenu à une bande
  étroite : le dashboard est inutilisable.
- Le bandeau de consentement public recouvre l'interface interne.
- Le titre du bandeau d'accueil a un contraste insuffisant.
- Plusieurs cartes utilisent des rayons supérieurs au standard UI Core.
- La coque, la topbar et les overlays ne suivent pas les tokens UI Core.
- Le template principal mélange structure, présentation et script.

## Captures avant migration

Les captures sont stockées dans `_audit/director_dashboard_before/` :

- `desktop.png` : 1440 x 900 ;
- `desktop_1024.png` : 1024 x 768 ;
- `tablet.png` : 900 x 1024 ;
- `mobile.png` : 390 x 844.

## Éléments à remplacer

- héritage de `base.html` par un shell interne commun ;
- `academic_sidebar` par `ui_core.app_sidebar` ;
- topbar manuelle par `ui_core.app_topbar` ;
- coque manuelle par `ui_core.app_shell` ;
- en-tête d'accueil par `ui_core.page_header` et une barre de contexte ;
- `academic_stat_card` par `ui_core.stat_card` ;
- cartes génériques par `ui_core.panel` ;
- table de synthèse compatible par `ui_core.data_table` ;
- overlays génériques par `ui_core.modal` et `ui_core.drawer` ;
- script inline massif par un adaptateur idempotent dédié.

## Risques

- Les partials métier sont volumineux et fortement couplés à leurs cibles HTMX.
- Les anciens événements d'overlay doivent être adaptés sans casser les boutons.
- Le rendu global DG/superutilisateur doit rester possible sans annexe.
- Les données de navigation doivent rester autorisées par le service central.
- Le worktree contient des modifications antérieures dans `portal` et `academics`;
  chaque édition doit préserver ces changements.
