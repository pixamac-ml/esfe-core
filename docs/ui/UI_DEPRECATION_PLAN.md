# Plan de dépréciation UI

> Phase 1.5 : la réorganisation interne de UI Core est terminée. Aucun
> composant historique n'a été supprimé ou désenregistré.

Aucun composant n'est supprimé en phase 1.

## Pilote Phase 2 - Directeur des Études

Le dashboard actif du Directeur des Études ne consomme plus directement
`academic_sidebar`, `academic_stat_card`, `academic_table`, `academic_drawer` ni
`academic_modal` pour sa coque et son accueil. Ils sont remplacés dans ce seul
dashboard par :

- `ui_core.app_shell`, `ui_core.app_sidebar` et `ui_core.app_topbar` ;
- `ui_core.page_header`, `ui_core.stat_card`, `ui_core.panel` et
  `ui_core.data_table` ;
- `ui_core.filter_bar`, `ui_core.modal`, `ui_core.drawer`,
  `ui_core.confirm_dialog` et `ui_core.toast`.

Les composants historiques restent enregistrés, car d'autres dashboards ou
partials les utilisent encore. Les contenus académiques spécialisés du Directeur
restent également en place à l'intérieur du shell UI Core. Aucune suppression
n'est autorisée à l'issue de ce seul pilote.

| Composants historiques | Remplaçant | Usages/dashboards | Risque | Ordre | Conditions |
|---|---|---|---|---:|---|
| `academic_sidebar`, `teacher_sidebar`, `secretary_sidebar`, `supervisor_sidebar` | `ui_core.app_sidebar` | directeur, enseignant, secrétaire, surveillant | élevé | 1 | navigation équivalente, permissions, annexe, mobile et clavier testés |
| topbars spécialisées | `ui_core.app_topbar` | mêmes dashboards | élevé | 2 | actions, notifications, profil et responsive conservés |
| `academic_page_layout` et wrappers Portal | `ui_core.app_shell` | directeur puis autres | élevé | 3 | héritage, HTMX, modales et session testés |
| `metric_card`, `stat_card`, `mini_stat`, `academic_stat_card` | `ui_core.stat_card` | dashboards multiples | moyen | 4 | mapping des tons et valeurs longues validé |
| `dashboard_card`, `widget_card`, `glass_card`, `academic_card`, `layout.panel` | `ui_core.panel` | dashboards et pages publiques | moyen | 5 | séparer les cartes publiques et métier |
| `dashboard.data_table`, `academic_table` | `ui_core.data_table` | gestion, académique | élevé | 6 | tri, édition, pagination et HTMX couverts |
| `academic_filter_bar`, `dashboard.filter_bar` | `ui_core.filter_bar` | gestion, académique | moyen | 7 | GET/POST, reset et événements HTMX couverts |
| alertes, badges et états vides concurrents | équivalents `ui_core` | transversal | faible à moyen | 8 | audit de contraste et paramètres |
| modales, drawers, toasts, confirmations | équivalents `ui_core` | workflows interactifs | élevé | 9 | contrat événementiel, focus trap et erreurs testés |

## Adaptateurs temporaires

Les composants historiques peuvent déléguer leur rendu à UI Core tout en conservant leurs anciens paramètres. Cet adaptateur doit être local, testé et marqué comme transitoire. Aucun alias silencieux ne doit changer la sémantique d'un paramètre.

## Conditions de suppression

1. Recherche globale sans référence de template, import Python, enregistrement, chaîne dynamique ou test.
2. Aucun dashboard actif ni partiel HTMX ne dépend du composant.
3. Tests ciblés et suite globale exécutés.
4. Recette clavier, mobile et annexe réussie.
5. Suppression de l'import dans `ui/components/__init__.py` au même changement.

Les nombres d'usages approximatifs et templates concernés sont détaillés dans `UI_COMPONENT_INVENTORY.md`.
