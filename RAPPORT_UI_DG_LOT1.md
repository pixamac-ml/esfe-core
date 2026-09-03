# Audit UI — lot 1 : dashboard DG

## Composants UI Core disponibles

Le socle contient `app_shell`, `app_sidebar`, `app_topbar`, `page_header`,
`content_grid`, `panel`, `filter_bar`, `data_table`, `stat_card`,
`status_badge`, `chart_panel`, `empty_state`, `loading_overlay`, `toast`,
`alert`, `drawer`, `modal` et `confirm_dialog`.

## Référence Direction des Études

Le dashboard DE est le consommateur de référence du shell certifié et utilise
déjà les composants de page, de tableaux, de badges, d'états vides et des
overlays UI Core. Le DG doit donc composer ce même shell, pas le remplacer.

## État DG avant migration

- Le DG passait bien par le shell certifié mais recréait ensuite une sidebar et
  une topbar historiques dans `templates/portal/dg/dashboard.html`.
- Les sections, modales et drawers existants sont tous référencés par les vues
  DG : aucune suppression n'est sûre à ce stade.
- Les styles et scripts historiques étaient concentrés dans `dashboard.html`.
- Les grandes listes DG sont encore limitées à un sous-ensemble chargé côté
  serveur ; la recherche/pagination par domaine reste un lot à livrer.

## Décision du lot 1

Le nouveau template de composition sert le shell certifié, un espace de
travail HTMX et les overlays communs. L'accueil est migré vers UI Core
(en-tête, contexte, KPI, table et états vides). Les styles des fragments non
encore migrés vivent temporairement dans un asset de compatibilité isolé,
sans réintroduire un second shell.

## Prochain lot

Migrer Personnel en premier : endpoint filtré/paginé côté serveur, barre de
recherche HTMX, table UI Core, menu d'actions et drawer de fiche. Ensuite
appliquer le même contrat à Paiements et Étudiants.
