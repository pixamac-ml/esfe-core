# Architecture front-end officielle ESFE Core

> Phase 1.75 : la séparation PublicShell/AppShell est désormais effective sur
> `/ui/system/`, qui utilise une base interne autonome et des interactions HTMX.

## 1. Vision générale

UI Core existe pour fournir une plateforme front-end unique aux espaces applicatifs ESFE. Il centralise la coque, la navigation visuelle, la structure des pages, l'affichage générique des données, le feedback, les overlays, l'accessibilité et les design tokens.

UI Core ne centralise jamais les modèles, calculs, permissions, règles d'annexe, querysets ou workflows métier. Il empêche la multiplication des architectures par rôle : les données, priorités, widgets et autorisations changent, mais la coque et les composants génériques restent communs.

Les pages publiques, documents imprimables et composants métier spécialisés conservent leurs contraintes propres.

## 2. Architecture globale

### Séparation des expériences

```text
Site public
`-- PublicShell (`templates/base.html`)
    |-- navbar publique
    |-- contenu éditorial
    |-- widgets publics
    `-- footer public

Portail interne
`-- AppShell (`ui_core.app_shell`)
    |-- AppSidebar
    |-- AppTopbar
    |-- Workspace
    `-- Overlays
```

`PublicShell` porte la navigation vitrine, le référencement, les appels à
candidature et le footer institutionnel. `AppShell` porte exclusivement les
outils internes authentifiés. Une page AppShell ne doit jamais hériter des blocs
publics par défaut. Le catalogue utilise `ui/templates/ui/system_base.html`;
les pages publiques existantes restent inchangées.

```text
AppShell
|-- AppSidebar
|-- AppTopbar
`-- Workspace
    |-- Breadcrumb
    |-- PageHeader
    |-- PageSection
    |   |-- ContentGrid
    |   |-- Panel
    |   |   `-- Widget métier
    |   |       `-- Composants UI Core
    |   `-- DataTable / FilterBar / Feedback
    `-- Overlays
        |-- Modal
        `-- Drawer
```

- `AppShell` porte le layout responsive et la zone principale.
- `AppSidebar` affiche une navigation déjà autorisée et préparée.
- `AppTopbar` affiche le titre, un contexte générique et les actions globales.
- Le workspace compose les éléments d'une page, sans devenir un composant monolithique.
- Les widgets métier gardent leurs contrats Django/HTMX et composent UI Core.
- Les overlays traitent uniquement l'interaction visuelle locale.

## 3. Responsabilités des couches

### Backend métier

Modèles, règles métier, calculs, permissions, filtrage obligatoire par annexe, querysets et services métier.

### Services de présentation

Préparation des données UI, navigation autorisée, mapping des statuts vers des tons, contrats de présentation. Ils peuvent consommer les API d'accès officielles, mais ne les remplacent pas. Ils ne cachent pas de requête métier dans un composant.

### Composants métier

Notes, paiements, inscriptions, admissions, emploi du temps, documents et workflows spécialisés. Ils conservent leurs événements et contrats HTMX.

### UI Core

Structure, présentation, interactions génériques, responsive, accessibilité et tokens. UI Core reçoit des données prêtes à afficher.

### Atoms et contrôles

Bouton, icône, badge atomique, avatar, input, label, spinner et skeleton. Ils ne dépendent d'aucune couche métier.

## 4. Dépendances autorisées

```text
Vue Django
|-- services métier
|-- services de présentation
`-- composants métier (données préparées)

Composant métier
|-- UI Core
`-- atoms / formulaires génériques

UI Core
`-- atoms / contrôles génériques

Atoms
`-- aucune couche métier
```

Le service `ui.services.navigation` peut appeler `can_access()` et `get_user_scope()` car il appartient à la couche de présentation, pas à UI Core.

## 5. Dépendances interdites

- UI Core n'importe aucun modèle Django et n'appelle pas l'ORM.
- UI Core n'appelle ni `can_access()` ni `get_user_scope()`.
- UI Core ne connaît ni positions, ni rôles, ni annexes.
- UI Core ne construit aucun queryset.
- UI Core ne contient aucun calcul académique ou financier.
- Un composant générique n'importe pas un composant métier.
- Un composant public n'est pas forcé dans le shell Portal.
- Un document imprimable ne dépend pas du shell écran.
- Alpine ou JavaScript ne prend aucune décision d'autorisation.

## 6. Anatomie officielle d'une page

```text
Page
|-- Breadcrumb (facultatif)
|-- PageHeader
|   |-- titre
|   |-- description
|   `-- actions
|-- barre de contexte (facultative)
|-- KPI (facultatifs)
|-- filtres (facultatifs)
|-- contenu principal
|   |-- Panel
|   |-- DataTable
|   |-- widget métier
|   `-- EmptyState
`-- Modal / Drawer / Toast
```

Syntaxe réellement utilisée :

```django
{% load component_tags %}
{% component "ui_core.page_header" title="Étudiants" subtitle="Suivi de la cohorte" %}
  {% fill "actions" %}
    <button type="button">Ajouter</button>
  {% endfill %}
{% endcomponent %}

