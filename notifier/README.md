# Architecture des notifications

Le systeme officiel est separe en deux applications :

- `notifier` est le moteur. Il cree les evenements, messages et tentatives de
  livraison, applique la politique des canaux et distribue email/in-app/WebSocket.
- `notification_center` est l'interface. Il liste uniquement les messages du
  destinataire connecte et gere l'etat lu/non lu des messages `in_app`.

Les applications metier appellent `NotificationBus`; elles ne doivent importer
ni les vues/selecteurs de `notification_center`, ni l'ancien paquet
`communication`.

## API publique

```python
from notifier.services import NotificationBus

NotificationBus.notify(
    recipient=user,
    event_type="payment_validated",
    title="Paiement valide",
    body="Votre paiement a ete valide.",
    source_app="payments",
    metadata={"payment_id": payment.pk, "branch_id": payment.branch_id},
)
```

`notify()` applique automatiquement la politique declaree dans
`notifier.services.policy` quand `channels` n'est pas fourni. Passer `channels`
explicitement constitue une surcharge volontaire du workflow appelant.

Pour un email transactionnel externe, utiliser `NotificationBus.send_email()`.
Ne pas appeler directement le provider Brevo.

## Regles de donnees

- Un `NotificationEvent` trace le fait metier.
- Un `NotificationMessage` represente un destinataire et un canal.
- Un `DeliveryAttempt` trace une tentative de distribution.
- Seuls les messages `in_app` entrent dans le compteur non lu.
- Toute resolution d'audience doit respecter l'annexe; un envoi multi-annexes
  doit etre explicite et autorise par le workflow metier.

## Reprise du legacy

`core.Notification` est copie puis supprime par la migration `core.0010`.
Les anciennes tables `communication_*` ne sont pas exploitees par l'application.
Avant de les supprimer en base de production :

```powershell
python manage.py migrate
python manage.py migrate_communications --dry-run
python manage.py migrate_communications
```

La commande est idempotente. Verifier les volumes et les erreurs de livraison
dans l'admin `notifier` avant toute suppression manuelle des tables legacy.
