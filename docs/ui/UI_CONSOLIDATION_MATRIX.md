# Matrice de consolidation UI

> Phase 1.5 : UI Core est maintenant structuré en domaines techniques. Cette
> matrice conserve l'ordre de migration prévu et les noms publics stables.

> Phase 1.75 : `ui_core.chart_panel`, `tabs`, `dropdown_menu`,
> `progress_bar`, `timeline` et `form_field` fournissent désormais les contrats
> génériques. Ils ne remplacent aucun wrapper métier avant la Phase 2.

## Principes

- UI Core fournit la structure et la présentation génériques.
- Les composants historiques restent enregistrés pendant la migration.
- Un wrapper métier n'est pas supprimé s'il porte une interaction, un contrat HTMX ou une sémantique propre.
- La migration se fait dashboard par dashboard, avec recherche globale et tests avant toute suppression.

## Familles concurrentes

| Famille | Base existante retenue | Capacités à conserver | Incompatibilités | API UI Core | Compatibilité | Ordre |
|---|---|---|---|---|---|---:|
| KPI | `dashboard.stat_card` | lien, icône, ton, tendance, chargement de `metric_card`/`mini_stat` | variables CSS et tailles différentes | `ui_core.stat_card(label, value, icon, tone, trend, href, loading)` | ancien composant maintenu; adaptation des contextes au pilote | 2 |
| Panels/cartes | `layout.panel` et `dashboard.dashboard_card` | header/footer, padding, slots, état vide | cartes métier et glass effects non équivalents | `ui_core.panel(title, subtitle, padding)` | wrapper temporaire par dashboard | 3 |
| Graphiques | `dashboard.chart_card` | titre, légende, zone canvas, état vide | dépendance Chart.js et initialisation JS | `ui_core.chart_panel` + `window.ESFEUI.charts` | historique maintenu jusqu'au pilote | 5 |
| Sidebar | `academic.academic_sidebar` | groupes, enfants, utilisateur, état actif; badges des variantes rôle | callbacks Alpine propres à chaque dashboard | `ui_core.app_sidebar(groups, user_name, user_role)` | service de navigation produit les données; anciennes sidebars restent | 1 |
| Topbar | `teacher_topbar` et shell Portal | identité, annexe, actions, notifications | structures et compteurs différents | `ui_core.app_topbar(title, branch_name, notification_count)` | slots d'actions; branchement notification ultérieur | 1 |
| Coque | `academic.academic_page_layout` et layouts Portal | sidebar repliable, contenu, responsive | héritages de templates et JS de navigation différents | `ui_core.app_shell` | introduite d'abord sur la page système | 1 |
| En-tête | `academic.academic_page_header` | breadcrumb, titre, sous-titre, actions | tailles et paramètres divergents | `ui_core.page_header` + `ui_core.breadcrumb` | mapping simple des paramètres | 2 |
| Tableaux | `dashboard.data_table` | tri HTMX, loading, vide, pagination; rendu académique dense | cellules éditables et tables métier non uniformes | `ui_core.data_table(headers, rows, loading)` | première API volontairement en lecture seule; spécialisations conservées | 4 |
| Filtres | `dashboard.filter_bar` | GET/POST, select, input, reset | paramètres HTMX et formulaires métier | `ui_core.filter_bar(filters, action, method)` | enrichissement après pilote | 4 |
| Badges | `dashboard.status_badge` | tons, icône, point | nomenclatures de tons divergentes | `ui_core.status_badge` | ton inconnu ramené à `neutral` | 2 |
| État vide | `dashboard.empty_state` | icône, message, action | variantes compactes | `ui_core.empty_state` | remplaçable après validation visuelle | 2 |
| Alertes | `dashboard.alert` | tons, fermeture, rôle ARIA | noms `level`/`tone` | `ui_core.alert` | adaptateur de paramètres au pilote | 2 |
| Modal | `academic.academic_modal` | slots, focus, footer, HTMX | événements d'ouverture spécifiques | `ui_core.modal` | ne pas migrer les workflows avant contrat événementiel | 5 |
| Drawer | `academic.academic_drawer` | côtés, titre, chargement HTMX | IDs et événements spécifiques | `ui_core.drawer` | coexistence jusqu'aux tests E2E | 5 |
| Toast | `dashboard.toast` | fermeture, tons | bus événementiel non harmonisé | `ui_core.toast` | présentation uniquement en phase 1 | 5 |
| Loading | `dashboard.loading_overlay` | overlay et libellé | cible Alpine/HTMX variable | `ui_core.loading_overlay` | utilisable dans un conteneur positionné | 3 |
| Confirmation | `dashboard.confirm_dialog` | libellés, danger, HTMX | action réelle propre au workflow | `ui_core.confirm_dialog` | phase 1 sans logique métier | 5 |

## Composants à ne pas fusionner

- `notes_grid`, `notes_table`, cellules de notes, workflow et anomalies : contrats académiques et édition live.
- Documents PDF (`esfe_receipt`, bulletins, attestations, fiches) : contraintes d'impression.
- Calendriers et emploi du temps : placement temporel et données spécialisées.
- Admission, inscription et paiement : étapes et validations métier.
- Panneaux informaticien : opérations et permissions propres.
- Composants blog, actualités et formations : expérience publique distincte du shell applicatif.

Ces composants pourront utiliser `ui_core.panel`, `ui_core.status_badge`, `ui_core.empty_state` ou `ui_core.data_table` en fondation, sans perdre leur API métier.

## Stratégie de migration

1. Stabiliser la page `/ui/system/` et les tests contractuels.
2. Migrer le dashboard Directeur des Études comme pilote.
3. Adapter navigation, en-têtes, KPI et panels avant les interactions.
4. Valider HTMX, Alpine, clavier, responsive et isolation d'annexe.
5. Migrer les autres dashboards par famille.
6. Déprécier un ancien composant seulement après zéro référence, zéro import et tests globaux.
