# Audit prealable - Profil et notifications du Directeur des etudes

Date : 26 juillet 2026

## Constat

Avant l'integration in-dashboard, la topbar du Directeur des etudes exposait
encore des sorties de shell sur les actions compte et notifications.

Le probleme n'etait pas l'absence de backend. Les vues, formulaires et
selecteurs existaient deja. Le point de rupture etait le chemin de rendu :
les actions quittaient le dashboard alors qu'un shell persistant et des
composants partages etaient disponibles.

## Carte des sorties existantes

| Libelle | Element source | Template | URL actuelle | Comportement actuel | Backend existant | Composant partage | Nouvelle cible | Methode | Permission | Risque |
|---|---|---|---|---|---|---|---|---|---|---|
| Mon profil | lien ou bouton de profil | `accounts/templates/accounts/profile_detail.html`, `accounts/templates/accounts/partials/profile_settings.html` | `accounts:profile` | page complete du portail compte | `accounts.views.profile_detail` | `account.profile_view` | drawer interne | `hx-get` | utilisateur authentifie | moyen |
| Modifier le profil | lien du profil | `accounts/templates/accounts/edit_profile.html`, `accounts/templates/accounts/edit_profile_system.html` | `accounts:edit_profile` | page complete d'edition | `accounts.views.edit_profile`, `accounts.forms.ProfileForm`, `accounts.forms.SystemProfileForm` | `account.profile_editor` | drawer interne | `hx-get` / `hx-post` | utilisateur authentifie | eleve |
| Securite | lien de menu ou page separee | `accounts/templates/accounts/profile_settings.html`, `accounts/templates/accounts/dashboard/manager_dashboard.html` | `accounts:password_change` | page complete | `PortalPasswordChangeView`, `PasswordChangeForm` | `account.security_settings` | drawer interne | `hx-get` / `hx-post` | utilisateur authentifie | eleve |
| Changer le mot de passe | action de securite | `accounts/templates/accounts/profile_settings.html` | `accounts:password_change` | page complete | `PortalPasswordChangeView` | `account.security_settings` | drawer interne | `hx-post` | utilisateur authentifie | eleve |
| Preferences | lien de menu | `accounts/templates/accounts/profile_preferences.html`, `accounts/templates/accounts/partials/profile_settings.html` | `accounts:edit_preferences` | page complete de preferences | `accounts.views.edit_preferences`, `accounts.forms.UserPreferenceForm`, `accounts.models.UserPreference` | `account.preference_settings` | drawer interne | `hx-get` / `hx-post` | utilisateur authentifie | moyen |
| Notifications | cloche topbar | `notification_center/templates/notification_center/partials/widget.html`, `notification_center/templates/notification_center/partials/dropdown.html` | `notification_center:notifications_widget`, `notification_center:notifications_partial` | apercu hors dashboard ou redirection indirecte | `notification_center.views.notifications_widget`, `notification_center.views.notifications_partial` | `notifications.bell` | dropdown + workspace interne | `hx-get` | utilisateur authentifie | moyen |
| Centre de notifications | bouton "Tout voir" | `notification_center/templates/notification_center/partials/center.html` | `notification_center:notifications` | page complete du centre de notifications | `notification_center.views.notifications`, `notification_center.views.mark_all_notifications_read` | `notifications.list`, `notifications.item`, `notifications.drawer` | workspace interne du DE | `hx-get` / `hx-post` | utilisateur authentifie | eleve |

## Remarques techniques

- Les routes historiques restent disponibles comme compatibilite.
- Le probleme se situe dans le chemin de rendu, pas dans l'absence de backend.
- Les composants partages `account.*` et `notifications.*` fournissent deja la
  base de l'integration interne.
- La correction doit rester sans ORM dans les composants, avec donnees preparees
  par la vue ou un service de presentation.

## Cibles attendues

- `#director-drawer-content` pour profil, securite, preferences et detail de
  notification.
- `#director-workspace` pour le centre complet de notifications.
- `#director-notification-detail` pour le panneau de detail du centre interne.
- `#notification-dropdown-content` pour l'aperçu rapide.

