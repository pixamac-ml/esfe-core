# Communication Migration Plan

## Objectif

Centraliser progressivement les flux de communication dans `communication/` sans casser les workflows déjà en production.

## Périmètre de la première étape

- nouvelle base de données unifiée pour événements, notifications et logs d'envoi
- bus d'événements central `CommunicationEventBus`
- provider email isolé `communication/providers/brevo.py`
- socle realtime dédié `ws/communication/notifications/`
- base de messagerie interne pour itération future

## Stratégie de transition

1. Laisser `core.Notification` et `community.Notification` fonctionner sans changement immédiat.
2. Introduire `communication` sur les nouveaux flux d'abord.
3. Ajouter ensuite des adaptateurs par domaine:
   - admissions
   - payments
   - community
   - dashboards staff
4. Migrer les interfaces de lecture vers `communication.selectors`.
5. Déprécier les modèles legacy seulement après double écriture stabilisée.

## Ordre recommandé

1. Admissions: remplacer les appels directs email par `CommunicationEventBus.emit(...)`.
2. Payments: remplacer les notifications post-commit directes par le bus.
3. Community: écrire en double vers l'ancien et le nouveau modèle, puis migrer la navbar et le centre de notifications.
4. Secrétariat et dashboard étudiant: brancher les widgets sur les sélecteurs `communication`.
5. Messagerie: brancher les premières conversations réelles sur les modèles `Conversation*`.

## Règles d'architecture

- aucun provider externe directement dans les apps métier
- tous les déclencheurs passent par le bus
- chaque canal reste séparé: `in_app`, `email_transactional`, `email_marketing`, `websocket`, `sms_future`
- l'envoi doit rester compatible `transaction.on_commit()`
- HTMX reste le mode principal pour les dashboards non critiques

## Intégration Brevo

- SMTP Brevo possible immédiatement derrière le provider
- API Brevo et templates dynamiques à brancher ensuite sans modifier les apps métier
- suivi provider, retries et logs à enrichir dans `CommunicationDelivery`
