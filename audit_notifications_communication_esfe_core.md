# Audit du système notifications / communication — ESFE Core

Date de l’audit : 13 juillet 2026  
Périmètre : code présent dans le dépôt, sans modification métier, migration ou suppression de modèle.

## Verdict

**FONCTIONNEL MAIS FRAGMENTÉ.**

Le noyau `notifier` est cohérent, branché sur plusieurs flux métier et couvert par des tests ciblés. En revanche, l’expérience utilisateur varie fortement selon le dashboard, les préférences de canal ne sont pas réellement centralisées, le SMS est seulement déclaré comme futur, et la livraison ne dispose ni d’une file durable, ni de reprise automatique, ni de clé d’idempotence globale. Le reliquat `community.Notification` ajoute une dette d’architecture.

## 1. Architecture observée

Le chemin officiel est : producteur métier → `NotificationBus` → `NotificationEvent` → une `NotificationMessage` par canal → `Dispatcher` → canal in-app, WebSocket ou Brevo. `notification_center` lit les messages in-app et fournit liste, détail, dropdown, compteur et actions de lecture. Le WebSocket est injecté globalement par `templates/base.html`.

`community/services/notifications.py` est marqué déprécié mais reste appelé ; il délègue désormais au bus officiel. Le modèle historique `community.Notification` et ses traces d’administration restent présents. `migrate_communications` sert à importer d’anciennes tables.

## 2. Matrice A — Couverture des dashboards

| DASHBOARD | CLOCHE | COMPTEUR | DROPDOWN | CENTRE | WEBSOCKET | MESSAGES | PRÉFÉRENCES | ÉTAT |
|---|---|---|---|---|---|---|---|---|
| Gestionnaire | Oui (widget officiel) | Oui | Oui | Oui | Oui, global | Oui | Non trouvé | Branché |
| DG | Oui (widget + alertes DG) | Oui | Oui | Partiel | Oui, global | Oui | Non trouvé | Partiel |
| Informaticien | Oui, composant dédié | Oui | Oui | Oui, workspace dédié | Oui, global | Oui | Non trouvé | Branché mais spécifique |
| Enseignant | Oui, topbar dédiée | Oui | Partiel | Section HTMX dédiée | Oui, global | Oui | Non trouvé | Fragmenté |
| Secrétaire | Oui, topbar dédiée | Oui | Partiel | Section dédiée | Oui, global | Oui | Non trouvé | Fragmenté |
| Étudiant | Non trouvé dans les templates vérifiés | Non trouvé | Non trouvé | Non trouvé | Hérité si page basée sur `base.html` | Messages métier distincts possibles | Non trouvé | Couverture à confirmer |
| Admissions | Non trouvé | Non trouvé | Non trouvé | Non trouvé | Oui si layout global | Non trouvé | Non trouvé | Partiel |
| Finance | Non trouvé | Non trouvé | Non trouvé | Non trouvé | Oui si layout global | Non trouvé | Non trouvé | Partiel |
| Directeur / superviseur | Non trouvé | Non trouvé | Non trouvé | Non trouvé | Oui si layout global | Non trouvé | Non trouvé | Partiel |
| Superadmin | Non trouvé | Non trouvé | Non trouvé | Non trouvé | Oui si layout global | Actions d’administration, pas centre unifié | Non trouvé | Partiel |

Le contexte `notification_widget` exécute un comptage des non-lues sur chaque requête authentifiée. Le centre pagine à 20 éléments ; le widget utilise une fenêtre courte. Les dashboards spécialisés réimplémentent une partie de la présentation au lieu de partager un composant unique.

## 3. Matrice B — Événements et canaux

