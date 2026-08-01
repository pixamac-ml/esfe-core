# Rapport UI Core - Phase 1.75

## 1. Resume executif

### Objectifs

Finaliser UI Core avant la migration des dashboards : isoler strictement l'interface
publique du shell portail, rendre `/ui/system/` navigable et interactive, completer
les composants generiques manquants, stabiliser les interactions HTMX/Alpine et
valider la fondation sur desktop, tablette et mobile.

### Resultat

- `/ui/system/` utilise un document interne autonome et n'affiche plus la navbar ni
  le footer publics.
- UI Core expose 27 composants publics repartis dans six familles techniques.
- Les tables, filtres, formulaires, overlays, confirmations, toasts, graphiques et
  etats de chargement sont demonstrables sans rechargement complet de page.
- Les scripts communs sont centralises dans `static/src/js/ui_core/index.js`.
- Les 57 tests UI passent, Django ne detecte aucune migration et Tailwind compile.
- La recette Playwright desktop, tablette et mobile est terminee et documentee.
- Aucun dashboard metier, modele, droit d'acces ou workflow metier n'a ete migre.

## 2. Separation public / portail

La cause de la navbar publique etait l'heritage direct de `base.html` par
`ui/templates/ui/system.html`. Les blocs publics de ce template sont affiches par
defaut.

La page systeme herite maintenant de `ui/templates/ui/system_base.html`, un shell
interne autonome qui charge uniquement les styles et scripts necessaires a UI Core.
La separation cible est documentee ainsi :

- `PublicShell` : pages institutionnelles et commerciales reposant sur `base.html`.
- `AppShell` : interfaces authentifiees, navigation applicative, sidebar et overlays.
- `SystemShell` : catalogue interne isole servant de reference a `AppShell`.

Les controles navigateur et les tests automatises confirment l'absence de navbar et
de footer publics sur `/ui/system/`.

## 3. Familles de composants

Les 27 noms publics `ui_core.*` sont organises sans rupture de compatibilite :

- `layout` : app shell, page header, page section, panel, content grid, breadcrumb.
- `navigation` : app sidebar, app topbar, nav group, nav item, tabs, dropdown menu.
- `data_display` : data table, stat card, status badge, empty state, progress bar,
  timeline, chart panel.
- `forms` : filter bar, form field.
- `feedback` : alert, toast, loading overlay, confirm dialog.
- `overlays` : modal, drawer.

## 4. Composants ajoutes

- `ui_core.tabs`
- `ui_core.dropdown_menu`
- `ui_core.progress_bar`
- `ui_core.timeline`
- `ui_core.chart_panel`
- `ui_core.form_field`

Chaque composant dispose d'une classe Django Component, d'un template, d'un export
public et d'une demonstration dans le catalogue.

## 5. Composants enrichis

- `data_table` : densites, tri, selection, compteur, pagination, actions, montants,
  statuts, header fixe et etats vide/erreur/interdit/chargement.
- `stat_card` : unite, periode, cible, progression, description, mode compact et
  etats vide/chargement.
- `filter_bar` : cible, declencheur et indicateur HTMX, densite, filtres actifs et
  remise a zero.
- `panel` : densite, ton, repli, chargement, erreur et contenu scrollable.
- `app_sidebar`, `nav_group`, `nav_item` : repli desktop, drawer mobile, groupes
  repliables, sous-navigation, compteurs et tooltips.
- `modal`, `drawer`, `confirm_dialog` : ouverture instantanee, contenu HTMX,
  focus piege, fermeture Escape, restitution du focus et blocage du scroll.

Les composants historiques restent disponibles. Ils ont ete reutilises ou
enveloppes lorsque leur responsabilite etait deja generique ; aucun composant
historique n'a ete supprime.

## 6. Interactions HTMX et Alpine

HTMX prend en charge la recherche, les filtres, le tri, la densite, la pagination,
la validation de formulaire, la confirmation, le rafraichissement et les fragments
d'overlay. Les recherches concurrentes utilisent `hx-sync` pour eviter les swaps
obsoletes. Les indicateurs et les reponses d'erreur sont geres globalement.

Alpine gere les etats locaux instantanes : sidebar, navigation mobile, panneaux,
tabs, menus, palette de commandes et overlays. Le controleur d'overlay centralise
le piege de focus, Escape, le retour du focus et le verrouillage du document.

Le script `static/src/js/ui_core/index.js` expose `window.ESFEUI` et centralise :

- la pile de toasts, la pause au survol et la fermeture manuelle ;
- les overlays accessibles ;
- l'initialisation idempotente des graphiques Chart.js apres swap ;
- les actions copier/effacer sans double binding ;
- les hooks HTMX, CSRF et erreurs de reponse.

## 7. Endpoints de demonstration

Les endpoints suivants sont proteges par le meme controle que la page systeme :
utilisateur authentifie en `DEBUG`, superutilisateur en production.

- `system_demo_table`
- `system_demo_modal`
- `system_demo_drawer`
- `system_demo_form`
- `system_demo_confirm`
- `system_demo_refresh`
- `system_demo_error`

Ils reposent sur des donnees statiques, sans ORM, donnees metier ou visibilite
inter-annexes.

## 8. Page `/ui/system/`

Le catalogue affiche le titre officiel
`UI Core - Design System officiel du portail ESFE` et la version
`Phase 1.75 - Version fonctionnelle et interactive`.

Ses 15 sections ancrees couvrent les fondations, navigation, layout, KPI, tables,
filtres, formulaires, feedback, overlays, productivite, visualisation, planning,
responsive, accessibilite et composition de dashboard. La palette `Ctrl+K` permet
une navigation rapide. Les demonstrations importantes restent sur la page.

