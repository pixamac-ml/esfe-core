# Contrats API UI Core

> Phase 1.75 : 27 composants publics, densités normalisées et interactions
> techniques documentées.

## Complément Phase 2

Le pilote Directeur des Études enrichit des contrats existants sans nouveau
composant générique :

- `ui_core.nav_item` accepte `hx_get`, `hx_target`, `hx_swap`, `hx_push_url` et
  `nav_key` pour une navigation partielle avec fallback HTTP complet ;
- `ui_core.stat_card` accepte `hx_get`, `hx_target` et `hx_push_url` lorsque le KPI
  est un lien de navigation ;
- `ui_core.filter_bar` accepte `swap` et `sync` pour cibler un workspace et
  synchroniser les recherches concurrentes ;
- `ui_core.app_topbar` accepte `notifications_url` et rend la cloche comme un lien
  réel vers le système existant ;
- modal, drawer et confirmation écoutent `ui-overlay-open` et
  `ui-overlay-close` ;
- le bouton d'acceptation de `ui_core.confirm_dialog` expose
  `data-ui-confirm-accept` pour l'adaptation de `htmx:confirm`.

Ces paramètres restent génériques et ne contiennent aucune permission, annexe ou
sémantique académique.

## Conventions communes

- Noms publics stables : `ui_core.<nom>`.
- Paramètres en anglais et sémantiques.
- `tone` remplace `variant`, `level`, `color` ou `status`.
- Tons autorisés selon le composant : `neutral`, `primary`, `info`, `success`, `warning`, `danger`.
- Une valeur inconnue utilise un fallback sûr.
- `id` est le nom officiel des identifiants DOM. Les alias Phase 1 restent acceptés pour compatibilité.
- Les données sont préparées par les vues/services; aucun composant n'interroge la base.
- `density` accepte uniquement `comfortable` ou `compact`; toute autre valeur
  revient à `comfortable`.
- Les événements sont génériques, sans sémantique métier.

## Layout

| Nom | Responsabilité | Obligatoire | Facultatif/défaut | Slots | États et accessibilité | Exemple |
|---|---|---|---|---|---|---|
| `ui_core.app_shell` | Coque responsive | aucun | `title="ESFE"`, `sidebar_open=True` | `sidebar`, `topbar`, `default` | lien d'évitement, navigation mobile | `{% component "ui_core.app_shell" %}...{% endcomponent %}` |
| `ui_core.breadcrumb` | Fil d'Ariane | aucun | `items=[]`, `label="Fil d'Ariane"` | aucun | `nav`, `aria-current` | `{% component "ui_core.breadcrumb" items=items %}` |
| `ui_core.content_grid` | Grille responsive | aucun | `columns=3`, borné 1..4 | `default` | une colonne mobile | `{% component "ui_core.content_grid" columns=4 %}` |
| `ui_core.page_header` | Titre de page | aucun | `title=""`, `subtitle=""`, `eyebrow=""` | `actions` | contenu long replié | `{% component "ui_core.page_header" title="Page" %}` |
| `ui_core.page_section` | Section sémantique | aucun | `title=""`, `description=""`, `labelled_by=""` | `default` | association `aria-labelledby` | `{% component "ui_core.page_section" title="Synthèse" %}` |
| `ui_core.panel` | Conteneur structuré | aucun | `title`, `subtitle`, `padding`, `density`, `tone`, `collapsible`, `open`, `loading`, `error`, `scrollable` | `header`, `default`, `footer` | section, collapsible clavier, loading/error | `{% component "ui_core.panel" title="Données" collapsible=True %}` |

## Navigation

| Nom | Responsabilité | Obligatoire | Facultatif/défaut | Slots | États et accessibilité | Exemple |
|---|---|---|---|---|---|---|
| `ui_core.app_sidebar` | Navigation préparée | aucun | `groups=[]`, `brand`, `subtitle`, `user_name`, `user_meta`, `collapsed=False` | aucun | état vide, hors-canvas | `{% component "ui_core.app_sidebar" groups=navigation %}` |
| `ui_core.app_topbar` | En-tête global | aucun | `title`, `user_name`, `context_label`, `notification_count=0` | `actions` | bouton mobile et notification labellisés | `{% component "ui_core.app_topbar" title="Portail" %}` |
| `ui_core.nav_group` | Groupe de liens | aucun | `label=""`, `items=[]` | aucun | section nommée | `{% component "ui_core.nav_group" items=items %}` |
| `ui_core.nav_item` | Lien de navigation | aucun | `label=""`, `url="#"`, `icon="circle"`, `active=False`, `badge=None`, `disabled=False` | aucun | `aria-current`, `aria-disabled` | `{% component "ui_core.nav_item" label="Accueil" url="/" %}` |
| `ui_core.tabs` | Navigation secondaire | aucun | `id`, `items=[]`, `active`, `density` | aucun | tablist, disabled, scroll mobile | `{% component "ui_core.tabs" items=tabs %}` |
| `ui_core.dropdown_menu` | Menu d'actions | aucun | `id`, `label`, `items=[]`, `align="right"`, `disabled=False` | aucun | Échap, clic extérieur, rôles menu | `{% component "ui_core.dropdown_menu" items=actions %}` |

## Affichage de données

