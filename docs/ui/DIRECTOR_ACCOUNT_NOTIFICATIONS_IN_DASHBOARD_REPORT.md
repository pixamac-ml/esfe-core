# Rapport - Profil et notifications in-dashboard du Directeur des etudes

Date : 26 juillet 2026  
Branche : `refactor/ui-core-foundation`

## Probleme initial

Le Directeur des etudes avait encore des sorties de shell sur les actions compte
et notifications :

- profil ;
- edition du profil ;
- securite ;
- mot de passe ;
- preferences ;
- cloche de notifications ;
- centre complet de notifications.

Ces actions quittaient le dashboard et rompaient le shell persistant alors que
le dashboard Directeur disposait deja de composants partages et de cibles HTMX
adaptables.

## Liens externes identifies

- `accounts:profile`
- `accounts:edit_profile`
- `accounts:password_change`
- `accounts:edit_preferences`
- `notification_center:notifications_widget`
- `notification_center:notifications_partial`
- `notification_center:notifications`

## Architecture mise en place

- `account.profile_dropdown`
- `account.profile_view`
- `account.profile_editor`
- `account.security_settings`
- `account.preference_settings`
- `notifications.bell`
- `notifications.list`
- `notifications.item`
- `notifications.drawer`

Cibles internes conservees :

- `#director-workspace`
- `#director-drawer-content`
- `#director-modal-content`

Cibles ajoutees ou exploitees :

- `#director-notification-detail`
- `#notification-dropdown-content`

Le shell reste persistant. Les changements de contenu passent par HTMX et les
overlays UI Core.

## Profil

Le menu profil du Directeur des etudes charge maintenant :

- la vue profil ;
- l'edition du profil ;
- la securite ;
- les preferences ;
- la deconnexion via POST.

Le profil est prepare cote vue dans `portal/views/views.py` puis rendu par
`ui.templates.account.profile_view` et `ui.templates.account.profile_dropdown`.

## Edition

L'edition du profil est rouverte dans le drawer sans quitter le dashboard.
`SystemProfileForm` est reutilise. Le POST HTMX renvoie le profil actualise avec
`HX-Trigger` pour rafraichir la topbar.

## Avatar

L'avatar est integre au formulaire de profil systeme avec support d'upload
multipart. Le bouton de selection declenche le fichier via `x-ref`.

## Securite

Le changement de mot de passe utilise le backend Django existant
`PasswordChangeForm`. La session reste coherente apres validation.

## Preferences

`UserPreferenceForm` est reutilise sans duplication. Les preferences sont
rendues dans le drawer et sauvees en HTMX.

## Notifications

La cloche et le centre complet restent dans le dashboard :

- apercu rapide dans la topbar ;
- liste interne dans le workspace ;
- detail de notification dans `#director-notification-detail` ;
- marquage comme lu ;
- action "Tout marquer comme lu" ;
- lien vers la ressource metier lorsque disponible et autorisee.

Le compteur est alimente par la source de verite existante et remis a jour sans
rechargement complet.

## Temps reel

La topbar se refraichit sur les evenements :

- `account:profile-updated`
- `notificationsChanged`
- `notification.read`

## HTMX

Flux principaux :

- `director_account_panel`
- `director_notifications_preview`
- `director_notifications_workspace`
- `director_notification_detail`
- `director_mark_all_notifications_read`

Le shell n'est pas remplace. Seules les zones internes sont ciblees.

## Topbar

`ui_core.app_topbar` est conserve comme composant commun. Le dashboard Directeur
injecte ses fragments via `templates/portal/staff/director/partials/topbar_fragments.html`.

## Permissions

Les vues restent protegees par les verrous de position et par le scope
d'annexe. Aucune permission n'est geree dans les composants UI.

## Tests

Commandes lancees dans cette session :

- `python manage.py check` - PASS deja confirme
- `python manage.py makemigrations --check --dry-run` - PASS deja confirme
- `python manage.py test portal.test_director_dashboard_phase2 --settings=config.settings_test_local --keepdb` - PASS
- `python manage.py test ui.test_ui_core --settings=config.settings_test_local --keepdb` - PASS
- `python manage.py test accounts notification_center notifier --settings=config.settings_test_local --keepdb` - FAIL avec erreurs/failures preexistants
- `npm run build:css` - PASS

Les echec/erreurs restants dans `accounts` et `notification_center` ne concernent
pas directement le flux in-dashboard du Directeur des etudes et semblent
provenir du socle de tests existant.

## QA navigateur

Recette headless Playwright executee sur le dashboard reel du Directeur des
etudes avec captures dans `_audit/director_account_notifications/`.

Parcours valide :

- connexion ;
- profil ;
- edition ;
- preferences ;
- notifications ;
- detail notification ;
- marquage lu ;
- tout marquer comme lu ;
- securite ;
- mot de passe ;
- aucune sortie de dashboard sur ces actions.

## Captures

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

## Risques restants

- La suite de tests globale contient encore des echecs preexistants.
- Le comportement temps reel WebSocket a ete valide indirectement par les
  evenements et le refresh topbar, pas par une charge de production.
- Les anciennes routes restent disponibles en compatibilite.

## Etat Git

- Branche : `refactor/ui-core-foundation`
- Worktree : sale avant et apres la mission
- Aucun commit
- Aucun push

## Verdict

**PROFIL ET NOTIFICATIONS IN-DASHBOARD VALIDÉS AVEC RÉSERVES SUR LES TESTS GLOBAUX PRÉEXISTANTS**

La QA navigateur du dashboard réel du Directeur des études est passée avec
succès. Tous les parcours profil, sécurité, préférences et notifications
restent intégralement dans le dashboard sans sortie de shell. Les tests
ciblés Directeur (`portal.test_director_dashboard_phase2`) et UI Core
(`ui.test_ui_core`) sont verts.

Les erreurs restantes dans `accounts`, `notification_center` et `notifier`
sont préexistantes et ne bloquent pas la validation fonctionnelle de cette
mission. Elles relèvent du socle de tests global et non du périmètre
profil/notifications in-dashboard validé ici.

