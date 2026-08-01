# Cartographie HTMX du dashboard Directeur des Études

Date : 26 juillet 2026

## Contrat commun

Tous les endpoints ci-dessous sont protégés par
`_position_required(DIRECTOR_DASHBOARD_POSITIONS)`. Chaque vue métier résout ensuite
le scope avec `require_director_branch_scope()` ou délègue à un service qui vérifie
l'annexe. Un Directeur sans annexe reçoit `403`; un objet d'une autre annexe n'est
jamais accepté.

Le shell, la sidebar et la topbar ne sont jamais remplacés. Les cibles stables sont :

- `#director-workspace` : section métier ;
- `#director-drawer-content` : détail latéral ;
- `#director-modal-content` : formulaire ou étape sensible ;
- grilles `#de-grid-*` : pagination locale en `outerHTML`.

`static/src/js/portal/director_dashboard.js` gère l'indicateur global, l'état de
navigation, l'ouverture des overlays UI Core et l'adaptation des confirmations
`hx-confirm`. `static/src/js/ui_core/index.js` gère CSRF, erreurs, toasts, Lucide et
réinitialisation idempotente après swap.

## Navigation et lecture

| Nom d'URL | Méthode | Cible / swap | Données et résultat |
|---|---|---|---|
| `portal_dashboard` | GET | document complet initial uniquement | Dashboard actif et AppShell |
| `portal_director` | GET | redirection contrôlée ; rendu global explicite pour superuser/DG/DGA | Compatibilité historique |
| `director_workspace` | GET | `#director-workspace`, `innerHTML` | Accueil ou section autorisée |
| `director_drawer` | GET | `#director-drawer-content`, `innerHTML` | Classe, programme, planning, étudiant ou résultat |
| `director_teacher_profile` | GET | drawer, `innerHTML` | Profil enseignant limité à l'annexe |
| `director_teacher_documents_modal` | GET | modal, `innerHTML` | Dossier documentaire enseignant |
| `director_teacher_contract_download` | GET | téléchargement | Contrat PDF |
| `director_correspondance_pdf` | GET | téléchargement | Correspondance PDF |
| `director_export_report_xlsx` | GET | téléchargement | Rapport académique de l'annexe |

La navigation sidebar, les actions rapides et les KPI utilisent `hx-push-url` avec
une URL complète partageable et chargent le fragment via `director_workspace`.

## Compte et notifications du Directeur des Études

| Nom d'URL | Méthode | Cible / swap | Succès / erreur |
|---|---|---|---|
| `director_topbar_fragments` | GET | `#director-topbar-fragments`, `outerHTML` | Recompose le profil et la cloche sans remplacer le shell |
| `director_account_panel` | GET, POST | `#director-drawer-content`, `innerHTML` | Vue profil, édition, sécurité, préférences |
| `director_notifications_preview` | GET | `#notification-dropdown-content`, `innerHTML` | Aperçu rapide dans la topbar |
| `director_notifications_workspace` | GET | `#director-workspace`, `innerHTML` | Centre complet interne avec detail panel |
| `director_notification_detail` | GET | `#director-notification-detail` ou `#director-drawer-content`, `innerHTML` | Détail d'une notification et event `notification.read` |
| `director_mark_all_notifications_read` | POST | `#director-workspace`, `innerHTML` | Marquage global comme lu + refresh topbar |

Parcours cible :

```text
profile dropdown / bell
-> HTMX GET
-> drawer ou workspace interne
-> pas de remplacement du document complet
-> HX-Trigger
-> refresh topbar
```

## Enseignants, documents et transferts

| Nom d'URL | Méthode | Cible | Succès / erreur |
|---|---|---|---|
| `director_teacher_create` | GET, POST | modal puis workspace | Formulaire, création et feedback |
| `director_teacher_assign` | GET, POST | modal puis workspace | Affectation limitée aux classes/EC de l'annexe |
| `director_teacher_document_upload` | GET, POST | modal puis workspace | Upload multipart et feedback |
| `director_teacher_document_review` | POST | workspace | Validation/refus d'une pièce |
| `director_transfer_create` | GET, POST | modal puis workspace | Demande de transfert |
| `director_transfer_review` | GET, POST | modal puis workspace | Décision autorisée |

