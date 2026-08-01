# Recette navigateur - Profil et notifications du Directeur des etudes

Date : 26 juillet 2026

## Cadre

Execution faite contre le dashboard reel du Directeur des etudes, avec un
serveur local temporaire sur `http://127.0.0.1:8020/` et le jeu de donnees
`config.settings_test_local`.

Compte de test utilise :

- utilisateur : `directeur.etudes`
- mot de passe initial : `pass1234`

## Parcours verifies

1. Connexion au dashboard.
2. Ouverture du menu profil.
3. Affichage de la vue profil dans le drawer.
4. Passage a l'edition du profil dans le drawer.
5. Sauvegarde du profil et rafraichissement de la topbar.
6. Ouverture des preferences dans le drawer.
7. Sauvegarde des preferences sans sortie du dashboard.
8. Ouverture de la cloche et affichage de l'aperçu.
9. Ouverture du centre interne de notifications dans le workspace.
10. Ouverture d'une notification non lue dans le panneau de detail.
11. Decrementation du compteur apres lecture.
12. "Tout marquer comme lu" sans reload complet.
13. Ouverture de la securite depuis la vue profil.
14. Changement de mot de passe sans sortie du dashboard.

## Captures

Les captures sont stockees dans :

`_audit/director_account_notifications/`

Fichiers produits :

- `01-dashboard.png`
- `02-profile-view.png`
- `03-profile-edit.png`
- `04-profile-saved.png`
- `05-preferences.png`
- `06-notifications-preview.png`
- `07-notifications-workspace.png`
- `08-notification-detail.png`
- `09-notifications-marked-read.png`
- `10-security.png`
- `11-security-saved.png`

## Resultats observes

- Le profil reste dans le drawer du dashboard.
- L'edition du profil reste dans le drawer du dashboard.
- Les preferences restent dans le drawer du dashboard.
- Le centre de notifications reste dans le workspace.
- Le detail d'une notification s'ouvre dans le panneau interne du workspace.
- Le compteur de notifications se decremente apres lecture.
- L'action "Tout marquer comme lu" met le compteur a zero.
- Le changement de mot de passe reste dans le dashboard.
- Aucun reload complet non voulu n'a ete observe pendant le parcours.

## Limites notees

- La recette a ete faite en mode headless avec Playwright.
- La recette vise le dashboard reel, pas `/ui/system/domains/`.
- Les tests de niveau projet restent distincts de cette QA navigateur.