## 9. API, tokens et dependances

Les contrats des 27 composants, variantes, valeurs de repli et evenements sont
documentes dans `UI_CORE_API_CONTRACTS.md`. L'architecture, les frontieres, la
matrice de consolidation, l'inventaire et les dependances ont ete actualises.

Les tokens couvrent maintenant les surfaces hover/active/selected, skeleton,
destructive, controles, graphiques, timeline, hauteurs de panneaux et l'echelle
typographique. Le scan final ne releve ni token brut dans les nouveaux templates et
scripts, ni dependance interdite. Tailwind analyse aussi les scripts UI Core.

## 10. Accessibilite et responsive

- Regions live pour les toasts et messages d'etat.
- Etats ARIA pour tabs, navigation repliable et overlays.
- Piege de focus, fermeture Escape et restitution du focus valides.
- Focus visible commun via `ui-focus-ring`.
- Boutons non-submit tous types explicitement.
- Navigation clavier testee sur les principales interactions.
- Absence de debordement horizontal a 1440, 900, 390 et 720 pixels CSS.
- Sidebar desktop 272/72 pixels et drawer mobile fonctionnels.

La validation avec un lecteur d'ecran reel reste un audit specialise a programmer ;
elle ne remplace pas les controles ARIA, focus et clavier deja effectues.

## 11. Tests et recette manuelle

### Validation automatisee

| Commande | Resultat |
|---|---|
| `python manage.py check` | OK, aucun probleme |
| `python manage.py makemigrations --check --dry-run` | OK, aucune migration |
| `python manage.py test ui --settings=config.settings_test_local --keepdb` | OK, 57/57 en 9.210 s |
| `npm run build:css` | OK en 15.936 s |
| Suite `ui core accounts portal` isolee | 339 tests, 5 echecs et 3 erreurs preexistants |

La baseline UI comptait 47 tests verts. Dix tests ont ete ajoutes pour les nouveaux
composants, la protection des endpoints, les interactions, les etats, les types de
boutons et l'idempotence des scripts.

Une premiere execution concurrente sur la meme base SQLite a produit des verrous de
base artificiels. Le resultat de reference ci-dessus provient d'une nouvelle
execution isolee : 339 tests en 67.621 s.

### Recette manuelle

La recette Playwright Chromium a ete executee sur :

- desktop 1440 x 900 ;
- tablette 900 x 1024 ;
- mobile 390 x 844 ;
- largeur CSS 720 pixels, equivalente au controle de reflow desktop a 200 %.

Recherche, filtres, tri, pagination, densite, tabs, dropdown, sidebar, modal,
drawer, confirmation, formulaires invalides/valides, toasts, erreur 500 simulee,
palette de commandes, focus et absence de navigation complete ont ete verifies.
Les captures sont conservees sous `_audit/ui_core_phase1_75_*.png`. Le detail est
dans `UI_CORE_PHASE1_75_MANUAL_QA.md`.

## 12. Problemes preexistants

La suite elargie conserve les huit defauts deja identifies hors UI Core :

- 3 erreurs : limitation du dashboard directeur par annexe, edition du profil,
  rendu du dashboard directeur dans `portal`.
- 5 echecs : formulaire de contact, panneau de revenu annuel gestionnaire, entree
  unique du dashboard directeur, verrouillage du semestre 2, preferences unifiees.

Ils ne sont pas provoques par Phase 1.75 et ne touchent pas les fichiers UI Core.

## 13. Risques restants

- Un test avec lecteur d'ecran reel reste recommande avant une certification WCAG.
- Les composants seront confrontes a des volumes et donnees reels pendant Phase 2.
- Le depot global contient de nombreuses modifications non liees ; le perimetre UI
  doit etre selectionne explicitement lors d'un futur commit.
- L'avertissement `caniuse-lite` du build CSS est informatif et n'empeche pas la
  compilation.

## 14. Fichiers ajoutes

- `ui/templates/ui/system_base.html`
- `static/src/js/ui_core/index.js`
- Classes et templates de `tabs`, `dropdown_menu`, `progress_bar`, `timeline`,
  `chart_panel` et `form_field`.
- Partials `ui/templates/ui/partials/system_*`.
- `docs/ui/UI_CORE_PHASE1_75_MANUAL_QA.md`
- `docs/ui/UI_CORE_PHASE1_75_REPORT.md`
- Captures `_audit/ui_core_phase1_75_{desktop,tablet,mobile}.png`

## 15. Fichiers modifies

- `ui/templates/ui/system.html`
- `ui/views.py`, `ui/urls.py`, `ui/test_ui_core.py`
- Composants existants sous `ui/components/ui_core/` et leurs templates.
- Exports `ui/components/__init__.py` et `ui/components/ui_core/**/__init__.py`.
- `static/src/css/input.css`, `static/public/css/main.css`,
  `tailwind.config.js`.
- Documentation d'architecture, API, tokens, inventaire, dependances et matrice
  sous `docs/ui/`.

## 16. Etat Git

`git status --short` reste volontairement charge par des travaux anterieurs dans
plusieurs applications. Aucun fichier non lie n'a ete restaure ou supprime. Aucun
commit et aucun push n'ont ete effectues. Le diff global n'est donc pas un diff
fiable du seul perimetre Phase 1.75.

## 17. Verdict

# PRÊT POUR LA PHASE 2

La separation des shells est effective, les composants principaux sont interactifs
sans rechargement complet, les overlays respectent le clavier et le focus, les tests
UI passent et la recette manuelle est documentee. La fondation peut accueillir la
migration du dashboard Directeur des Etudes prevue en Phase 2.
