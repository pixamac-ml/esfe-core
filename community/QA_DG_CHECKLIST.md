# QA Community - Validation DG

## Objectif
Valider que le module `community` est stable, cohérent et prêt pour démonstration DG (UX + notifications + emails).

## Pré-vol
```powershell
python -u "C:\Users\WORK\PycharmProjects\esfe\manage.py" check
python -u "C:\Users\WORK\PycharmProjects\esfe\manage.py" migrate
python -u "C:\Users\WORK\PycharmProjects\esfe\manage.py" runserver
```

## Cas de test obligatoires
- [ ] Créer un sujet (`community/create_topic.html`) -> apparition immédiate en listing.
- [ ] Répondre à un sujet (`community/topic_detail.html`) -> rendu HTMX sans reload complet.
- [ ] Voter une réponse -> score mis à jour sans erreur.
- [ ] Accepter une réponse -> badge solution visible et cohérent.
- [ ] Signaler un contenu -> formulaire `community/report.html` fonctionnel.
- [ ] Vérifier `community/notifications.html` -> filtres et pagination opérationnels.
- [ ] Marquer une notification comme lue -> état + compteur non lu synchronisés.
- [ ] Supprimer une notification -> carte retirée + compteur cohérent.
- [ ] Cliquer "Tout marquer lu" -> compteur à 0 + badge navbar mis à jour.
- [ ] Vérifier websocket notif (badge navbar se met à jour à l'arrivée d'une nouvelle notif).

## Tests emails
- [ ] Déclencher une notification avec envoi email (`send_email=True`).
- [ ] Vérifier réception email (objet, contenu, lien absolu).
- [ ] Vérifier que les erreurs SMTP remontent dans les logs (pas de fail silencieux).

## Go / No-Go
- **GO**: tous les cas ci-dessus validés, aucun 500 backend, UX fluide.
- **NO-GO**: au moins un blocage sur notifications temps réel ou envoi email.

## Notes de capture DG
- Capture 1: Listing discussions + recherche + tri.
- Capture 2: Détail sujet avec réponse HTMX et vote.
- Capture 3: Notifications page + badge navbar avant/après action.
- Capture 4: Profil public avec onglets activité/réponses/sujets/badges.