{% component "ui_core.page_section" title="Synthèse" %}
  {% component "ui_core.content_grid" columns=3 %}
    {% component "ui_core.stat_card" label="Inscrits" value=student_count tone="primary" %}{% endcomponent %}
  {% endcomponent %}
{% endcomponent %}
```

Lorsqu'un composant reçoit des slots nommés, son contenu par défaut utilise explicitement `{% fill "default" %}`.

## 7. Anatomie officielle d'un dashboard

Un dashboard compose `AppShell`, la navigation fournie par un service, `PageHeader`, KPI, sections, panels, widgets métier, feedback et overlays. Il n'est pas un composant monolithique.

Le template principal reste court. Les sections importantes sont séparées en partiels. Les widgets métier gardent leurs URLs, cibles et événements HTMX. Les différences entre rôles proviennent des données et autorisations préparées, jamais d'une nouvelle coque.

## 8. Conventions de nommage

- Fichiers Python : `snake_case`.
- Nom public : `ui_core.nom_du_composant`.
- Paramètres génériques : anglais, sémantiques et stables.
- Ton sémantique : `tone`, avec `neutral`, `primary`, `info`, `success`, `warning`, `danger`.
- Identifiant DOM : `id`; les alias Phase 1 `table_id`, `modal_id`, `drawer_id`, `dialog_id` restent temporairement acceptés.
- Aucun suffixe `v2`, `new`, `final`, `clean` ou `modern`.
- Aucun composant générique dupliqué par rôle.
- Aucun nom fondé uniquement sur une couleur ou un effet visuel.

## 9. Conventions HTMX

- HTMX met à jour des zones métier, pas la coque complète.
- Sidebar et topbar ne sont pas réinjectées à chaque requête.
- Les IDs de cibles sont stables et fournis par la page.
- Les événements personnalisés sont documentés par le composant métier producteur.
- UI Core n'invente aucun événement métier.
- `ui_core.loading_overlay` fournit l'indicateur visuel de chargement.
- Une réponse partielle charge elle-même les bibliothèques de tags Django requises.
- Les endpoints de démonstration héritent exactement de la protection de la page.
- Une démonstration ne touche aucune donnée métier et cible un fragment stable.
- `hx-indicator` rend toute attente visible et `htmx:responseError` produit un
  feedback générique.

## 10. Conventions Alpine.js

Alpine gère l'état visuel local : navigation mobile, menus, accordéons, modales et drawers. Il ne calcule aucune donnée métier, ne décide aucune autorisation, ne stocke aucune donnée sensible et ne réplique pas un workflow Django.

Les overlays UI Core ferment sur Échap, confinent le focus et le rendent au déclencheur.

## 11. Conventions JavaScript

- Pas de grand script inline.
- Initialisation centralisée pour les comportements transversaux.
- Initialisation idempotente après swap HTMX.
- Bus événementiel documenté.
- Erreurs rendues visibles et récupérables.
- Aucune dépendance lourde sans validation architecturale.

Depuis la Phase 1.75, `static/src/js/ui_core/index.js` centralise :

- le contrôleur Alpine `uiOverlay`;
- la pile de toasts et l'événement `ui:toast`;
- l'initialisation/déstruction Chart.js;
- les réinitialisations idempotentes après `htmx:afterSwap`;
- les actions génériques clear/copy et le header CSRF HTMX.

Le script marque les contrôles liés avec `data-ui-bound` pour éviter les doubles
listeners. Il ne crée aucun événement ni état métier.

## 12. Responsive

### Desktop

Sidebar ouverte, contenu large, grilles KPI et tables complètes.

### Tablette

Sidebar en drawer, grilles réduites et actions regroupées.

### Mobile

Navigation hors-canvas, une colonne, actions prioritaires, tables avec scroll contrôlé ou vue carte métier. Aucune information critique ne devient inaccessible.

## 13. Accessibilité

- Focus visible sur les contrôles.
- Navigation clavier et lien d'évitement.
- Labels explicites et rôles ARIA adaptés.
- Contrastes fond/texte vérifiés.
- Fermeture des overlays par Échap.
- Confinement du focus et retour au déclencheur.
- La couleur n'est jamais le seul indicateur : texte, icône ou libellé l'accompagne.

## 14. Stratégie de migration

1. Stabiliser UI Core et ses contrats.
2. Migrer uniquement le dashboard Directeur des Études.
3. Valider fonctionnellement, visuellement, au clavier et sur mobile.
4. Valider HTMX, Alpine et isolation d'annexe.
5. Migrer progressivement les autres dashboards.
6. Employer des adaptateurs temporaires lorsque nécessaire.
7. Déprécier puis supprimer seulement après zéro référence et tests.

## 15. Règles non négociables

- Aucune nouvelle sidebar ou topbar générique par rôle.
- Aucune carte KPI parallèle sans évaluation de `ui_core.stat_card`.
- Aucun tableau générique concurrent.
- Aucun style inline évitable.
- Aucun accès ORM ou calcul de permission depuis UI Core.
- Aucun dashboard monolithique.
- Aucune suppression sans recherche globale et tests.
- Aucune migration simultanée de plusieurs dashboards.
- Aucun affaiblissement du filtrage par annexe.

## 16. Référence Phase 2 : Directeur des Études

Le dashboard actif du Directeur des Études est le premier pilote métier UI Core.
Il suit le flux `portal_dashboard` -> `_render_director_dashboard()` et compose :

- `portal/app_base.html`, base interne sans navigation ni footer publics ;
- un unique `ui_core.app_shell`, avec `app_sidebar` et `app_topbar` ;
- `portal/services/director_dashboard_presentation.py` pour les contrats de
  navigation, KPI, actions rapides et tableaux ;
- `#director-workspace` comme cible stable des huit sections HTMX ;
- les composants académiques existants à l'intérieur du workspace ;
- les overlays UI Core autour des contenus métier existants ;
- `static/src/js/portal/director_dashboard.js` comme adaptateur idempotent.

La vue et les services métier continuent de résoudre le rôle, le scope global ou
l'annexe avant de préparer la présentation. UI Core ne reçoit ni queryset ni règle
d'autorisation. Cette composition est la référence des prochaines migrations, qui
restent indépendantes et séquentielles.
