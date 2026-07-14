# Checkpoints de la refonte d'authentification

## Checkpoint 1 - Socle de sécurité et référence

Date : 12 juillet 2026

Résultat obtenu :

- validation centralisée des états inactif, suspendu et bloqué via
  `AuthenticationGate`;
- gate appliquée au login classique et au login par carte;
- validation locale du paramètre `next` pour le login et l'inscription publique;
- `/portal/it/v2/` limité à la position `it_support`;
- quatre flags V2 ajoutés et désactivés par défaut;
- cartographie Portal initiale écrite.

Fichiers propres au lot :

- `accounts/authentication.py`;
- `accounts/auth_views.py`;
- `accounts/views.py`;
- `accounts/test_authentication_security.py`;
- `students/views_carte.py`;
- `portal/views/it_dashboard_v2.py`;
- `config/settings.py`;
- `docs/authentication_portal_cartography.md`;
- `docs/authentication_refactor_checkpoints.md`.

Migrations : aucune.

Vérifications :

- `manage.py check --settings=config.settings_test_local` : réussi;
- compilation Python des fichiers du lot : réussie;
- suites `accounts portal` et tests ciblés : timeout respectivement après 2 et
  5 minutes avant production d'un résultat. Elles ne sont pas déclarées réussies.

Décisions : les corrections de redirection ouverte et de contrôle IT sont actives
immédiatement. AccessContext, Policy V2, shadow mode et nouveau routage Portal
restent désactivés.

Rollback : désactiver les flags V2 ne change encore aucun comportement. Le reste
du lot se retire fichier par fichier à partir de ce checkpoint; aucune donnée ni
structure de base n'a été modifiée.

Prochaine étape : challenge de carte signé et à usage unique, obligation de
changement de mot de passe après reset IT, révocation des sessions, puis tests
ciblés avec diagnostic du temps d'initialisation de la base de test.

## Checkpoint 2 - Challenge carte et cycle de session

Date : 12 juillet 2026

Résultat obtenu : challenge carte signé, expirant, lié à la session et à usage
unique ; `AuthenticationGate` commun avant connexion ; reset IT avec mot de passe
temporaire et révocation des sessions ; changement obligatoire du mot de passe ;
révocation après désactivation, suspension, blocage, changement de position ou
d'annexe.

Fichiers : `students/views_carte.py`, `students/tests_carte.py`,
`accounts/session_security.py`, `accounts/middleware.py`, `accounts/auth_views.py`,
`accounts/signals.py`, `portal/signals.py`, `portal/views/it_workflows.py` et
`accounts/test_authentication_security.py`.

Migrations : aucune pour ce checkpoint.

Vérifications : compilation Python et `git diff --check` réussis. Les tests ciblés
n'ont produit aucune sortie et ont atteint le timeout après 5 minutes, processus
Python toujours actif en CPU ; aucun succès n'est revendiqué.

Rollback : les changements sont isolés dans les fichiers ci-dessus. Les sessions
déjà révoquées ne sont pas restaurables, mais une reconnexion reste possible.

Prochaine étape : diagnostiquer l'initialisation Django, valider ce lot par les
tests, puis poursuivre la séparation PUBLIC/SYSTEM et le mode shadow.

## Checkpoint 3 - Policy V2 shadow et audit des comptes

Date : 12 juillet 2026

Résultat : la position V2 provient uniquement d'une affectation explicite ; les
groupes, `role`, `is_staff` et objets historiques ne créent plus d'identité SYSTEM.
Le middleware peut comparer l'ancienne classification à V2 sans modifier la
réponse. La commande `audit_access_state --dry-run --json` inventorie les comptes
invalides ou ambigus. Seul l'alias déterministe `branch_manager -> annex_manager`
peut être appliqué avec `--apply`.

Tests : 15/15 réussis. `manage.py check` et la commande en dry-run réussis.
Rollback : désactiver `AUTH_POLICY_V2_SHADOW_ENABLED`; la commande n'écrit rien
sans `--apply`.

## Checkpoint 4 - Séparation progressive des profils et routage Portal

Date : 12 juillet 2026