Le filtre enseignants utilise `ui_core.filter_bar` :

```text
input (debounce 350 ms) ou submit
-> GET director_workspace?section=enseignants
-> hx-sync="#director-workspace:replace"
-> innerHTML #director-workspace
```

Le reset exécute le même flux sans `teacher_q`.

## Programmes et correspondances

| Nom d'URL | Méthode | Cible | Actions |
|---|---|---|---|
| `director_programme_action` | POST | drawer ou workspace | Semestre, UE, EC, suppression contrôlée |
| `director_correspondance_create` | POST | workspace | Brouillon administratif |
| `director_correspondance_publish` | POST | workspace | Publication |

Les suppressions ou changements irréversibles portent `hx-confirm`; l'événement
`htmx:confirm` est intercepté par `ui_core.confirm_dialog` avant `issueRequest(true)`.

## Résultats, bulletins et évaluations

| Nom d'URL | Méthode | Cible | Actions |
|---|---|---|---|
| `director_results_action` | POST | workspace ou modal | Validation, rejet, demande de publication |
| `director_results_confirm_otp` | POST | workspace | Confirmation OTP existante |
| `director_bulletin_action` | POST | workspace | Génération des bulletins |
| `director_exam_session_action` | POST | workspace | Création, publication, annulation de session |
| `director_evaluation_action` | POST | workspace | Création, publication, annulation d'évaluation |

Les règles de notes, moyennes, publication, bulletins et OTP restent dans les
services existants. UI Core ne reçoit que le HTML final et les états de feedback.

## Calendrier et planning

| Nom d'URL | Méthode | Cible | Actions |
|---|---|---|---|
| `director_calendar_action` | POST | workspace | Calendrier, entrées, validation, publication, archive |
| `director_planner_hub` | GET | workspace | Point d'entrée planning |
| `director_planner_view_workspace` | GET | workspace | Vue de planning |
| `director_planner_workspace` | GET | workspace | Programmation |
| `director_weekly_slots_workspace` | GET | workspace ou drawer | Créneaux hebdomadaires |
| `director_weekly_slot_save` | POST | workspace | Création/mise à jour/désactivation |
| `director_week_materialize` | POST | workspace | Matérialisation semaine |
| `director_month_materialize` | POST | workspace | Matérialisation mois |
| `director_create_schedule_event` | POST | workspace | Événement de planning |

Les grilles temporelles restent des composants académiques spécialisés.

## Chargement, erreurs et focus

- `htmx:beforeRequest` place le workspace en `aria-busy="true"` et affiche
  `#director-loading`.
- Les contenus modal/drawer ouvrent l'overlay instantanément avant la réponse.
- `htmx:afterRequest` retire l'état busy.
- `htmx:afterSwap` réinitialise Lucide, synchronise l'item actif et place le focus
  sur le workspace.
- `htmx:responseError` produit un toast danger générique.
- Les réponses métier conservent leurs messages locaux et `HX-Trigger`.
- Escape, focus trap et retour du focus relèvent du contrôleur `uiOverlay`.

## Événements

| Événement | Producteur | Consommateur | Effet |
|---|---|---|---|
| `ui-overlay-open` | adaptateur Directeur | modal/drawer/confirm UI Core | ouverture et focus |
| `ui-overlay-close` | adaptateur Directeur | modal/drawer/confirm UI Core | fermeture et restitution |
| `ui:toast` | réponse ou script générique | `window.ESFEUI` | feedback live |
| `htmx:confirm` | HTMX | adaptateur Directeur | dialogue UI Core |
| `htmx:afterSwap` | HTMX | UI Core + adaptateur | réinitialisation idempotente |

## Flux non HTMX assumés

Les téléchargements PDF/XLSX et la déconnexion sont des navigations ou
téléchargements explicites. Ils ne constituent pas des interactions de workspace
et ne remplacent pas le shell pendant une action métier courante.

Le centre complet de notifications n'est plus une navigation externe. Il est
désormais chargé dans `#director-workspace` via `director_notifications_workspace`
en HTMX, comme le reste du workspace.
