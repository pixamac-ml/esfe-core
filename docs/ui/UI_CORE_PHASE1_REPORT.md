# Rapport UI Core - Phase 1

> Mise à jour Phase 1.5 : ce document conserve l'historique de la Phase 1.
> L'organisation plate décrite ci-dessous a ensuite été consolidée en
> `layout/`, `navigation/`, `data_display/`, `forms/`, `feedback/` et
> `overlays/`. Voir `UI_CORE_PHASE1_5_REPORT.md`.

Date : 25 juillet 2026  
Branche : `refactor/ui-core-foundation`

## 1. Résumé exécutif

Le dépôt contenait 235 composants Django Components enregistrés, plusieurs familles concurrentes de cartes, sidebars, topbars, tableaux, filtres et overlays, ainsi que des composants métier légitimement spécialisés. L'enregistrement réel appartient à `UiConfig.ready()` via `ui/components/__init__.py`; l'indication historique qui le situait dans `CoreConfig.ready()` n'est plus exacte.

La phase 1 crée une fondation additive `ui_core.*`, des tokens sémantiques, un service de navigation consommant `accounts.access`, une page protégée `/ui/system/`, une cartographie exhaustive et des tests. Aucun dashboard métier, modèle, service métier, calcul, permission ou workflow d'annexe n'a été migré.

Les composants historiques restent présents et enregistrés. Aucune migration de base de données n'a été créée.

## 2. Fichiers ajoutés

### Documentation

- `docs/ui/UI_COMPONENT_INVENTORY.md`
- `docs/ui/UI_CONSOLIDATION_MATRIX.md`
- `docs/ui/UI_DOMAIN_BOUNDARIES.md`
- `docs/ui/UI_DESIGN_TOKENS.md`
- `docs/ui/UI_DEPRECATION_PLAN.md`
- `docs/ui/UI_CORE_PHASE1_REPORT.md`

### Composants Python

Sous `ui/components/ui_core/` :

```text
__init__.py
alert.py
app_shell.py
app_sidebar.py
app_topbar.py
breadcrumb.py
confirm_dialog.py
content_grid.py
data_table.py
drawer.py
empty_state.py
filter_bar.py
loading_overlay.py
modal.py
nav_group.py
nav_item.py
page_header.py
page_section.py
panel.py
stat_card.py
status_badge.py
toast.py
```

### Templates

Sous `ui/templates/ui_core/` :

```text
alert.html
app_shell.html
app_sidebar.html
app_topbar.html
breadcrumb.html
confirm_dialog.html
content_grid.html
data_table.html
drawer.html
empty_state.html
filter_bar.html
loading_overlay.html
modal.html
nav_group.html
nav_item.html
page_header.html
page_section.html
panel.html
stat_card.html
status_badge.html
toast.html
```

Autres ajouts :

- `ui/services/__init__.py`
- `ui/services/navigation.py`
- `ui/templates/ui/system.html`
- `ui/test_ui_core.py`

## 3. Fichiers modifiés

| Fichier | Raison |
|---|---|
| `ui/components/__init__.py` | enregistrement additif des composants `ui_core.*` |
| `ui/views.py` | vue de référence protégée et données de démonstration |
| `ui/urls.py` | route nommée `ui:system` |
| `config/urls.py` | disponibilité de `/ui/system/` hors DEBUG pour les superutilisateurs |
| `config/urls_test_local.py` | exposition des routes UI dans la configuration de test isolée |
| `tailwind.config.js` | tokens additifs UI Core; les modifications antérieures du fichier sont conservées |
| `static/src/css/input.css` | variables CSS de dimensions/rayons UI Core |
| `static/public/css/main.css` | résultat généré par `npm run build:css` |

`core/apps.py` n'a pas été modifié : le propriétaire réel de l'enregistrement est `ui/apps.py`.

## 4. Composants conservés

- Atoms, formulaires et boutons existants : déjà réutilisables et à rapprocher progressivement des tokens.
- Composants publics blog, actualités, formations, home et about : contexte visuel différent du Portal.
- Documents PDF et imprimables : contraintes de format distinctes.
- Calendrier et emploi du temps : logique de placement spécialisée.
- Tous les composants historiques de dashboard : nécessaires pendant la coexistence.

## 5. Composants à fusionner

- `metric_card`, `stat_card`, `mini_stat`, `academic_stat_card` vers `ui_core.stat_card`.
- Cartes structurelles et `layout.panel` vers `ui_core.panel`.
- Sidebars spécialisées vers `ui_core.app_sidebar`.
- Topbars spécialisées vers `ui_core.app_topbar`.
- Layouts applicatifs vers `ui_core.app_shell`.
- Tableaux génériques vers `ui_core.data_table`.
- Filtres génériques vers `ui_core.filter_bar`.
- Alertes, badges, états vides et overlays vers leurs équivalents `ui_core`.