| ÉVÉNEMENT | PRODUCTEUR | DESTINATAIRES | INTERNE | WEBSOCKET | EMAIL | SMS | DASHBOARDS | TESTS | ÉTAT |
|---|---|---|---|---|---|---|---|---|---|
| candidature_submitted / accepted / rejected / document_missing | `admissions.signals` | candidat identifié | Oui | Selon politique | Oui transactionnel | Non | Admissions, gestionnaire, candidat selon flux | Oui, admissions/notifier | Actif |
| inscription_created / payment_pending / partial_payment / active | `inscriptions.signals`, superadmin | candidat | Oui | Selon politique | Oui transactionnel | Non | Admissions/gestionnaire/candidat | Oui | Actif |
| payment_validated | `payments.services.workflows` | étudiant | Oui | Silencieux | Non par défaut | Non | Finance/étudiant | Oui | Actif |
| first_payment_validated_staff | `payments.services.workflows` | finance/staff | Oui | Silencieux | Non | Non | Finance/gestionnaire | Oui | Actif |
| receipt_generated / payment_confirmation | payments, students | étudiant/client | Oui ou email seul | Non | Oui | Non | Finance/étudiant | Partiel | Actif |
| salary_available / teacher_honorarium_available | `accounts.services.manager_intelligence` | staff finance/payroll | Oui | Oui pour salaire | Non par défaut | Non | Gestionnaire/finance | Oui salaire, honoraire à renforcer | Actif |
| community_new_topic / new_answer / reply / accepted_answer / upvote | `community.services.notifications` | auteur, abonnés ou participants | Oui | Oui sauf upvote selon politique | Non | Non | Community et dashboards utilisant le centre | Smoke/tests ciblés | Actif mais legacy adjacent |
| shop_order_received / purchase_validated / order_ready / delivered | `shop.services.shop_service` | acheteur, gestionnaire | Oui | Oui selon événement | Oui pour certains | Non | Shop/gestionnaire | Oui partiel | Actif |
| diploma_ready / grades_session_complete / lesson_log_* | `academics.signals` | étudiant/enseignant/superviseur | Oui | Selon appel | Oui pour diplôme | Non | Académique | Tests de signaux partiels | Actif |
| sensitive_action_otp / grade_modification_otp | accounts, academic_cycle | utilisateur autorisé | Oui | Non | Oui | Non | Sécurité/portail | Oui | Actif |
| secretary_* (routed, appointment, document, task, report) | `secretary.services` | agents concernés | Oui | Selon politique | Non | Non | Secrétariat | Couverture faible | Actif |
| marketing.announcement / contact_* | marketing, core | audience/email | Variable | Non | Oui pour emails | Non | Back-office/public | Tests d’appel mockés | Actif |
| SMS générique | aucun provider actif | — | — | — | — | Déclaré `sms_future` | — | Aucun | Non implémenté |

La résolution d’audience applique l’annexe lorsqu’une branche est fournie et filtre les inscriptions actives. Le périmètre `all` reste volontairement global ; le resolver ne remplace pas un contrôle d’autorisation appelant.

## 4. Matrice C — Composants techniques

| COMPOSANT | FICHIER | RESPONSABILITÉ | UTILISÉ PAR | QUALITÉ | PROBLÈME | RECOMMANDATION |
|---|---|---|---|---|---|---|
| Événement | `notifier/models/event.py` | journal source, statut | Bus, audit | Bonne séparation | Pas de clé d’idempotence | Ajouter une clé métier/event contrôlée |
| Message | `notifier/models/message.py` | unité par destinataire/canal | Centre, dispatcher | Indexé et lisible | CASCADE sur suppression utilisateur, rétention absente | Politique d’archivage et conservation explicite |
| Livraison | `notifier/models/delivery.py` | tentative/provider | Dispatcher | Traçable | Une seule tentative, pas de retry durable | Worker/queue, backoff, dead-letter |
| Bus | `notifier/services/bus.py` | orchestration et `on_commit` | Producteurs | API claire | Overrides de canaux faciles à utiliser hors politique | Documenter/contrôler les overrides |
| Dispatcher | `notifier/services/dispatcher.py` | exécution canal | Bus | Gestion d’erreur correcte | Pas de reprise après crash | Rendre les jobs rejouables et idempotents |
| Politique | `notifier/services/policy.py` | défauts, priorité, audience | Bus/audience | Centralisée | Couverture inégale des nouveaux event types | Registre validé et test de couverture |
| Audience | `notifier/services/audience.py` | utilisateurs/annexes | Bus | Branches et rôles pris en compte | `set`/`IN` en mémoire, pas de bulk dispatch | Querysets paginés, service de diffusion par lots |
| Centre | `notification_center/selectors.py`, `views.py` | lecture, compteurs, filtres | Dashboards | Isolation utilisateur testée | Listes sans `select_related` systématique; préférences absentes | Optimiser queryset, ajouter préférences et archivage |
| WebSocket | `notifier/realtime/*`, partial realtime | push et toast | `base.html` | Sécurité authentifiée testée | Reconnexion fixe, JSON entrant non protégé | Backoff borné, validation de payload, métriques |
| Email | `notifier/providers/brevo.py`, `core.emailing` | transactionnel | Dispatcher | Fallbacks et tests | Registry retourne Brevo indépendamment du nom configuré; logs PII | Provider réellement sélectionné, journalisation minimisée |
| SMS | `notifier/services/channels.py` | futur | Dispatcher | Contrat explicite | Toujours `skipped` | Décider fournisseur, consentement, coût et observabilité |
| Compatibilité community | `community/models.py`, `community/services/notifications.py` | ancien modèle + façade | Community/admin | Migration prévue | Deux vocabulaires et risque de confusion | Geler les écritures legacy puis retirer après inventaire |
| Import historique | `notifier/management/commands/migrate_communications.py` | migration ancienne donnée | Exploitation | Idempotence annoncée | Pas de rapport de rapprochement permanent | Produire volumes, erreurs et doublons vérifiables |
| Configuration | `config.settings`, `base.html` | Redis/InMemory, email | ASGI/notifications | Fallback dev explicite | InMemory en environnement permissif peut masquer un défaut de prod | Check de configuration en déploiement |

