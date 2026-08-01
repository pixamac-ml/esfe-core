# Design tokens UI Core

> Phase 1.5 : l'audit complet est disponible dans
> `UI_CORE_TOKEN_AUDIT.md`. Les tokens de surface inverse, overlay et
> dimensions récurrentes ont été ajoutés sans remplacer les tokens historiques.

> Phase 1.75 complète l'échelle avec les états hover, active, selected,
> destructive et skeleton, la hauteur de contrôle, la densité des tables et les
> dimensions des graphiques/panels.

Les tokens sont additifs. Les couleurs historiques `primary`, `secondary`, `accent` et les classes existantes ne sont pas remplacées en phase 1.

## Couleurs

| Token | Valeur | Tailwind | Usage |
|---|---|---|---|
| marque | `#1e4f6f` | `ui-primary` | actions principales et repères |
| marque forte | `#163b53` | `ui-primary-strong` | hover et contraste |
| accent | `#f4b942` | `ui-accent` | signal secondaire, jamais seul indicateur |
| succès | `#177245` | `ui-success` | état validé |
| avertissement | `#9a5b00` | `ui-warning` | attention non bloquante |
| danger | `#b42318` | `ui-danger` | erreur ou action destructive |
| information | `#176b87` | `ui-info` | information neutre |
| surface | `#ffffff` | `ui-surface` | contenu principal |
| surface douce | `#f8fafc` | `ui-surface-soft` | fond d'application |
| surface atténuée | `#eef2f6` | `ui-surface-muted` | en-têtes et contrôles |
| bordure | `#dbe3ea` | `ui-border` | séparation |
| texte | `#17212b` | `ui-text` | texte principal |
| texte secondaire | `#5f6f7f` | `ui-text-muted` | aide et métadonnées |
| sidebar | `#17394d` | `ui-sidebar` | navigation |
| focus | `#1db5b0` | `ui-focus` | focus clavier visible |
| texte inverse | `#ffffff` | `ui-on-primary` | texte sur marque/sidebar |
| overlay | `#0f172a` | `ui-overlay` | fond des modales et drawers |
| hover | surface neutre | `ui-surface-hover` | survol des contrôles |
| actif | surface primaire atténuée | `ui-active` | navigation active |
| sélection | surface accentuée | `ui-selected` | ligne sélectionnée |
| skeleton | surface de chargement | `ui-skeleton` | placeholders |

Les variantes `*-soft` sont réservées aux fonds d'état. Un état doit toujours inclure texte, icône ou libellé; la couleur seule est interdite.

## Dimensions

| Token | Valeur | Tailwind |
|---|---:|---|
| sidebar ouverte | `17rem` | `w-ui-sidebar` |
| sidebar réduite | `4.5rem` | `w-ui-sidebar-collapsed` |
| topbar | `4rem` | `h-ui-topbar` |
| contenu maximal | `90rem` | `max-w-ui-content` |
| largeur minimale table | `36rem` | `min-w-ui-table` |
| hauteur maximale overlay | `85vh` | `max-h-ui-overlay` |
| padding desktop | `2rem` | `px-ui-desktop` |
| padding tablette | `1.5rem` | `px-ui-tablet` |
| padding mobile | `1rem` | `px-ui-mobile` |
| contrôle | `2.5rem` | `h-ui-control` |
| graphique | `20rem` | `h-ui-chart` |
| panel scrollable | `28rem` | `max-h-ui-panel` |

## Typographie officielle

`ui-display`, `ui-page-title`, `ui-section-title`, `ui-panel-title`, `ui-body`,
`ui-body-small`, `ui-label`, `ui-caption` et `ui-micro`. La valeur KPI utilise
le niveau de titre adapté à son conteneur et les chiffres tabulaires lorsque la
comparaison le nécessite.

## Rayons et ombres

| Usage | Valeur | Tailwind |
|---|---:|---|
| input/bouton | `0.375rem` | `rounded-ui-input`, `rounded-ui-button` |
| carte/modal | `0.5rem` | `rounded-ui-card`, `rounded-ui-modal` |
| badge | `9999px` | `rounded-ui-badge` |
| carte | ombre légère | `shadow-ui-card` |
| dropdown | ombre moyenne | `shadow-ui-dropdown` |
| drawer/modal | ombre forte | `shadow-ui-drawer`, `shadow-ui-modal` |

## Espacement

UI Core utilise l'échelle Tailwind standard (`1`, `2`, `3`, `4`, `5`, `6`, `8`) et les paddings de shell nommés. Une exception est autorisée pour les formats d'impression et les grilles temporelles métier.

## Règles

- Ne pas remplacer les tokens historiques avant migration du dashboard concerné.
- Employer les tokens sémantiques UI Core dans les nouveaux composants.
- Conserver un focus visible et un contraste lisible.
- Ne pas utiliser un rayon supérieur à `0.5rem` pour les cartes applicatives.
- Les pages publiques peuvent conserver une expression visuelle distincte.
