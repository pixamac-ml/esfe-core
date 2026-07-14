# Régularisation des comptes avant Policy V2

Ne jamais déduire une position officielle d'un groupe, de `role`, de `is_staff`
ou d'une activité historique. Chaque compte signalé doit être confirmé par une
personne habilitée.

Pour chaque `user_id` ambigu :

1. confirmer s'il s'agit d'un compte PUBLIC ou SYSTEM ;
2. pour SYSTEM, choisir exactement une position du registre ;
3. confirmer l'annexe pour toute position BRANCH ;
4. enregistrer la position et l'annexe dans le profil historique pendant la
   période de double écriture ;
5. attribuer ensuite les groupes de permissions nécessaires, sans utiliser ces
   groupes pour changer le dashboard ;
6. relancer `python manage.py audit_access_state --dry-run --json`.

Pour rendre un compte PUBLIC, vider explicitement `Profile.position` et
`Profile.branch`. Le signal supprime alors sa copie institutionnelle sans toucher
à son profil communautaire.

Pour suspendre ou modifier une position/annexe, utiliser les écrans administratifs
existants : les sessions précédentes seront automatiquement révoquées.

La bascule est autorisée uniquement lorsque l'audit ne contient plus de compte
ambigu ou invalide. Activer ensuite progressivement :

1. `AUTH_ACCESS_CONTEXT_V2_ENABLED=True` ;
2. `AUTH_POLICY_V2_SHADOW_ENABLED=True` et observer les divergences ;
3. `AUTH_PORTAL_ROUTING_V2_ENABLED=True` ;
4. `AUTH_POLICY_V2_ENABLED=True`.

Rollback immédiat : remettre les quatre flags à `False`. Les données historiques
de `Profile`, les services métier et les anciennes routes restent conservés.