## 5. Sécurité, annexes et données

- Les vues du centre filtrent par `recipient=request.user` et les tests couvrent l’isolation des lectures.
- L’audience de candidats refuse l’in-app/WebSocket si le compte n’est pas résolu, mais conserve l’email lorsque disponible.
- Le filtrage annexe est présent dans la résolution staff/étudiant lorsqu’un scope de branche est transmis. Il faut toutefois vérifier chaque producteur : le bus n’impose pas automatiquement une annexe.
- Les payloads et métadonnées JSON sont sérialisés (`make_json_safe`) mais ne constituent pas une politique de minimisation des données sensibles. Les logs Brevo contiennent l’adresse destinataire.
- La suppression d’un utilisateur supprime ses messages (`CASCADE`), ce qui peut contredire les besoins d’audit et de preuve de livraison.

## 6. Performance et exploitation

Le coût nominal est correct pour une notification individuelle : création événement/messages puis dispatch après commit. Les risques apparaissent pour les campagnes : audience matérialisée en mémoire, absence de bulk insert/queue, compteurs répétés du contexte processeur, et absence de purge/partitionnement des historiques. Redis est requis en production WebSocket, mais aucun worker de tâches durable (Celery/Huey/RQ) n’est configuré dans le chemin audité.

## 7. Tests et angles morts

Les tests ciblés `notifier notification_center` passent : **23 tests, 0 échec**. Ils couvrent politiques, fallback email, payload, authentification realtime, isolation du centre et lecture.

Manquent ou restent faibles : retry/backoff et échec provider, idempotence, SMS, préférences, gros volumes, campagne multi-annexe, purge/archivage, rendu de tous les dashboards, et intégration SMTP/Brevo réelle. Plusieurs tests métier vérifient seulement que `NotificationBus` est appelé (mock), pas que la livraison et l’affichage aboutissent.

## 8. Décisions proposées avant toute implémentation

### À conserver

`notifier` comme source officielle, `NotificationEvent`/`NotificationMessage`/`DeliveryAttempt`, politiques centralisées, isolation par destinataire, `notification_center` et WebSocket authentifié.

### À consolider

Un composant de cloche/centre réutilisable pour tous les dashboards, un registre d’événements documenté, les règles d’annexe/audience, et une stratégie d’observabilité (statuts, erreurs, volumes, latence).

### À déprécier puis retirer (après validation)

Le modèle `community.Notification` et tout lecteur/écriture restant réellement legacy, après export/rapprochement et vérification des volumes historiques.

### À décider explicitement

Préférences par canal et consentements, conservation des messages, comportement de suppression de compte, fournisseur SMS éventuel, queue de livraison, politique de retry, et niveau de visibilité des notifications pour chaque rôle.

## 9. Plan d’intégration recommandé (sans exécution dans cet audit)

1. Valider la matrice des dashboards et les événements obligatoires par rôle/annexe.
2. Ajouter les tests contractuels événement → destinataire → canal → interface.
3. Uniformiser le composant UI et exposer les préférences sans contourner la politique.
4. Introduire une livraison asynchrone rejouable avec idempotence et métriques.
5. Traiter SMS/marketing uniquement après décision de consentement et fournisseur.
6. Migrer puis retirer le legacy community après preuve de non-utilisation.

**Aucune implémentation n’a été effectuée après cet audit.**
