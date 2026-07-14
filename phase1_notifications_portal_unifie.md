# Phase 1 — Notifications Portal unifiées

Date : 13 juillet 2026  
Statut : **PASS sur contrôles automatisés**

## Résultat

Le moteur `notifier` reste l'unique moteur officiel. Un seul composant Portal,
chargé depuis `notification_center/partials/portal_component.html`, est monté par
le socle `templates/base.html` pour les comptes SYSTEM. Il se place dans la
topbar lorsqu'un emplacement `data-portal-notification-slot` existe et utilise
un bouton flottant responsive dans les autres surfaces.

Le composant fournit : cloche, compteur, aperçu, centre complet, lecture,
marquage global, archivage/restauration, filtres, pagination, liens d'action
internes validés, états vides, erreur de chargement et rafraîchissement
WebSocket/HTMX/polling. Les messages internes étudiants restent distincts des
notifications automatiques.

Le centre SYSTEM est rendu dans le shell Portal institutionnel. Le centre
PUBLIC conserve son rendu séparé et ne reçoit pas le composant SYSTEM.

## Couverture des dashboards

| Position | Composant commun | Centre Portal | Temps réel | Isolation destinataire/annexe | Résultat |
|---|---:|---:|---:|---:|---|
| STUDENT | Oui | Oui | Oui | Oui | PASS |
| TEACHER | Oui | Oui | Oui | Oui | PASS |
| ANNEX_MANAGER | Oui | Oui | Oui | Oui | PASS |
| SECRETARY | Oui | Oui | Oui | Oui | PASS |
| ADMISSIONS_OFFICER (`admissions`) | Oui | Oui | Oui | Oui | PASS |
| ACADEMIC_SUPERVISOR | Oui | Oui | Oui | Oui | PASS |
| DIRECTOR_OF_STUDIES | Oui | Oui | Oui | Oui | PASS |
| IT_SUPPORT | Oui | Oui | Oui | Oui | PASS |
| MARKETING_MANAGER | Oui | Oui | Oui | Oui | PASS |
| EXECUTIVE_DIRECTOR | Oui | Oui | Oui | Oui | PASS |
| DEPUTY_EXECUTIVE_DIRECTOR | Oui | Oui | Oui | Oui | PASS |
| SUPER_ADMIN | Oui | Oui | Oui | Oui | PASS |
| PAYMENT_AGENT transitoire | Oui | Oui | Oui | Oui | PASS |

Les préférences centralisées ne sont volontairement pas simulées dans cette
phase : leur modèle et leurs règles obligatoires/optionnelles relèvent de la
PHASE 3 prévue par la mission.

## Migration

- `notifier.0002_notificationmessage_archived_at`
  - ajoute `archived_at`, distinct des statuts de livraison ;
  - ajoute l'index destinataire/canal/archivage/date ;
  - migration appliquée sur la base locale et sur la base de test.

## Tests et vérifications

- `python manage.py check` : PASS ;
- `python manage.py makemigrations notifier --check --dry-run` : PASS ;
- `notification_center` : 18/18 PASS ;
- `notifier notification_center` : 31/31 PASS ;
- `ui` : 29/29 PASS ;
- authentification/session/WebSocket ciblés : 66/66 PASS ;
- `npm run build:css` : PASS ;
- serveur local `/notifications/` sans session : HTTP 302 vers la connexion,
  attendu.

## Fichiers structurants

- moteur/façade : `notifier/models/message.py`,
  `notifier/services/notifications.py`, `notifier/services/bus.py` ;
- centre : `notification_center/selectors.py`, `views.py`, `urls.py`,
  `presentation.py` ;
- interface commune :
  `notification_center/templates/notification_center/partials/portal_component.html` ;
- centre Portal : `index_system.html` et `partials/center.html` ;
- intégration globale : `templates/base.html` et les emplacements de topbar ;
- tests contractuels Phase 1 :
  `notification_center/tests/test_portal_phase1.py`.

## Risques résiduels

- la recette visuelle multi-navigateurs et mobile reste prévue en PHASE 7 ;
- les préférences par catégorie/canal seront ajoutées en PHASE 3 ;
- le registre fermé des événements et l'audit complet des producteurs restent
  la prochaine étape (PHASE 2) ;
- les compteurs sont encore recalculés périodiquement ; leur cache et leur
  optimisation sont prévus en PHASE 4.

## Rollback

Le rollback applicatif peut retirer les emplacements et le composant commun en
laissant la colonne nullable `archived_at`, sans perte de données. Un retour de
schéma vers `notifier.0001` ne doit être fait qu'avant toute utilisation réelle
de l'archivage ou après export, car il supprimerait l'historique d'archivage.

## Prochaine étape

PHASE 2 : registre officiel des événements, inventaire des producteurs,
événements métier manquants et tests contractuels
`ÉVÉNEMENT -> DESTINATAIRES -> CANAUX -> INTERFACE`.