| Nom | Responsabilité | Obligatoire | Facultatif/défaut | Slots | Loading/empty/accessibilité | Exemple |
|---|---|---|---|---|---|---|
| `ui_core.stat_card` | KPI | aucun | `label`, `value`, `unit`, `description`, `icon`, `tone`, `trend`, `period`, `target`, `progress`, `href`, `loading`, `empty`, `compact` | aucun | skeleton, empty, valeur longue; ton inconnu `neutral` | `{% component "ui_core.stat_card" label="Total" value=total progress=80 %}` |
| `ui_core.data_table` | Tableau générique | aucun | `id`, alias `table_id`, `caption`, `headers`, `rows`, `density`, `selectable`, `selected_count`, `result_count`, `page`, `page_count`, `loading`, `error`, `permission_denied` | `actions`, `footer` | caption SR, sticky header, horizontal scroll, empty/error/permission | `{% component "ui_core.data_table" headers=headers rows=rows density="compact" %}` |
| `ui_core.status_badge` | État compact | aucun | `label=""`, `tone="neutral"`, `icon=""`, `dot=False` | aucun | texte toujours présent; fallback neutral | `{% component "ui_core.status_badge" label="Actif" tone="success" %}` |
| `ui_core.empty_state` | Absence de données | aucun | `title`, `message`, `icon`, `action_label`, `action_url` | aucun | action rendue seulement si complète | `{% component "ui_core.empty_state" title="Vide" %}` |
| `ui_core.progress_bar` | Progression bornée | aucun | `value=0`, `label`, `tone`, `show_value`, `compact` | aucun | `role=progressbar`, valeur bornée 0..100 | `{% component "ui_core.progress_bar" value=72 %}` |
| `ui_core.timeline` | Suite chronologique | aucun | `items=[]`, `compact`, `empty_message` | aucun | liste ordonnée et état vide | `{% component "ui_core.timeline" items=events %}` |
| `ui_core.chart_panel` | Graphique générique | aucun | `id`, `title`, `description`, `chart_type`, `labels`, `datasets`, `loading`, `error` | aucun | canvas nommé, empty/error/loading | `{% component "ui_core.chart_panel" labels=labels datasets=series %}` |

## Forms

| Nom | Responsabilité | Obligatoire | Facultatif/défaut | Slots | Comportement | Exemple |
|---|---|---|---|---|---|---|
| `ui_core.filter_bar` | Filtres et recherche | aucun | `filters`, `action`, `method`, `submit_label`, `reset_url`, `target`, `trigger`, `indicator`, `density`, `active_filters` | aucun | labels, clear non-submit, HTMX optionnel, density fallback | `{% component "ui_core.filter_bar" filters=filters target="#results" %}` |
| `ui_core.form_field` | Champ uniforme | aucun | `id`, `name`, `label`, `value`, `type`, `placeholder`, `help_text`, `error`, `success`, `required`, `disabled`, `readonly`, `options` | aucun | label, `aria-describedby`, états validation | `{% component "ui_core.form_field" id="email" type="email" %}` |

## Feedback

| Nom | Responsabilité | Obligatoire | Facultatif/défaut | Slots | États/accessibilité | Exemple |
|---|---|---|---|---|---|---|
| `ui_core.alert` | Message persistant | aucun | `title`, `message`, `tone="info"`, `dismissible=False` | `default` | danger=`alert`, fallback neutral | `{% component "ui_core.alert" message="Information" %}` |
| `ui_core.toast` | Message transitoire | aucun | `message=""`, `tone="info"`, `visible=True` | aucun | `role=status`, fallback info | `{% component "ui_core.toast" message="Enregistré" tone="success" %}` |
| `ui_core.loading_overlay` | Chargement local | aucun | `loading=False`, `label` | aucun | absent si false, `aria-live` si true | `{% component "ui_core.loading_overlay" loading=True %}` |
| `ui_core.confirm_dialog` | Confirmation générique | aucun | `id`, alias `dialog_id`, titre/message/libellés, `tone="danger"`, `open=False` | aucun | Échap, focus trap/retour; tone primary/danger | `{% component "ui_core.confirm_dialog" id="confirm" trigger_label="Supprimer" %}` |

## Overlays

| Nom | Responsabilité | Obligatoire | Facultatif/défaut | Slots | États/accessibilité | Exemple |
|---|---|---|---|---|---|---|
| `ui_core.modal` | Dialogue centré | aucun | `id`, alias `modal_id`, `title`, `trigger_label`, `open=False` | `default`, `footer` | Échap, modal ARIA, focus trap/retour | `{% component "ui_core.modal" id="edit" trigger_label="Modifier" %}` |
| `ui_core.drawer` | Panneau latéral | aucun | `id`, alias `drawer_id`, `title`, `trigger_label`, `side="right"`, `open=False` | `default` | side inconnu -> right; Échap et focus | `{% component "ui_core.drawer" id="detail" trigger_label="Détails" %}` |

## Événements

### Événements et HTMX

- `ui:toast` : événement DOM générique. Détail :
  `{message, tone, duration}`. Les tons acceptés sont `info`, `success`,
  `warning`, `danger`.
- Une réponse HTMX peut émettre le même événement via `HX-Trigger`.
- `uiOverlay(initiallyOpen)` gère ouverture, Échap, focus trap, retour du focus
  et verrouillage du scroll.
- `content_url` de modal/drawer charge un fragment dans une cible interne stable.
- `action_url` et `target` de confirmation exécutent une requête POST HTMX.
- `window.ESFEUI.charts.render(root)` détruit toute instance précédente avant
  rendu et est rappelé après `htmx:afterSwap`.

### Fallbacks et erreurs

- `tone` inconnu : `neutral`, sauf toast qui revient à `info`.
- `density` inconnue : `comfortable`.
- `chart_type` inconnu : `line`.
- progression hors bornes : ramenée à 0..100.
- données absentes : état vide explicite; erreur fournie : alerte locale.
