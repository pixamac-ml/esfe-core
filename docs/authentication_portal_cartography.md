# Cartographie Portal et authentification

Statut initial du 12 juillet 2026. Cette cartographie accompagne la migration
progressive et ne remplace pas les contrôles d'accès dans les endpoints métier.

## Entrées et routage

| Route | Classe | État / décision |
| --- | --- | --- |
| `/accounts/login/` | PORTAL_ENTRY | Connexion SYSTEM actuelle, redirection par `portal.permissions` |
| `/accounts/register/` | PORTAL_ENTRY | Inscription PUBLIC; aucun dashboard SYSTEM ne doit en découler |
| `/accounts/dashboard/` | COMPATIBILITY_REDIRECT | Routage historique concurrent à consolider dans Portal |
| `/portal/dashboard/` | PORTAL_ENTRY | Entrée Portal SYSTEM générique actuelle |
| `/portal/student-dashboard/` | PORTAL_ENTRY | Dashboard étudiant spécialisé |
| `/portal/it/v2/` | SECURITY_FIX | Position `it_support` désormais obligatoire |
| `/accounts/manager/` | COMPATIBILITY_REDIRECT | Redirige vers Portal lorsque `AUTH_PORTAL_ROUTING_V2_ENABLED` est actif |
| `/portal/manager/` | PORTAL_ENTRY | Entrée officielle unique ANNEX_MANAGER, réutilise les modules gestionnaire |
| `/accounts/dashboard/finance/` | COMPATIBILITY_REDIRECT | ANNEX_MANAGER est redirigée vers Portal ; reste restreint aux agents finance compatibles |
| `/portal/access/regularization/` | SECURITY_FIX | État contrôlé pour position absente, inconnue ou annexe obligatoire manquante |
| `/accounts/dashboard/admissions/` | LEGACY_UI | Dashboard parallèle à migrer par position |
| `/accounts/dashboard/executive/` | LEGACY_UI | Dashboard parallèle à migrer par position |

## Modules réutilisables

- Les endpoints `accounts/htmx/manager/*`, widgets, exports et documents restent
  des `MODULE_ENDPOINT`. Leur logique métier ne doit pas être déplacée dans Portal.
- `accounts/dashboards/htmx_*.py`, `accounts/services/` et les services de
  `payments`/`shop` sont les briques à conserver pour ANNEX_MANAGER.
- Les workspaces et partials sous `templates/portal/` constituent le shell Portal
  moderne. Portal orchestre la navigation et le rendu, sans absorber les modèles.
- Le routage actuel utilise encore position, rôle historique, groupes et objets
  métier. `accounts/access.py` reste une couche de compatibilité jusqu'à Policy V2.

## Risques confirmés

- Une appartenance simultanée à `finance_agents` et `gestionnaire` conduit
  historiquement `/accounts/dashboard/` vers Finance, car Finance est testée avant
  Manager.
- Le profil communautaire `accounts/profile/` sert encore de fallback aux comptes
  sans dashboard et mélange les contextes PUBLIC et SYSTEM.
- La connexion classique et la connexion par carte avaient des contrôles d'état
  différents.
- Les routes IT spécialisées doivent toutes recevoir le même contrôle de position
  que leurs actions internes.

## Cible ANNEX_MANAGER

La route officielle définitive sera une entrée Portal dédiée qui réutilise les
modules gestionnaire existants. Tant que son shell et Policy V2 ne sont pas
activés, `/accounts/manager/` demeure l'interface de compatibilité fonctionnelle;
`/accounts/dashboard/finance/` ne doit plus devenir un second dashboard principal.
