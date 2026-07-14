# Rapport de recette visuelle — sessions SYSTEM

Date : 13 juillet 2026  
Statut final : **PASS**

## Environnement de recette

- Chromium piloté avec Playwright, viewport 1440 × 900.
- `SYSTEM_SESSION_MANUAL_TEST_MODE=True` uniquement dans les processus QA locaux.
- Site complet servi avec `config.settings_session_qa`, base SQLite temporaire et couche Channels en mémoire.
- Comptes temporaires isolés : étudiant, enseignant, gestionnaire d'annexe, superviseur académique, super administrateur, secrétaire active et compte administratif révoqué.
- Passage principal : 358,1 secondes.
- Complément ciblé : formulaire non enregistré, bouton Retour et reconnexion WebSocket refusée.
- Serveur QA arrêté, bases temporaires supprimées et comptes/candidatures QA nettoyés après la recette.

## Matrice demandée

| Compte / position | Modal | Compte à rebours | Prolongation | Multi-onglets | HTMX / AJAX | WebSocket | Redirection | Audit | Résultat |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Étudiant / `student` | PASS | PASS | PASS | N/A¹ | PASS | PASS | PASS | PASS | **PASS** |
| Enseignant / `teacher` | PASS | PASS | PASS | N/A¹ | PASS | PASS | PASS | PASS | **PASS** |
| Gestionnaire / `annex_manager` | PASS | PASS | PASS | PASS (3 onglets) | PASS | PASS | PASS | PASS | **PASS** |
| Administratif / `academic_supervisor` | PASS | PASS | PASS | N/A¹ | PASS | PASS | PASS | PASS | **PASS** |
| Super administrateur / `super_admin` | PASS | PASS | PASS | N/A¹ | PASS | PASS | PASS | PASS | **PASS** |

¹ La synchronisation multi-onglets est assurée par le gestionnaire commun et a été exercée en profondeur sur le compte gestionnaire : prolongation propagée puis expiration des trois onglets.

## Résultats par scénario

1. **Expiration normale — PASS** : dashboard officiel atteint pour les cinq profils, modal et décompte visibles, expiration sans interaction, redirection connexion et message explicite d'inactivité. Après le bouton Retour, une ancienne page ne peut plus appeler une ressource protégée : réponse JSON 401.
2. **Prolongation — PASS** : « Continuer ma session » ferme le modal et le serveur retourne de nouveau au moins 165 secondes sur les 180 secondes du mode court. Une simple dissimulation visuelle, sans appel serveur, n'empêche pas l'expiration suivante.
3. **Activité réelle — PASS** : la session témoin active reste ouverte jusqu'à la fin ; 7 appels d'activité seulement pendant 358 secondes, donc limitation effective. Navigation Portal, édition de profil et formulaire ont été exercés.
4. **Polling passif — PASS** : les statuts, widgets et heartbeats n'ont prolongé aucune des cinq sessions inactives.
5. **Plusieurs onglets — PASS** : trois onglets gestionnaire synchronisés à la prolongation, puis tous redirigés à l'expiration ; aucune action protégée ne reste possible.
6. **Formulaire non enregistré — PASS** : avertissement visible, champ conservé après prolongation, aucun POST automatique et contenu du champ absent de `localStorage`.
7. **HTMX / AJAX — PASS** : HTMX reçoit 401 + `HX-Redirect` sans HTML de connexion injecté ; AJAX reçoit un JSON 401 `session_expired`.
8. **WebSocket — PASS** : socket ouverte pendant la session puis fermée à l'expiration. La reconnexion après expiration est refusée avant acceptation (`opened=false`, Chromium expose 1006 ; le serveur journalise `WebSocket REJECT`). Les tests Channels valident aussi les codes applicatifs 4401/4403.
9. **Profil SYSTEM — PASS** : les cinq profils restent dans le shell Portal, aucun profil public n'apparaît, les champs autorisés sont modifiables, le retour dashboard et la session restent corrects.
10. **Audit — PASS** : événements observés `LOGIN_SUCCESS`, `LOGOUT_VOLUNTARY`, `IDLE_TIMEOUT`, `ABSOLUTE_TIMEOUT` et `ADMIN_REVOKED`, ainsi que les changements de position/annexe des fixtures. Les métadonnées sont exemptes de mot de passe, PIN, cookie, clé de session brute, token complet et contenu sensible de formulaire.

## Défaut déterministe corrigé

La redirection arrivait bien sur la connexion, mais le template ne rendait aucun message expliquant l'expiration. Correction appliquée :

- liste fermée des motifs et messages dans `accounts/auth_views.py` ;
- alerte visible et accessible dans `templates/registration/login.html` ;
- test anti-réflexion d'un motif inconnu dans `accounts/test_authentication_security.py`.

La capture finale confirme le texte : « Votre session a expiré après une période d'inactivité. Reconnectez-vous pour continuer. »

## Validation finale

- `python manage.py check` : PASS, 0 erreur.
- `python manage.py makemigrations accounts --check --dry-run` : PASS, aucune modification.
- `python manage.py test --settings=config.settings_test_local --keepdb --noinput accounts.test_authentication_security notifier.test_realtime_security` : **66/66 PASS**.
- `npm run build:css` : PASS.
- Rapport machine principal : `test_artifacts/session_visual_qa/report.json` — `passed=true`.
- Rapport complémentaire : `test_artifacts/session_visual_qa/edge_report.json` — `passed=true`.

## Retour aux valeurs normales

- `SYSTEM_SESSION_MANUAL_TEST_MODE=False` chargé ; aucune valeur correspondante n'est présente dans `.env`.
- Étudiant / enseignant : 1800 s (30 min).
- Secrétariat, admissions, superviseur académique, direction des études, marketing : 900 s (15 min).
- Gestionnaire, IT, direction générale, super administration, paiement, finance : 600 s (10 min).
- Avertissement : 120 s ; limite absolue : 43200 s (12 h) ; limitation d'activité : 30 s.
- Aucun serveur QA n'écoute sur le port 8010 et aucune base QA temporaire ne subsiste.

## Preuves visuelles

- `test_artifacts/session_visual_qa/*_warning.png` : alertes des cinq profils.
- `test_artifacts/session_visual_qa/*_expired_login.png` : redirections et message d'expiration.
- `test_artifacts/session_visual_qa/student_unsaved_warning.png` : formulaire modifié et avertissement de perte.
- `test_artifacts/session_visual_qa/student_back_after_expiry.png` : contrôle après navigation Retour.

