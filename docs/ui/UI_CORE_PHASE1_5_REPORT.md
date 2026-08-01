# Rapport UI Core - Phase 1.5

## 1. Résumé exécutif

### Objectif

Consolider la fondation UI Core avant toute migration de dashboard : organiser les
composants par sous-domaines techniques, stabiliser leurs contrats publics, auditer
leurs dépendances et leurs tokens, renforcer la page système et documenter
l'architecture frontend cible.

### Résultat

- Les 21 composants `ui_core.*` sont répartis dans six sous-domaines cohérents.
- Leurs noms publics Django Components restent inchangés.
- Aucun composant historique et aucun dashboard métier n'ont été supprimés ou migrés.
- Les dépendances métier interdites sont absentes de UI Core.
- Les API, tokens, overlays clavier et tests d'architecture ont été renforcés.
- `/ui/system/` expose la fondation Phase 1.5 derrière son contrôle d'accès.
- Les 47 tests UI passent, Django ne détecte aucune migration et Tailwind compile.

### Verdict de préparation

**PRÊT POUR LA PHASE 2.**

Ce verdict concerne la fondation UI Core. La suite élargie conserve huit défauts
préexistants et ne doit pas être présentée comme entièrement verte.

## 2. Architecture avant/après

### Avant

Les 21 modules Python et les 21 templates étaient placés directement dans
`ui/components/ui_core/` et `ui/templates/ui_core/`. Cette structure plate rendait
les responsabilités moins lisibles et augmentait le coût de navigation.

### Après

