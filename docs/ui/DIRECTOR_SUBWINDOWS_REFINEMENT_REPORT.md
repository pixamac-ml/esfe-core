# Rapport de raffinement — Sous-fenêtres du dashboard Directeur des Études

Date : 26 juillet 2026
Branche : `refactor/ui-core-foundation`

## 1. Cohérence métier vérifiée

| Fonction | Section correcte | Vue existante | Action |
|---|---|---|---|
| Créer session d'examens (macro) | `evaluations_calendar` | `director_exam_session_action` | `AcademicCalendarEntry` — déjà en place |
| Publier/annuler session | `evaluations_calendar` | `director_exam_session_action` | `AcademicCalendarEntry` — déjà en place |
| Planifier une évaluation (classe + EC + date) | `evaluations` | `director_evaluation_action` | `AcademicScheduleEvent` — sous-fenêtre « Planifier » |
| Lister les évaluations programmées | `evaluations` | `director_evaluations_subcontent` | Sous-fenêtre « Programmées » |
| Valider les notes d'un semestre | `evaluations` | `director_results_action` | `Semester` — sous-fenêtre « Validation » |
| Rejeter / Publier (OTP) | `evaluations` | `director_results_action` | `Semester` — drawer evaluations_drawer |
| Générer les bulletins | `evaluations` | `director_bulletin_action` | PDF bulletins — drawer evaluations_drawer |
| Vue d'ensemble (KPIs + alertes) | `evaluations` | `director_evaluations_subcontent` | Sous-fenêtre « Vue d'ensemble » |

Les 4 sous-fenêtres sont correctement placées dans la section `evaluations` (« Résultats & Notes »). Aucune responsabilité n'a été inventée.

## 2. Section finale retenue

**Section : `evaluations`** — alias « Résultats & Notes »

Le titre de la section a été corrigé de « Planification des évaluations » à « Résultats et notes » pour refléter le vrai périmètre : création d'évaluations individuelles + validation/publication des notes + bulletins.

## 3. Sous-fenêtres finales

| Sous-fenêtre | Clé | Contenu | Actions backend |
|---|---|---|---|
| Vue d'ensemble | `overview` | 4 KPIs (évaluations, à venir, à valider, à publier), accès rapides, alertes, classes candidates diplome | Lecture seule + navigation |
| Planifier | `create` | Formulaire création `AcademicScheduleEvent` | POST `director_evaluation_action` |
| Programmées | `scheduled` | Liste évaluations programmées par classe | POST annulation évaluation |
| Validation | `validation` | Grille classes + statut workflow + pagination | Drawer evaluations_drawer → validate/publish/reject/bulletins |

## 4. Composants UI Core réutilisés

- Header pattern : `rounded-2xl border bg-[color:var(--card)] shadow-sm px-6 py-5` (identique planification/evaluations_calendar)
- KPIs : Pattern A (plain numeric, 4 colonnes) — même structure que programme/correspondances
- Cartes d'action : même pattern que drawer operation (icon + label + panel-right-open)
- Grille classes : même pattern que planification (`gap-0 divide-y sm:divide-y-0 sm:divide-x`)
- Alertes : même pattern que planification (border warning + bouton action)
- État vide : `border-dashed` + icon + titre bold + sous-titre muted
- Formulaires : `rounded-xl border bg-white px-4 py-2.5 text-sm focus:ring-[color:var(--school-primary)]/30`
- Badges : `rounded-full bg-[color:xxx-soft] px-2.5 py-0.5 text-[10px] font-bold text-[color:xxx]`
- Boutons : primary (`rounded-lg border bg-[color:var(--school-primary)] text-white`), secondary (`border bg-[color:var(--card)] hover:bg-slate-50`), danger (`border bg-[color:var(--danger-soft)] text-[color:var(--danger)]`)

## 5. Interactions HTMX

| Élément | `hx-get` | `hx-target` | `hx-swap` | `hx-push-url` | `hx-indicator` |
|---|---|---|---|---|---|
| Tab Vue d'ensemble | `director_evaluations_subcontent?view=overview` | `#director-section-subcontent` | `innerHTML` | `director_workspace?section=evaluations&view=overview` | `#eval-subcontent-loading` |
| Tab Planifier | `director_evaluations_subcontent?view=create` | `#director-section-subcontent` | `innerHTML` | `director_workspace?section=evaluations&view=create` | `#eval-subcontent-loading` |
| Tab Programmées | `director_evaluations_subcontent?view=scheduled` | `#director-section-subcontent` | `innerHTML` | `director_workspace?section=evaluations&view=scheduled` | `#eval-subcontent-loading` |
| Tab Validation | `director_evaluations_subcontent?view=validation` | `#director-section-subcontent` | `innerHTML` | `director_workspace?section=evaluations&view=validation` | `#eval-subcontent-loading` |
| Bouton Accès rapides | `director_evaluations_subcontent?view=...` | `#director-section-subcontent` | `innerHTML` | `director_workspace?section=evaluations&view=...` | `#eval-subcontent-loading` |
| Carte classe | `director_drawer?panel=evaluations&class_id=...` | `#director-drawer-content` | `innerHTML` | — | — |
| Annuler évaluation | `director_evaluation_action` POST | `#director-workspace` | `innerHTML` | — | — |
| Formulaire création | `director_evaluation_action` POST | `#director-workspace` | `innerHTML` | — | `#eval-create-loading` |

