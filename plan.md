# Plan - Cloture de la section Parametres enseignant

## Objectif

Finaliser la section **Parametres** du dashboard enseignant pour qu'elle soit exploitable, coherente avec le reste du portail, et prete a etre consideree comme terminee.

## Perimetre

- Dashboard enseignant uniquement.
- Section `Parametres`.
- Profil enseignant, preferences d'affichage, raccourcis de session et coherence UI.
- Pas de refonte globale du dashboard.
- Pas de modification des modules directeur, surveillant, etudiant ou informaticien sauf dependance directe.

## Etat cible

La section Parametres doit permettre a l'enseignant de :

- consulter clairement ses informations de profil;
- voir son annexe, statut, code employe et date de prise de service;
- acceder rapidement aux actions utiles de compte;
- changer les preferences locales utiles au dashboard;
- quitter proprement sa session;
- comprendre si une information manque sans erreur visuelle;
- utiliser la section sur desktop et mobile sans chevauchement.

## Livrables

1. **Bloc profil enseignant finalise**
   - Nom complet.
   - Code employe.
   - Statut d'emploi.
   - Annexe.
   - Date de prise de service.
   - Nombre de classes actives.
   - Nombre de matieres actives.
   - Messages sobres pour les donnees non renseignees.

2. **Bloc compte**
   - Lien vers le profil utilisateur existant.
   - Lien vers la modification du profil si la route existe.
   - Bouton de deconnexion conserve et bien visible.
   - Aucun lien mort.

3. **Bloc preferences**
   - Mode sombre clair/stable sur le dashboard enseignant.
   - Preference sauvegardee cote navigateur avec `localStorage`.
   - Retour automatique a la preference sauvegardee au chargement.
   - Libelles propres et sans texte technique.

4. **Bloc raccourcis**
   - Aller a l'accueil du dashboard.
   - Aller aux classes.
   - Aller aux supports.
   - Aller au cahier de texte.
   - Les raccourcis doivent changer de section sans rechargement inutile.

5. **Etat vide et donnees manquantes**
   - Si l'enseignant n'a pas d'annexe, afficher `Non rattache`.
   - Si le code employe manque, afficher `Non renseigne`.
   - Si la date de prise de service manque, afficher `Non renseignee`.
   - Aucun champ ne doit afficher `None`, `null`, ou une erreur Django.

6. **Responsive**
   - Mobile: les blocs doivent passer en une colonne.
   - Desktop: disposition claire en deux colonnes.
   - Les boutons ne doivent pas deborder.
   - Les textes longs doivent rester lisibles.

7. **Tests**
   - Ajouter ou completer un test de rendu de la section Parametres enseignant.
   - Verifier les valeurs profil principales.
   - Verifier les fallbacks de donnees manquantes.
   - Verifier que la route enseignant continue de rendre `Dashboard enseignant`.

## Ordre d'execution

1. Lire `templates/portal/teacher.html` autour de la section `teacher-settings-section`.
2. Lire le contexte fourni par `build_teacher_dashboard_context`.
3. Identifier les donnees deja disponibles et celles a ajouter dans le service.
4. Mettre a jour le service uniquement si une donnee manque vraiment.
5. Recomposer la section Parametres dans le template.
6. Ajouter la persistance du mode sombre dans le JS Alpine existant.
7. Ajouter les tests de regression.
8. Executer les tests cibles enseignant.
9. Executer `python manage.py check`.

## Criteres d'acceptation

- La section Parametres est visible et complete dans le dashboard enseignant.
- Aucun bouton de la section ne pointe vers une route inexistante.
- Les preferences d'affichage persistent apres rechargement.
- Les informations manquantes sont affichees proprement.
- Les tests enseignants passent.
- `python manage.py check` passe.

## Hors scope pour cette cloture

- Edition complete du profil RH.
- Changement de mot de passe.
- Notifications avancees.
- Parametres globaux de l'etablissement.
- Gestion des permissions.
- Refonte complete du dashboard enseignant.

## Fichiers probablement concernes

- `templates/portal/teacher.html`
- `portal/services/teacher_dashboard_service.py`
- `accounts/tests.py`