```text
ui_core/
|-- layout/
|-- navigation/
|-- data_display/
|-- forms/
|-- feedback/
`-- overlays/
```

La structure sépare la composition de page, la navigation, la restitution de
données, les formulaires, les retours utilisateur et les surfaces superposées.
L'organisation physique change sans modifier l'espace de noms public `ui_core.*`.

## 3. Fichiers ajoutés

Documentation ajoutée pendant la consolidation :

- `docs/ui/FRONTEND_ARCHITECTURE.md`
- `docs/ui/UI_ARCHITECTURE_DIAGRAM.md`
- `docs/ui/UI_CORE_DEPENDENCY_AUDIT.md`
- `docs/ui/UI_CORE_API_CONTRACTS.md`
- `docs/ui/UI_CORE_TOKEN_AUDIT.md`
- `docs/ui/UI_CORE_PHASE1_5_REPORT.md`

Paquets ajoutés pour matérialiser les sous-domaines :

- `ui/components/ui_core/layout/__init__.py`
- `ui/components/ui_core/navigation/__init__.py`
- `ui/components/ui_core/data_display/__init__.py`
- `ui/components/ui_core/forms/__init__.py`
- `ui/components/ui_core/feedback/__init__.py`
- `ui/components/ui_core/overlays/__init__.py`

## 4. Fichiers déplacés

Chaque module Python et son template homologue ont été déplacés selon la même
correspondance :

| Ancien chemin sous `ui_core/` | Nouveau sous-domaine |
|---|---|
| `app_shell.py` / `app_shell.html` | `layout/` |
| `breadcrumb.py` / `breadcrumb.html` | `layout/` |
| `content_grid.py` / `content_grid.html` | `layout/` |
| `page_header.py` / `page_header.html` | `layout/` |
| `page_section.py` / `page_section.html` | `layout/` |
| `panel.py` / `panel.html` | `layout/` |
| `app_sidebar.py` / `app_sidebar.html` | `navigation/` |
| `app_topbar.py` / `app_topbar.html` | `navigation/` |
| `nav_group.py` / `nav_group.html` | `navigation/` |
| `nav_item.py` / `nav_item.html` | `navigation/` |
| `data_table.py` / `data_table.html` | `data_display/` |
| `empty_state.py` / `empty_state.html` | `data_display/` |
| `stat_card.py` / `stat_card.html` | `data_display/` |
| `status_badge.py` / `status_badge.html` | `data_display/` |
| `filter_bar.py` / `filter_bar.html` | `forms/` |
| `alert.py` / `alert.html` | `feedback/` |
| `confirm_dialog.py` / `confirm_dialog.html` | `feedback/` |
| `loading_overlay.py` / `loading_overlay.html` | `feedback/` |
| `toast.py` / `toast.html` | `feedback/` |
| `drawer.py` / `drawer.html` | `overlays/` |
| `modal.py` / `modal.html` | `overlays/` |

Les chemins complets sont respectivement
`ui/components/ui_core/<sous-domaine>/...` et
`ui/templates/ui_core/<sous-domaine>/...`.

## 5. Fichiers modifiés

| Fichier ou groupe | Raison |
|---|---|
| `ui/components/ui_core/__init__.py` | importer explicitement les sous-domaines |
| modules UI Core déplacés | corriger `template_name`, normaliser les paramètres et fallbacks |
| templates UI Core déplacés | tokens sémantiques, états accessibles et interactions Alpine |
| `ui/templates/ui/system.html` | présenter la hiérarchie, tous les composants et un assemblage complet |
| `ui/views.py` | fournir uniquement les données génériques de la page système |
| `ui/test_ui_core.py` | couvrir noms publics, chemins, API, dépendances, fallbacks et clavier |
| `tailwind.config.js` | déclarer les tokens sémantiques et dimensions UI Core |
| `static/src/css/input.css` | compléter les primitives/tokens de la fondation |
| `static/public/css/main.css` | sortie reconstruite par `npm run build:css` |
| `docs/ui/UI_COMPONENT_INVENTORY.md` | refléter les nouveaux chemins et corriger la classification |
| autres documents Phase 1 sous `docs/ui/` | signaler la consolidation Phase 1.5 sans réécrire l'historique |

Aucun modèle, migration, service métier, permission, calcul, filtrage par annexe ou
dashboard métier n'a été modifié par la Phase 1.5.

## 6. API normalisées

- `ui_core.app_topbar` expose désormais `context_label`; l'ancien nom trop métier
  `branch_name` n'est plus le contrat de référence.
- `ui_core.app_sidebar` expose `user_meta`; l'ancien `user_role` trop spécifique
  n'est plus le contrat de référence.
- `ui_core.data_table`, `ui_core.modal`, `ui_core.drawer` et
  `ui_core.confirm_dialog` utilisent officiellement `id`.
- Les alias `table_id`, `modal_id`, `drawer_id` et `dialog_id` restent acceptés
  pour préserver la compatibilité.
- Les variantes inconnues de badge, alerte, toast et statistique retombent sur un
  rendu neutre documenté.
- Les valeurs facultatives, slots, états vides et responsabilités d'accessibilité
  des 21 composants sont décrits dans `UI_CORE_API_CONTRACTS.md`.

Les 21 noms enregistrés `ui_core.*` sont inchangés et testés.

## 7. Dépendances auditées

### Violations trouvées

L'audit initial a relevé des paramètres de présentation nommés d'après le métier
(`branch_name`, `user_role`) et une dépendance autorisée mais à isoler :
`ui/services/navigation.py` consomme `accounts.access`.

### Violations corrigées

Les paramètres génériques ont remplacé les noms métier. Un scan AST et template
vérifie désormais l'absence :

- d'import d'application métier ou de `django.db`;
- d'accès `.objects`;
- d'appel direct à `can_access()` ou `get_user_scope()`;
- d'inclusion de template métier dans UI Core.

### Violations restantes

Aucune dépendance interdite n'est détectée dans `ui/components/ui_core/` ou
`ui/templates/ui_core/`. Le service de navigation conserve volontairement sa
dépendance descendante vers l'API publique `accounts.access`; les composants ne la
connaissent pas. La petite duplication Alpine des trois overlays reste locale et
documentée plutôt que d'introduire prématurément un gestionnaire JavaScript global.

## 8. Tokens audités

Les couleurs génériques répétées ont été remplacées par des tokens UI Core :
`ui-surface`, `ui-on-primary`, `ui-overlay` et les variantes sémantiques existantes.
Les dimensions récurrentes ont reçu des noms : `ui-table`, `ui-overlay`,
`ui-skip`, `ui-caption` et `ui-micro`.

Le scan final ne trouve ni couleur hexadécimale ni classe visuelle brute
`bg-white`, `text-white`, `bg-black` ou `text-black` dans les templates UI Core.
Les seules correspondances à la syntaxe entre crochets sont les sélecteurs
JavaScript `[tabindex]` nécessaires au piège de focus; ce ne sont pas des tokens
visuels. Les exceptions et règles d'évolution sont consignées dans
`UI_CORE_TOKEN_AUDIT.md`.

## 9. Tests exécutés

### Baseline Phase 1.5

| Commande | Résultat |
|---|---|
| `python manage.py check` | PASS, 0 problème |
| `python manage.py test ui --settings=config.settings_test_local --keepdb` | PASS, 40/40 |
| `npm run build:css` | PASS, avertissement Browserslist uniquement |

### Validation finale

| Commande | Résultat |
|---|---|
| `python manage.py check` | PASS, 0 problème |
| `python manage.py makemigrations --check --dry-run` | PASS, aucune modification détectée |
| `python manage.py test ui --settings=config.settings_test_local --keepdb` | PASS, 47/47 en 7,641 s |
| `python manage.py test --settings=config.settings_test_local --keepdb ui core accounts portal` | 329 tests, 5 échecs, 3 erreurs en 190,057 s |
| `npm run build:css` | PASS en 11,183 s, avertissement `caniuse-lite` obsolète |

Les sept tests UI ajoutés couvrent notamment la nouvelle arborescence, les 21 noms
publics, les dépendances interdites, les templates métier, les valeurs longues et
facultatives, les fallbacks inconnus, les états vides et le clavier des overlays.

### Défauts préexistants retrouvés

Échecs :

1. `core.tests.ContactFormTests.test_contact_post_creates_message_without_serialization_error`
2. `accounts.tests.ManagerDashboardRegressionTests.test_manager_report_section_renders_annual_revenue_panel`
3. `accounts.tests.PortalPhaseOneTests.test_portal_dashboard_renders_director_dashboard_from_single_entry`
4. `accounts.tests.PortalPhaseOneTests.test_student_semester_two_is_locked_until_semester_one_is_validated`
5. `accounts.tests.ProfileCenterTests.test_edit_preferences_creates_and_updates_unified_preferences`

Erreurs :

1. `accounts.tests.PortalPhaseOneTests.test_director_dashboard_is_limited_to_its_branch` : fixture créant une seconde année active
2. `accounts.tests.ProfileCenterTests.test_edit_profile_updates_identity_and_contact_fields` : `form_kwargs` non défini
3. `portal.tests.DirectorDashboardRenderTests.test_director_dashboard_renders` : appel de `create_user` sur la classe `User`

La baseline Phase 1 ciblée rapportait déjà les mêmes catégories avec 322 tests,
5 échecs et 3 erreurs. La hausse à 329 correspond aux sept tests UI ajoutés, tous
verts. **Aucune nouvelle erreur UI Core n'est apparue. La suite élargie ne passe
pas intégralement.**

## 10. État de `/ui/system/`

- Route : `/ui/system/`, nommée `ui:system`.
- Protection : `login_required`; en production, accès superutilisateur uniquement;
  en `DEBUG`, accès aux utilisateurs authentifiés.
- Vérification HTTP non authentifiée : `302` vers
  `/accounts/login/?next=/ui/system/`.
- Rendu : titre « UI Core - Fondation officielle du portail » et version
  architecturale Phase 1.5.
- Responsive : shell, navigation, grilles, panneaux, table et overlays utilisent
  les contraintes responsive de la fondation.
- Présentation : layout, navigation, en-tête, grilles, panneaux, statistiques,
  badges, table, filtres, état vide, alertes, toast, chargement, modal, drawer,
  confirmation et page assemblée complète.
- Données : exemples techniques uniquement, aucune donnée métier réelle.

## 11. Risques restants

- **Technique** : les défauts préexistants de `core`, `accounts` et `portal`
  empêchent une suite élargie entièrement verte.
- **Architecture** : un seul dashboard pilote pourra valider la frontière entre
  services d'adaptation métier et composants génériques.
- **Visuel** : la page système valide la cohérence, mais une recette sur navigateurs
  et tailles réelles reste nécessaire pendant le pilote.
- **HTMX** : aucun dashboard réel migré ne valide encore tous les remplacements,
  erreurs réseau, indicateurs et restaurations de focus.
- **Alpine** : les overlays ont Escape, piège de focus et retour au déclencheur;
  les scénarios imbriqués devront rester interdits ou être contractualisés.
- **Accessibilité** : la structure ARIA et le clavier sont couverts statiquement;
  un audit manuel lecteur d'écran, contraste et zoom 200 % reste requis.

## 12. Verdict Phase 2

**PRÊT POUR LA PHASE 2**

La fondation possède une arborescence lisible, des noms publics stables, des
contrats documentés, des tokens sémantiques, une page de référence protégée et
47 tests ciblés verts. Les défauts de la suite élargie sont antérieurs, reproduits
et sans lien avec la consolidation. Ils restent néanmoins à traiter séparément.

## 13. Proposition de Phase 2

La Phase 2 doit migrer **uniquement le dashboard du Directeur des Études** comme
pilote. Elle devra préserver strictement les permissions, le filtrage par annexe,
les contrats HTMX et les workflows existants, puis comparer le rendu et les tests
avant/après. Aucun autre dashboard ne doit entrer dans ce périmètre.

## 14. État Git

Commandes exécutées :

```powershell
git status --short
git diff --stat
```

Le worktree était déjà fortement modifié avant cette mission et contient des
changements métier, rapports, captures et fichiers non suivis hors périmètre. Ils
n'ont pas été annulés ni incorporés à la consolidation. Le statut pertinent pour
UI Core comprend :

```text
M  config/urls.py
M  config/urls_test_local.py
M  static/public/css/main.css
M  static/src/css/input.css
M  tailwind.config.js
M  ui/components/__init__.py
M  ui/urls.py
M  ui/views.py
?? docs/ui/
?? ui/components/ui_core/
?? ui/services/
?? ui/templates/ui/system.html
?? ui/templates/ui_core/
?? ui/test_ui_core.py
```

Le `git diff --stat` global, qui mélange les travaux antérieurs, indique 86 fichiers
suivis modifiés, 3 571 insertions et 720 suppressions, auxquels s'ajoutent les
nouveaux fichiers non suivis. Ce total ne représente donc pas le diff isolé de la
Phase 1.5.

Aucun commit et aucun push n'ont été effectués.
