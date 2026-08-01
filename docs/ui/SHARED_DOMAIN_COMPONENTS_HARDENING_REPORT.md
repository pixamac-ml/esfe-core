# Shared Domain Components Hardening Report

**Date :** 26 juillet 2026  
**Branche :** `refactor/ui-core-foundation`

## Ce qui a été durci

- Ajout d'un catalogue métier dédié à `/ui/system/domains/`.
- Ajout de vues fragmentaires pour le détail et la démo de composant.
- Ajout de tests de route et de protection hors `DEBUG`.
- Correction du fallback d'avatar pour éviter un fichier statique absent.
- Définition d'un garde-fou global `window.sidebarCollapsed` pour neutraliser une référence runtime héritée.

## Ce qui a été vérifié

- `python manage.py check`
- `python manage.py test ui.test_shared_domain_catalog --settings=config.settings_test_local --keepdb`
- QA navigateur sur `127.0.0.1:8015`

## Résultat final

- Le catalogue charge sans erreur page.
- La démo `account.profile_card` charge sans 500.
- Aucun 404 résiduel n'apparaît sur le fallback d'avatar.
- Le flux reste utilisable dans le navigateur sans rechargement complet.

## Risque résiduel

- Le catalogue dépend encore du serveur de développement pour les données branchées.
- Les démos restent volontairement limitées aux composants déjà branchés au backend; ce n'est pas une couche de prévisualisation générique.
