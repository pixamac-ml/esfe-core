# Frontières UI générique et UI métier

> Phase 1.5 : les frontières sont désormais matérialisées par les packages
> `layout`, `navigation`, `data_display`, `forms`, `feedback` et `overlays`.

## A. Fondation générique

Boutons, icônes, avatars, badges, labels, tooltips, séparateurs, spinners et skeletons ne connaissent ni utilisateur, ni rôle, ni annexe. Les composants `atoms`, `forms` et `ui.button` existants restent la base à rapprocher progressivement des tokens UI Core.

## B. Structure applicative générique

`ui_core.app_shell`, `app_sidebar`, `app_topbar`, `nav_group`, `nav_item`, `breadcrumb`, `page_header`, `page_section`, `content_grid`, `panel`, `modal` et `drawer` reçoivent uniquement des données préparées. Ils ne doivent importer aucun modèle, ni appeler `can_access()`.

La décision d'afficher une entrée appartient au service `ui.services.navigation`, qui consomme la politique officielle de `accounts.access`.

## C. Affichage générique des données

`ui_core.stat_card`, `data_table`, `filter_bar`, `status_badge`, `empty_state`, `alert`, `toast`, `loading_overlay` et `confirm_dialog` normalisent la présentation. Les vues restent responsables des querysets, permissions, URLs d'action et données.

## D. Composants métier

| Domaine | Composants maintenus | Fondation future |
|---|---|---|
| Notes | `notes_grid`, cellules EC, workflow, validation, anomalies | panel, data table, badge, alert, button |
| Académique | calendrier, stepper, planning, timeline spécialisée | panel, status badge, empty state |
| Admissions | hero, formulaire, indicateur d'étapes | app shell public, panel, alert |
| Inscriptions/paiements | identité, finance, statuts, reçus | panel, badge, data table |
| Documents | reçus, attestations, fiches, factures | tokens d'impression dédiés; pas le shell |
| IT | audit, import, support, supervision, réglages | panel, data table, alert |
| Contenu public | blog, actualités, formations, home/about | fondations publiques; pas la sidebar Portal |

Exemple cible :

```text
notes_grid
  utilise ui_core.panel
  utilise ui_core.data_table
  utilise ui_core.status_badge
  conserve validation, édition et contrats HTMX métier
```

## Règles d'architecture

1. Aucun composant UI Core n'accède aux modèles.
2. Aucun composant UI Core ne déduit une permission ou une annexe.
3. Les URLs d'action sont fournies par la vue ou un service autorisé.
4. Les composants métier peuvent composer UI Core, sans être fusionnés arbitrairement.
5. Les variantes visuelles utilisent des tokens sémantiques, pas des couleurs métier codées en dur.
6. Les documents imprimables gardent une architecture séparée du shell écran.
