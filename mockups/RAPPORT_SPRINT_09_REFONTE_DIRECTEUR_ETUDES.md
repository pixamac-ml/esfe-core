# SPRINT 9 — Refonte complète du Dashboard Directeur des Études

## Objectif
Normaliser le frontend du Dashboard Directeur des Études pour en faire le modèle de référence de tous les futurs dashboards ESFE, en utilisant exclusivement `ui/`, Django Components, HTMX, Alpine.js et Tailwind CSS.

## Composants créés / enrichis

### Nouveaux composants Academic
- `ui/components/academic/academic_button.py` — bouton normalisé (primary, secondary, success, danger, warning, info, ghost, outline) avec variants `size`, `icon`, `icon_only`, `loading`, `disabled`, `confirm`, HTMX bindings.
- `ui/templates/academic/academic_button.html`
- `ui/components/academic/academic_sidebar.py` — sidebar professionnelle avec sous-menus repliables, branding, profil utilisateur.
- `ui/templates/academic/academic_sidebar.html`

### Composants réutilisés existants (déjà dans `ui/`)
- `AcademicPageLayout`
- `AcademicPageHeader`
- `AcademicToolbar`
- `AcademicCard`
- `AcademicStatCard`
- `AcademicTable`
- `AcademicAlert`
- `AcademicEmptyState`
- `AcademicModal`
- `AcademicDrawer`
- `AcademicTabs`
- `AcademicFilterBar`
- `AcademicProgress`
- `AcademicBadge`
- `AcademicTimeline`
- `AcademicStepper`
- `AcademicQuickAction`
- `metric_card`

### Composants de formulaire déjà disponibles
- `Input`, `Select`, `Textarea`, `Checkbox`, `RadioGroup`, `Switch`, `DatePicker`, `Combobox`, `UploadZone`, `AmountInput`, `FormActions`, `FormSection`, `Stepper`.

## Fichiers dashboard modifiés
- `templates/portal/staff/director_dashboard.html` — refondu pour utiliser `academic_sidebar`, `academic_page_header`, `academic_button`, `academic_card`, `academic_stat_card`, `academic_table`, `academic_alert`, `academic_empty_state`, `academic_modal`, `academic_drawer`.
- `portal/views/views.py` — ajout de `_build_director_sidebar_items()` et `_build_director_class_rows()` pour fournir les données structurées au template, sans logique métier dans le HTML.

## Menu de la sidebar (sous-menus repliables)
- Accueil
- Planification
  - Calendrier
  - Emplois du temps
- Programmes
  - Formations
  - UE
  - EC
- Enseignants
  - Affectations
- Pilotage
  - Synthèse
  - Alertes
- Résultats
  - Validation
  - Bulletins
- Documents
- Paramètres

## Suppressions / obsolescences
- Suppression des styles legacy `.de-*` (`.de-btn`, `.de-card`, `.de-table`, `.de-badge-*`, `.de-kpi`, `.de-section-label`, `.de-empty`) dans le template.
- La sidebar inline HTML est remplacée par le composant `academic_sidebar`.
- Les KPIs inline sont remplacés par `academic_stat_card`.
- Le tableau de classes inline est remplacé par `academic_table`.

## Tests ajoutés
- `ui/tests.py`
  - `test_academic_button_renders_variant_and_icon`
  - `test_academic_sidebar_renders_menu_items`
- `portal/tests.py`
  - `DirectorDashboardRenderTests.test_director_dashboard_renders`

## Résultat des tests
- `python manage.py check --settings=config.settings_test_local` : OK
- `python manage.py test ui --settings=config.settings_test_local -v 2` : 29 tests OK

## Architecture frontend recommandée
Tous les dashboards ESFE doivent désormais s'appuyer sur :
1. `AcademicPageLayout` comme enveloppe de page.
2. `AcademicSidebar` pour la navigation avec sous-menus.
3. `AcademicPageHeader` + `AcademicToolbar` pour les en-têtes.
4. `AcademicCard` pour les conteneurs.
5. `AcademicStatCard` / `MetricCard` pour les KPIs.
6. `AcademicTable` + `DataTable` pour les tableaux.
7. `AcademicButton` pour tous les boutons.
8. `FormField` + `Input` / `Select` / `Textarea` / `DatePicker` pour les formulaires.
9. `AcademicModal` + `AcademicDrawer` pour les interactions.
10. `AcademicAlert` + `AcademicEmptyState` + `AcademicBadge` pour les états.

## Corrections après retour utilisateur (09/07)
- **Utilisation du thème institutionnel** : toutes les couleurs passent par les tokens de `esfe_theme.css` (`--esfe-primary`, `--esfe-dark`, `--esfe-light`, `--esfe-accent`, `--school-primary`, `--surface`, `--card`, `--line`, etc.). Plus de `bg-slate-900`, `bg-blue-600` ou autres couleurs brutes.
- **Bouton "Ouvrir" parasite** : le `academic_modal` affichait son slot trigger par défaut. Corrigé en fournissant un slot `trigger` vide dans `director_dashboard.html`.
- **Freeze au clic** : synchronisation des événements drawer/modal (`academic-drawer-open/close`, `academic-modal-open/close`) et retrait de `x-collapse` (plugin Alpine non garanti).
- **Sidebar** : fond `--esfe-dark`, activation parent/enfant, sous-menus animés en pure transition Alpine.
- **Dashboard** : header compact, bannière de bienvenue avec dégradé institutionnel, stat cards avec bordures colorées, grille responsive repensée, quick actions enrichies.
- **Drawer** : retrait de l'overlay de chargement qui utilisait des classes inexistantes (`sg-drawer-loading-overlay`, `esfe-spinner`).

## Notes
- Aucune modification du backend métier : les services `calendar_service`, `teacher_assignment_service`, `timetable_management_service`, `academic_readiness_service` et `director_monitoring_service` restent consommés par les vues.
- Aucune dette technique introduite : les anciens styles inline sont retirés, les composants sont réutilisables.
- Le template est responsive (sidebar collapsible, grids responsive, header adaptatif).