Résultat : ajout de `PublicCommunityProfile` et `InstitutionalProfile`, conservation
du `Profile` historique, copie réversible des données et double écriture transitoire.
Les activités communautaires sont conservées pour tous les comptes. Le routage V2
sépare PUBLIC et SYSTEM, refuse les affectations incomplètes via une page de
régularisation et donne à ANNEX_MANAGER une seule entrée Portal.

Migration : `accounts.0025_split_public_and_institutional_profiles`, réversible.

Tests : 18/18 réussis ; aucune migration de modèle manquante ; checks Django
réussis. La configuration SQLite de test conserve désormais réellement la base
avec `--keepdb`, réduisant fortement le temps des exécutions suivantes.

Rollback : désactiver `AUTH_PORTAL_ROUTING_V2_ENABLED`; la route et les lectures
historiques restent disponibles. La migration inverse supprime seulement les
copies nouvelles et ne touche pas au `Profile` historique.

## Checkpoint 5 - Enforcement ANNEX_MANAGER

Date : 12 juillet 2026

Résultat : lorsque `AUTH_POLICY_V2_ENABLED` est actif, le shell et les endpoints
HTMX centralisés de la gestionnaire appliquent Policy V2. Une appartenance au
groupe `gestionnaire` ne suffit plus : la position officielle `annex_manager` et
une annexe valide sont obligatoires. La branche injectée dans les querysets vient
du contexte institutionnel V2.

Tests : 21/21 tests sécurité/routage/policy et 72/72 tests des workflows complets
gestionnaire réussis. Checks Django et détection des migrations réussis.

Décision : le flag reste désactivé par défaut pour permettre le shadow et la
régularisation préalable des comptes réels. Aucun alias ambigu n'est converti.

Rollback : désactiver `AUTH_POLICY_V2_ENABLED`; les décorateurs reprennent la
compatibilité historique. Les endpoints et services métier n'ont pas été déplacés.

Prochaine étape : exécuter l'audit sur une copie des données réelles, régulariser
les comptes ambigus, puis étendre l'enforcement position par position aux autres
dashboards et à leurs exports/endpoints spécialisés.

## Checkpoint 6 - Extension multi-dashboards et audit réel

Date : 12 juillet 2026

Résultat : `get_user_position` et `can_access` basculent centralement vers
`InstitutionalProfile` lorsque Policy V2 est active. Étudiant, enseignant,
secrétaire, admissions, finance, direction des études, surveillance, IT,
marketing, DG/DGA et super-administration héritent ainsi du deny-by-default dans
leurs contrôles existants. Les anciennes entrées finance, admissions et secrétaire
redirigent vers leur entrée Portal sous le flag de routage. SUPER_ADMIN métier est
séparé de `is_superuser`. Le WebSocket de notifications réévalue aussi l'état du
compte avec `AuthenticationGate`.

Correctif métier connexe : restauration de la recherche de `PayrollEntry` dans
le workflow de saisie/correction des salaires gestionnaire. Les cinq tests salaire
et OTP concernés réussissent.

Tests : 35/35 sécurité et WebSocket, 32/32 superadmin/positions, 72/72 workflows
gestionnaire. Une suite élargie de 387 tests a exposé des échecs préexistants ou
contradictoires avec les nouvelles règles (fixtures académiques, attentes de
templates et ancien test autorisant les préférences pendant un changement de mot
de passe obligatoire). Ils ne sont pas déclarés résolus par ce checkpoint.

Base réelle : migrations `accounts.0024` et `accounts.0025` appliquées. Audit sur
57 comptes : 37 valides, 19 ambigus, 1 invalide faute d'annexe. L'unique alias
déterministe (user_id 62) a été normalisé en `annex_manager`. Aucun autre compte
n'a été modifié automatiquement.

Blocage de bascule : les user_id 2, 4, 15, 19, 40, 41, 42, 44, 46, 54, 65, 67,
90, 91, 95, 97, 98, 100 et 101 nécessitent une position officielle confirmée.
Le user_id 56 nécessite une annexe confirmée. Les flags V2 doivent rester
désactivés par défaut jusqu'à cette régularisation.
