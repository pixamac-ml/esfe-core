# Audit des design tokens UI Core

> Complément Phase 1.75 : les composants interactifs et la galerie finale ont
> été inclus dans l'audit.

## Corrections appliquées

| Fichier/famille | Valeur initiale | Correction |
|---|---|---|
| navigation, overlays, feedback, forms | `bg-white`, `text-white` | `bg-ui-surface`, `text-ui-on-primary` |
| overlays et shell mobile | `bg-black/45` | `bg-ui-overlay/45` |
| alert dismiss | `hover:bg-black/5` | `hover:bg-ui-overlay/5` |
| data table | `min-w-[36rem]` | `min-w-ui-table` |
| modal | `max-h-[85vh]` | `max-h-ui-overlay` |
| loading | `backdrop-blur-[1px]` | `backdrop-blur-ui-overlay` |
| skip link | `z-[100]` | `z-ui-skip` |
| microtexte navigation | `text-[10px]`, `text-[11px]` | `text-ui-micro`, `text-ui-caption` |
| indicateurs circulaires | `rounded-full` | `rounded-ui-badge` |

Tokens ajoutés : `ui-on-primary`, `ui-overlay`, `ui-table`, `ui-overlay` (hauteur et blur), `ui-skip`, `ui-caption`, `ui-micro`.

## Ajouts Phase 1.75

| Besoin réel | Token |
|---|---|
| hauteur des contrôles | `ui-control` |
| états hover/active/selected | `ui-surface-hover`, `ui-active`, `ui-selected` |
| skeleton | `ui-skeleton` |
| surface destructive | `ui-destructive-surface` |
| hauteur graphique | `ui-chart` |
| panel scrollable | `ui-panel` |
| position du point timeline | `ui-timeline-dot` |
| échelle typographique | `ui-display`, `ui-page-title`, `ui-section-title`, `ui-panel-title`, `ui-body`, `ui-body-small`, `ui-label` |

Les couleurs Chart.js sont fournies sous forme de noms sémantiques, puis résolues
par `window.ESFEUI.charts` depuis les variables CSS `--ui-chart-primary` et
`--ui-chart-primary-soft`. Les données de vue ne transportent plus de couleur
hexadécimale.

## Exceptions acceptées

| Classe | Justification |
|---|---|
| `max-w-sm`, `max-w-md`, `max-w-xl` | Contraintes structurelles ponctuelles Tailwind, non dimensions globales du shell. |
| `h-8`, `h-9`, `h-10`, `h-11` | Échelle standard pour contrôles tactiles et icônes. |
| `gap-*`, `space-y-*`, `p-*`, `px-*`, `py-*` | Échelle d'espacement Tailwind officielle. |
| opacités `/5`, `/10`, `/45`, `/80`, `/95` | États et superpositions appliqués à des couleurs sémantiques. |
| `max-w-*` de contenu textuel | Lisibilité locale; ne remplace pas `max-w-ui-content`. |

## Résultat

Aucune couleur hexadécimale n'est codée en dur dans les templates UI Core ou les
partials du catalogue. Les définitions hexadécimales restent centralisées dans
Tailwind/CSS, qui constituent la source des tokens. Les surfaces, bordures,
rayons, ombres, focus et dimensions récurrentes passent par les tokens. Les
classes structurelles Tailwind restent autorisées.
