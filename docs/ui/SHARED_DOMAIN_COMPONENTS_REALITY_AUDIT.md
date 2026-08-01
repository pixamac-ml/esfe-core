# Shared Domain Components Reality Audit

**Date :** 26 juillet 2026  
**Branche :** `refactor/ui-core-foundation`

## Objectif

Verifier que le catalogue `/ui/system/domains/` expose des composants qui existent vraiment dans le depot et qui s'appuient sur du code executable.

## Constat

- 17 composants metier partages sont exposes.
- 4 familles sont couvertes: account, notifications, student, shop.
- Le catalogue ouvre un drawer de detail sans rechargement complet.
- Les composants account utilisent le compte courant et les donnees de profil reelles.
- Les composants notifications branchent le compteur et les selecteurs du centre de notifications.
- Les composants student s'appuient sur `Student` et sur la resolution de profil etudiant.
- Les composants shop s'appuient sur `ShopProduct` et sur la resolution d'annexe.

## Verification backend

- Les fragments de detail et de demo sont servis par des vues Django.
- Les routes du catalogue sont protegees hors `DEBUG`.
- Le fallback d'avatar ne renvoie plus un fichier statique absent.
- La demo `account.profile_card` ne produit plus de 500.

## Verification navigateur

- Ouverture du catalogue: OK
- Ouverture du drawer de detail: OK
- Chargement de la demo `account.profile_card`: OK
- Erreurs page: 0
- Erreurs console: 0
- Reponses HTTP >= 400 durant la passe finale: 0

## Conclusion

Le catalogue est branche sur des vues et des composants reels. Il peut servir de reference de travail.
