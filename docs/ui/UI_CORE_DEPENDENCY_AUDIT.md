# Audit des dépendances UI Core

Périmètre scanné :

- `ui/components/ui_core/`
- `ui/templates/ui_core/`
- `ui/services/`

Méthodes : recherche des imports, analyse AST dans les tests, recherche ORM/modèles, rôles/annexes, classes visuelles, JavaScript inline et références externes.

## Résultats

| Fichier | Type | Gravité | Description | Correction | Statut |
|---|---|---:|---|---|---|
| `navigation/app_topbar.py` | annexe implicite | moyenne | Paramètre `branch_name` trop spécifique pour un composant générique. | Renommé `context_label`; la vue prépare le texte. | corrigé |
| `navigation/app_sidebar.py` | rôle implicite | moyenne | Paramètre `user_role` exposait un concept métier. | Renommé `user_meta`. | corrigé |
| templates UI Core | styles | moyenne | Plusieurs `bg-white`, `text-white`, `bg-black` contournaient les tokens. | Remplacés par `ui-surface`, `ui-on-primary`, `ui-overlay`. | corrigé |
| templates UI Core | dimensions | faible | Dimensions récurrentes arbitraires pour table, overlay et z-index. | Tokens `ui-table`, `ui-overlay`, `ui-skip` ajoutés. | corrigé |
| overlays | accessibilité | élevée | Échap présent, mais pas de focus trap ni retour au déclencheur. | Contrôleur Alpine local avec trap et restitution du focus. | corrigé |
| overlays | duplication JS | faible | Contrôleur de focus similaire dans modal, drawer et confirmation. | Conservé localement pour éviter une abstraction prématurée; extraction si un quatrième contrat équivalent apparaît. | documenté |
| `ui/services/navigation.py` | permission/annexe | autorisée | Importe `can_access()` et `get_user_scope()`. | Dépendance maintenue dans la couche présentation; absente de UI Core. | conforme |
| `ui/services/navigation.py` | URL | faible | Fallback `#` si une URL optionnelle n'est pas disponible. | `NoReverseMatch` ciblée; item marqué désactivé. | conforme |

## Contrôles négatifs

- Aucun import de modèle ou de `django.db` sous `ui/components/ui_core`.
- Aucun appel `.objects`, queryset ou ORM.
- Aucun import d'application métier.
- Aucun appel direct à `can_access()` ou `get_user_scope()` depuis un composant.
- Aucun rôle, position ou annexe codé dans UI Core après normalisation.
- Aucun template métier importé.
- Aucun composant dépend implicitement de `/ui/system/`; cette page est seulement un consommateur.
- Aucun import circulaire détecté : les sous-domaines exportent vers le `__init__` racine, sans import inverse.

## Dépendance autorisée du service

`ui.services.navigation` transforme la politique d'accès officielle en données de navigation. Il ne crée aucune règle concurrente et ne filtre aucune donnée métier. Un utilisateur sans scope institutionnel ne reçoit que la navigation personnelle.

## Complément Phase 1.75

- Les endpoints `ui_system_demo_*` utilisent exclusivement `DEMO_ROWS` en
  mémoire et des fragments techniques.
- Aucun endpoint ne lit ou n'écrit un modèle.
- La protection commune `ui_system_access` reproduit la politique de
  `/ui/system/` sans appeler ni remplacer `accounts.access`.
- `static/src/js/ui_core/index.js` ne contient aucune permission, rôle, annexe,
  URL métier ou calcul métier.
- `ui/templates/ui/system_base.html` ne dépend pas de `base.html` et ne peut donc
  rendre ni navbar ni footer publics.
- Les composants historiques étudiés restent en place; aucun import ou
  enregistrement n'a été retiré.
