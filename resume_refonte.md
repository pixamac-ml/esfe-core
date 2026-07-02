# Résumé de la refonte UI — branche `refonte/dashboards-ui`

## ✅ Réalisé (commité)

### Phase 0 — Fondations
- Tokens sémantiques CSS dans `static/core/css/esfe_theme.css` :
  `--school-primary`, `--school-secondary`, `--text`, `--muted`,
  `--success`, `--danger`, `--warning`, `--info`,
  `--surface-0/1/2`, `--border`, `--line`, `--card-soft`
- Support dark-mode (classe `.dark-preview`)
- CDN Tailwind supprimé de 3 templates :
  `superadmin/base.html`, `informaticien/dashboard.html`,
  `director_dashboard.html` → remplacé par `main.css` + `esfe_theme.css`
- Fix Lucide/HTMX (`base_app.html` lignes 161-165)

### Phase 1 — Bibliothèque de composants (`ui/components/`)
**Atomes :** `icon`, `label`, `avatar`, `pill`
**Molécules :** `form_field`, `search_bar`, `tabs`
**Organismes :** `kpi_row`, `data_table`, `toast`
**Mis à jour :** `button`, `status_badge`, `metric_card`, `dashboard_card`, `section_header`
→ tous utilisent les tokens CSS + Lucide

### Phase 2.1 — Dashboard Étudiant
- `templates/portal/student/dashboard.html` : KPI convertis en `metric_card` + `kpi_row`
- Sections HTMX centralisées en boucle `sections[]`
- Contexte `lazy_sections`→`sections` ajouté à la vue

### Phase 2.2 — Dashboard Enseignant
- `templates/portal/teacher/sg_dashboard.html` : nav-tabs convertis tokens CSS
- KPIs → `kpi_row` (via `sg_partials/overview_kpis.html`)
- Contexte `kpi_cards` ajouté à `teacher_portal()`

## ✅ Réalisé (non commité — en cours)

### Phase 2.3 — Dashboard Secrétaire
- `secretary/templates/secretary/partials/dashboard_kpis.html` :
  4 KPIs convertis → `metric_card` (Registre, Visiteurs, Rendez-vous, Pièces)
  → plus de `sg-kpi-*`, plus de FontAwesome, plus de couleurs en dur

### Phase 3 — Nettoyage
- 9 fichiers maquettes/mockups HTML supprimés de la racine du projet :
  `maquettes_dg.html`, `dash_maquette.html`, `dash_section_2.html`,
  `dash_section_3.html`, `dashboard_informaticien.html`,
  `dashboard_surveillant.html`, `dashboard_surveillant_creation_emploi_du_temps.html`,
  `section_alertes_risques_dg.html`, `section_workflow_annexes_dg.html`

### Vérification
- `python manage.py check` → **0 erreurs**

## ⏳ Reste à faire (plan original)

| Phase | Travail | Priorité |
|-------|---------|----------|
| 2.3-2.8 | Dashboard Gestionnaire (~1500l, 79 fa-*), Directeur, DG, Communauté, Informaticien | Haute |
| 3.1 | Unifier les ~23 layouts/bases différents | Haute |
| 3.2 | Supprimer classes CSS locales mortes (`sg-*`, `dg-*`, `student-*`, AdminLTE) | Haute |
| 3.3 | Convertir ~481 `fa-*` restants → Lucide, puis retirer FontAwesome CDN | Haute |
| 3.4 | Supprimer doublons d'icônes | Moyenne |
| 4 | Vérification qualité : contraste, responsive, accessibilité, pas de fuite CSS | Haute |

### Où se trouvent les FontAwesome restants
- `accounts/templates/accounts/dashboard/` : ~481 références `fa-*`
- `secretary/templates/secretary/base.html` : CDN FontAwesome (à retirer après migration)
- `templates/base.html`, `templates/portal/teacher/sg_base.html` : CDN FontAwesome
- `templates/base_app.html` : FontAwesome local via `vendor/fontawesome/css/all.min.css`
