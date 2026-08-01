# Shared Domain Components Browser QA

**Date :** 26 juillet 2026  
**Environnement :** serveur Django local `127.0.0.1:8015`

## Compte de test

- Utilisateur: `ui_catalog_qa`
- Mot de passe: `Catalog123!`

## Parcours vérifiés

1. Connexion au portail.
2. Ouverture de `/ui/system/domains/`.
3. Ouverture du drawer du composant `account.profile_card`.
4. Chargement de la démo HTMX du composant.

## Résultats

- Navigation principale conservée pendant l'ouverture du catalogue: OK
- Drawer de détail: OK
- Fragment de démo: OK
- Erreurs page: 0
- Erreurs console: 0
- Réponses HTTP en échec: 0

## Captures

Les captures de QA sont stockées dans `_audit/shared_domain_components/`.

- `catalog-qa-2.png`
- `catalog-drawer-profile-qa-2.png`

## Remarque

Une première passe sur un serveur sans reload servait encore l'ancien code et montrait des artefacts de validation. La passe finale a été faite sur `127.0.0.1:8015` avec le code courant.