Les incompatibilités et l'ordre sont détaillés dans `UI_CONSOLIDATION_MATRIX.md`.

## 6. Composants dépréciés

Aucun composant n'est supprimé ni techniquement désenregistré dans cette phase. Les familles listées dans `UI_DEPRECATION_PLAN.md` sont des candidates, conditionnées à zéro référence, zéro import, tests globaux et recette du dashboard migré.

## 7. Composants métier maintenus

Les grilles et workflows de notes, admissions, inscriptions, paiements, documents, calendriers et panneaux IT restent spécialisés. Leur évolution cible consiste à composer `ui_core.panel`, `data_table`, `status_badge`, `alert`, `empty_state` et les contrôles génériques, sans déplacer leur logique métier dans UI Core.

## 8. Tests exécutés

### État initial

| Commande | Résultat |
|---|---|
| `python manage.py check` | PASS, 0 problème |
| `npm run build:css` | PASS; avertissement `caniuse-lite` obsolète |
| `python manage.py test --settings=config.settings_test_local` | arrêt avant tests : demande interactive de suppression de `test_db.sqlite3`, puis EOF |
| `python manage.py test --settings=config.settings_test_local --keepdb` | 710 tests, 6 échecs, 15 erreurs, 7 ignorés |

Les problèmes initiaux concernent notamment des validations/fixtures `academics`, des tests `accounts`, le formulaire contact `core` et des tests Portal. Ils existaient avant UI Core.

### Après implémentation

| Commande | Résultat |
|---|---|
| `python manage.py check` | PASS, 0 problème |
| `python manage.py makemigrations --check --dry-run` | PASS, aucune migration |
| `python manage.py test ui --settings=config.settings_test_local --keepdb` | PASS, 40/40 |
| `python manage.py test --settings=config.settings_test_local --keepdb ui core accounts portal` | 322 tests, 5 échecs, 3 erreurs |
| `npm run build:css` | PASS, terminé en environ 13 s; avertissement Browserslist |

La suite ciblée élargie retrouve des défauts de la baseline, dont :

- `accounts.views.edit_profile` : `form_kwargs` non défini;
- fixture d'année académique active concurrente;
- `portal.tests` : usage incorrect de `User.create_user`;
- formulaire contact ne créant pas le message attendu;
- assertions existantes du dashboard gestionnaire, du verrouillage semestriel et des préférences.

Les 40 tests UI, incluant tous les templates enregistrés, passent. La suite complète n'a pas été relancée une seconde fois après les changements, car la baseline de 710 tests prend environ 402 s et échoue déjà; la suite ciblée demandée a été exécutée.

## 9. Risques restants

- Le shell n'est utilisé que par la page système; aucun dashboard réel ne valide encore toutes les interactions HTMX/Alpine.
- `data_table` phase 1 est volontairement en lecture seule; édition, tri et pagination doivent être contractualisés pendant le pilote.
- Les modales et drawers fournissent les bases ARIA, clavier et responsive; un focus trap complet doit être validé dans le shell Portal.
- Les compteurs de notifications ne sont pas encore reliés au composant commun.
- L'inventaire utilise des comptes de références approximatifs; les noms courts peuvent produire des faux positifs.
- Le worktree contenait de nombreux changements utilisateur avant la mission. Toute préparation de commit devra sélectionner strictement les fichiers UI Core.

## 10. Proposition de phase 2

Migrer uniquement le dashboard Directeur des Études :

1. remplacer sa coque, sidebar et topbar par UI Core;
2. adapter les données de navigation sans modifier `accounts.access`;
3. migrer page header, KPI et panels;
4. conserver les widgets académiques métier;
5. tester HTMX, Alpine, notifications, clavier et responsive;
6. tester refus inter-annexes et utilisateur sans annexe;
7. comparer visuellement avant/après;
8. ne migrer aucun autre dashboard avant validation du pilote.

## Rollback

Le rollback de cette phase consiste à retirer la route système, les imports `ui_core`, le service, les nouveaux dossiers et les tokens additifs, puis reconstruire le CSS. Aucun rollback de données ou migration n'est requis. Les anciens composants n'ayant pas été remplacés, leurs dashboards restent la voie fonctionnelle actuelle.

## 11. État Git

Commandes :

```powershell
git status --short
git diff --stat
```

Résultat au moment du rapport :

```text
branche: refactor/ui-core-foundation
103 entrées dans git status --short
86 files changed, 3408 insertions(+), 720 deletions(-)
```

Ces totaux couvrent le worktree entier et incluent un volume important de modifications préexistantes étrangères à UI Core. Au début de la mission, le dépôt contenait déjà des modifications dans `academics`, `accounts`, `admissions`, `portal`, `secretary`, `tailwind.config.js`, `static/public/css/main.css` et divers rapports/assets. Elles n'ont pas été annulées ni attribuées à cette phase.

Aucun commit et aucun push n'ont été effectués.