Indicateur de chargement : spinner animé + texte « Chargement... » overlay sur `#director-section-subcontent` pendant le chargement HTMX.

## 6. Pagination

La pagination dans la sous-fenêtre « Validation » utilise `_pagination.html` avec :
- `target_id="#de-grid-evals"` — cible unique de la grille
- `hx_select="#de-grid-evals"` — extraction partielle de la réponse
- `query_suffix="section=evaluations&view=validation"` — conservation de la sous-fenêtre active
- Les boutons Précédent/Suivant remplacent uniquement la grille, pas l'ensemble de la section

## 7. Formulaires

Le formulaire de création suit les patterns existants :
- Labels `text-xs font-black uppercase tracking-wide text-slate-600`
- Champs requis avec `required`
- Désactivation du bouton pendant la requête (`hx-disabled-elt="button[type=submit]"`)
- Indicateur de chargement HTMX inline (`#eval-create-loading`)
- Données EC par classe sérialisées en JSON (`de-ecs-by-class-data`)
- Sélection en cascade classe → EC via Alpine.js (`x-model="selectedClass"`)
- POST HTMX → validation backend → rendu du workspace complet avec toast

## 8. Actions backend

Aucune action factice. Tous les boutons déclenchent de vraies vues :
- Création : POST `director_evaluation_action` → `AcademicScheduleEvent.create`
- Annulation : POST `director_evaluation_action` → `AcademicScheduleEvent` status → cancelled
- Validation : drawer → POST `director_results_action` → `Semester` status → finalized
- Publication : drawer → POST `director_results_action` → OTP → `Semester` status → published
- Bulletins : drawer → POST `director_bulletin_action` → génération PDF

## 9. Données de santé utilisées

Aucune donnée fictive créée. Les exemples dans les placeholders utilisent :
- « Anatomie » (matière réelle d'école de santé)
- « Amphi 1 » (salle réaliste)
- Les classes et matières sont chargées dynamiquement depuis la base via `eval_form_classes` et `eval_form_ecs_json`

## 10. Fichiers modifiés

| Fichier | Changement |
|---|---|
| `portal/views/views.py` | +`director_evaluations_subcontent` vue, +`_EVAL_SUBVIEW_TEMPLATES` |
| `portal/urls.py` | +route `director/evaluations/subcontent/` |
| `templates/portal/staff/director/partials/workspace.html` | Section évaluations raffinée : header corrigé, tabs avec `hx-indicator`, loading overlay |
| `templates/portal/staff/director/partials/evaluations/overview.html` | Raffiné : KPIs Pattern A, accès rapides avec `panel-right-open`, alertes, diplome |
| `templates/portal/staff/director/partials/evaluations/create.html` | Raffiné : labels slate-600, indicateur chargement inline, bouton primary standard |
| `templates/portal/staff/director/partials/evaluations/scheduled.html` | Raffiné : hover bg-slate-50, badges consistent, état vide dashed |
| `templates/portal/staff/director/partials/evaluations/validation.html` | Raffiné : `#de-grid-evals` pour pagination, `panel-right-open`, hover states |
| `portal/test_director_dashboard_phase2.py` | +12 tests ciblés (sub-navigation, HTMX, loading, unicité fragments, cibles) |

## 11. Captures

Répertoire : `_audit/director_subwindows_refinement/`

Les captures écran nécessitent une session navigateur réelle (non automatisables sans Playwright configuré).

## 12. Tests

| Test | Résultat |
|---|---|
| `python manage.py check` | 0 erreurs |
| `makemigrations --check --dry-run` | Aucun changement |
| `test portal.test_director_dashboard_phase2` | 28 tests OK |
| `test ui` | 108 tests OK |
| `npm run build:css` | OK |

Tests ajoutés :
- `test_evaluations_section_shows_subnavigation` — tabs + title + loading
- `test_evaluations_subcontent_default_is_overview` — KPIs + accès rapides
- `test_evaluations_subcontent_create` — formulaire + indicateur chargement
- `test_evaluations_subcontent_scheduled` — état vide
- `test_evaluations_subcontent_validation` — grille validation
- `test_evaluations_subcontent_unknown_view_defaults_to_overview`
- `test_evaluations_subcontent_requires_authentication`
- `test_evaluations_subcontent_requires_director_position`
- `test_each_subcontent_returns_unique_fragment`
- `test_workspace_evaluations_has_htmx_indicator`
- `test_workspace_evaluations_tabs_use_correct_target`
- `test_workspace_evaluations_has_no_global_overflow`

## 13. Limites

- Les captures écran nécessitent une session navigateur réelle.
- Les autres sections du dashboard ne sont pas encore converties (pilote uniquement).
- Le comportement temps réel (WebSocket) n'est pas affecté.
- La pagination dans les sous-fenêtres recharge la section complète via `director_workspace` puis extrait uniquement la grille via `hx-select` — fonctionnel mais pas ultra-léger.

## 14. État Git

- Branche : `refactor/ui-core-foundation`
- Worktree : sale avant et après la mission
- Aucun commit
- Aucun push

---

**SOUS-FENÊTRES RAFFINÉES ET PRÊTES POUR VALIDATION VISUELLE**
