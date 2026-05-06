# ESFE Core Communication Workflows Blueprint

## Scope

Ce document formalise l'architecture metier de communication a utiliser dans `ESFE Core` avant l'industrialisation des templates, automatisations et integrations provider.

Principes directeurs :

- `communication/` est l'unique noyau officiel pour les notifications, emails transactionnels et realtime.
- Les domaines metier restent separes. On mutualise l'infrastructure, pas les usages metier.
- Chaque workflow doit etre rattache a un evenement metier stable.
- Les canaux sont choisis par criticite et contexte utilisateur.
- On renforce l'existant sans casser les flux deja en production.

## Noyau Technique Officiel

Composants centraux deja valides :

- `CommunicationEvent`
- `CommunicationNotification`
- `CommunicationDelivery`
- `CommunicationEventBus`
- `NotificationService`
- `EmailService`
- provider `brevo`
- realtime centralise `communication/realtime`

Canaux officiels :

- `email_transactional`
- `in_app`
- `websocket`
- `dashboard_alert`
- `sms_future`

Note : `dashboard_alert` et `sms_future` doivent etre traites comme couches fonctionnelles a formaliser au-dessus des modeles actuels. Le stockage natif deja present aujourd'hui couvre surtout `email_transactional`, `in_app` et `websocket`.

## Regles De Conception

- Utiliser des evenements metier stables en `UPPER_SNAKE_CASE` comme nomenclature officielle.
- Conserver temporairement les `event_type` existants en base et en code tant qu'une migration de nomenclature n'est pas planifiee.
- Distinguer `evenement`, `notification`, `livraison provider` et `etat UX`.
- Regrouper les notifications bruyantes par lot quand le cas metier le justifie.
- Eviter les emails sur des evenements faibles quand `in_app` + `websocket` suffisent.

## Cartographie Metier

### 1. Admissions

Evenements deja observes dans le code :

| Canonique | Event type actuel | Statut | Destinataire principal | Canaux recommandes |
|---|---|---|---|---|
| `CANDIDATE_SUBMITTED` | `candidature_submitted` | actif | candidat | `email_transactional` si externe seul, sinon `email_transactional` + `in_app` + `websocket` |
| `CANDIDATE_UNDER_REVIEW` | `candidature_under_review` | actif | candidat | `email_transactional` + `in_app` + `websocket` |
| `CANDIDATE_TO_COMPLETE` | `candidature_to_complete` | actif | candidat | `email_transactional` + `in_app` + `websocket` |
| `CANDIDATE_ACCEPTED` | `candidature_accepted` | actif | candidat | `email_transactional` + `in_app` + `websocket` |
| `CANDIDATE_ACCEPTED_WITH_RESERVE` | `candidature_accepted_with_reserve` | actif | candidat | `email_transactional` + `in_app` + `websocket` |
| `CANDIDATE_REJECTED` | `candidature_rejected` | actif | candidat | `email_transactional` + `in_app` + `websocket` |
| `MISSING_DOCUMENTS` | `document_missing` | actif | candidat | `email_transactional` + `in_app` + `websocket` |

Variables templates prioritaires :

- `recipient_name`
- `candidature_reference`
- `programme`
- `academic_year`
- `status_label`
- `admin_comment`
- `dashboard_url`
- `missing_documents`

Automatisations officielles :

- `CANDIDATE_UNDER_REVIEW` + pieces manquantes detectees -> emettre `MISSING_DOCUMENTS`
- `CANDIDATE_ACCEPTED` ou `CANDIDATE_ACCEPTED_WITH_RESERVE` -> ouvrir le workflow d'inscription
- `CANDIDATE_REJECTED` -> clore le parcours d'admission sans onboarding

UX/dashboard :

- badge statut candidature
- timeline de traitement
- alerte haute priorite pour dossiers incomplets
- regroupement par reference de candidature

### 2. Inscriptions

Evenements deja observes dans le code :

| Canonique | Event type actuel | Statut | Destinataire principal | Canaux recommandes |
|---|---|---|---|---|
| `REGISTRATION_CREATED` | `inscription_created` | actif | candidat/inscrit | `email_transactional` + `in_app` + `websocket` |
| `REGISTRATION_PAYMENT_PENDING` | `inscription_payment_pending` | actif | candidat/inscrit | `email_transactional` + `in_app` + `websocket` |
| `REGISTRATION_PARTIAL_PAYMENT` | `inscription_partial_payment` | actif | inscrit | `email_transactional` + `in_app` + `websocket` |
| `REGISTRATION_ACTIVATED` | `inscription_active` | actif | inscrit | `email_transactional` + `in_app` + `websocket` |
| `REGISTRATION_SUSPENDED` | `inscription_suspended` | actif | inscrit | `email_transactional` + `in_app` + `websocket` + `dashboard_alert` |
| `REGISTRATION_EXPIRED` | `inscription_expired` | actif | inscrit | `email_transactional` + `in_app` + `websocket` + `dashboard_alert` |
| `REGISTRATION_COMPLETED` | `inscription_completed` | actif | inscrit | `email_transactional` + `in_app` + `websocket` |

Variables templates prioritaires :

- `reference`
- `programme`
- `academic_year`
- `dashboard_url`
- `amount_due`
- `payment_deadline`
- `status_label`

Automatisations officielles :

- `REGISTRATION_ACTIVATED` -> verifier le premier paiement et le provisionnement etudiant
- `REGISTRATION_PAYMENT_PENDING` -> relances echeance futures
- `REGISTRATION_SUSPENDED` -> alerte dashboard admin et finance

UX/dashboard :

- alertes echeances paiement
- cartes de suivi du statut inscription
- regroupement par inscription et par etudiant

### 3. Payments / Finance

Evenements deja observes ou clairement derives du code :

| Canonique | Source actuelle | Statut | Destinataire principal | Canaux recommandes |
|---|---|---|---|---|
| `PAYMENT_VALIDATED` | `payments.models.Payment.save()` | derive actif | etudiant/inscrit | `email_transactional` + `in_app` + `websocket` |
| `FIRST_PAYMENT_VALIDATED` | `create_student_after_first_payment()` | derive actif | inscrit | `email_transactional` + `in_app` + `websocket` + `dashboard_alert` |
| `PAYMENT_CONFIRMATION_SENT` | `payment_confirmation` | actif | etudiant | `email_transactional` |
| `RECEIPT_GENERATED` | generation recu PDF | derive actif | etudiant + finance | `email_transactional` + `dashboard_alert` |
| `INVOICE_GENERATED` | a formaliser | cible | etudiant + finance | `email_transactional` + `in_app` |
| `PAYMENT_FAILED` | a formaliser | cible | payeur + finance | `email_transactional` + `dashboard_alert` |
| `PAYMENT_OVERDUE` | a formaliser | cible | etudiant + finance | `email_transactional` + `in_app` + `dashboard_alert` + `sms_future` |

Variables templates prioritaires :

- `payment_reference`
- `receipt_number`
- `amount`
- `currency`
- `programme`
- `student_name`
- `payment_date`
- `remaining_balance`
- `receipt_url`
- `invoice_url`

Pieces jointes / documents :

- recu PDF
- facture PDF future

Automatisations officielles :

- `FIRST_PAYMENT_VALIDATED` -> creation compte etudiant si absent
- `RECEIPT_GENERATED` -> email automatique avec PDF ou lien securise
- `PAYMENT_OVERDUE` -> relances progressives J+X

UX/dashboard :

- alertes de paiements en retard
- compteur finance prioritaire
- groupe de notifications par etudiant et par echeance

### 4. Students / Onboarding

Evenements deja observes :

| Canonique | Event type actuel | Statut | Destinataire principal | Canaux recommandes |
|---|---|---|---|---|
| `STUDENT_ACCOUNT_CREATED` | creation dans `create_student_after_first_payment` | derive actif | etudiant | `email_transactional` + `dashboard_alert` |
| `STUDENT_WELCOME_CREDENTIALS` | `student_welcome_credentials` | actif | etudiant | `email_transactional` |
| `PAYMENT_CONFIRMATION` | `payment_confirmation` | actif | etudiant | `email_transactional` |

Variables templates prioritaires :

- `username`
- `temporary_password`
- `student_name`
- `programme`
- `academic_year`
- `portal_url`
- `branch_name`

Automatisations officielles :

- `FIRST_PAYMENT_VALIDATED` -> `STUDENT_ACCOUNT_CREATED`
- `STUDENT_ACCOUNT_CREATED` -> `STUDENT_WELCOME_CREDENTIALS`
- premier acces effectue -> futur email de securisation / changement mot de passe

UX/dashboard :

- badge "compte cree"
- badge "identifiants envoyes"
- alerte si email etudiant absent ou invalide

### 5. Teachers

Evenements deja observes :

| Canonique | Event type actuel | Statut | Destinataire principal | Canaux recommandes |
|---|---|---|---|---|
| `TEACHER_ACCOUNT_CREATED` | `teacher_account_created` | actif | enseignant | `email_transactional` |
| `TEACHER_ASSIGNMENTS_UPDATED` | journalise seulement | a formaliser | enseignant + direction | `email_transactional` + `in_app` |
| `TEACHER_DOCUMENT_UPLOADED` | workflow metier present | a formaliser | direction | `dashboard_alert` + `websocket` |
| `TEACHER_DOCUMENT_REVIEWED` | workflow metier present | a formaliser | enseignant + direction | `email_transactional` + `in_app` |
| `TEACHER_CONTRACT_GENERATED` | generation PDF presente | a formaliser | enseignant + direction | `email_transactional` + `dashboard_alert` |

Variables templates prioritaires :

- `teacher_name`
- `username`
- `temporary_password`
- `branch_name`
- `class_labels`
- `ec_labels`
- `contract_url`
- `document_type`
- `review_status`

Automatisations officielles :

- creation enseignant -> email acces enseignant
- contrat genere -> notification ou email avec lien/PDF
- document refuse -> alerte prioritaire pour correction

UX/dashboard :

- suivi des comptes enseignants
- statut dossier enseignant
- alertes de pieces non conformes

### 6. Community

Evenements deja observes dans le runtime centralise :

| Canonique | Event type actuel | Statut | Destinataire principal | Canaux recommandes |
|---|---|---|---|---|
| `COMMUNITY_TOPIC_CREATED` | `community_new_topic` | actif | audience cible | `in_app` + `websocket` |
| `COMMUNITY_REPLY` | `community_new_answer` | actif | auteur du sujet | `in_app` + `websocket` + `email_transactional` optionnel |
| `COMMUNITY_REPLY_TO_REPLY` | `community_reply_to_reply` | actif | auteur du message parent | `in_app` + `websocket` + `email_transactional` optionnel |
| `COMMUNITY_UPVOTE` | `community_upvote` | actif avec regroupement | auteur du contenu | `in_app` + `websocket` |
| `COMMUNITY_ACCEPTED_ANSWER` | `community_accepted_answer` | actif | auteur de la reponse | `in_app` + `websocket` + `email_transactional` optionnel |
| `COMMUNITY_MENTION` | a formaliser | cible | utilisateur mentionne | `in_app` + `websocket` + `email_transactional` optionnel |

Variables templates prioritaires :

- `topic_title`
- `topic_url`
- `answer_excerpt`
- `actor_name`
- `vote_count`
- `mentioned_context`

Automatisations officielles :

- regrouper `COMMUNITY_UPVOTE` par fenetre temporelle
- ne pas envoyer d'email si l'utilisateur est deja actif dans la session recente
- escalader en priorite normale seulement pour reponse acceptee ou mention

UX/dashboard :

- dropdown temps reel
- regroupement des upvotes
- lecture/marquage lu
- navigation directe vers le topic

### 7. Contact Public

Evenements deja observes :

| Canonique | Event type actuel | Statut | Destinataire principal | Canaux recommandes |
|---|---|---|---|---|
| `PUBLIC_CONTACT_SUBMITTED_INTERNAL` | `contact_internal` | actif | administration interne | `email_transactional` + `dashboard_alert` |
| `PUBLIC_CONTACT_RECEIVED_CONFIRMATION` | `contact_received` | actif | expediteur public | `email_transactional` |
| `PUBLIC_CONTACT_REPLIED` | `contact_reply` | actif | expediteur public | `email_transactional` |

Variables templates prioritaires :

- `sender_name`
- `sender_email`
- `subject_label`
- `message_body`
- `ticket_reference`
- `staff_name`
- `reply_date`

Automatisations officielles :

- soumission publique -> notification dashboard admin
- absence de reponse dans le SLA -> alerte critique interne
- reponse envoyee -> cloture ou passage en `answered`

UX/dashboard :

- file de messages entrants
- indicateur SLA / retard
- badge urgent / traite / clos

### 8. Securite / Auth

Flux deja presents dans le projet :

- URLs Django `password_reset` et `password_change`
- reset de mot de passe IT via `it_reset_password`
- etat support `must_change_password`
- journalisation `SupportAuditLog.ACTION_PASSWORD_RESET`

Evenements officiels a retenir :

| Canonique | Source actuelle | Statut | Destinataire principal | Canaux recommandes |
|---|---|---|---|---|
| `PASSWORD_RESET_REQUESTED` | Django auth | partiel | utilisateur | `email_transactional` |
| `PASSWORD_RESET_COMPLETED` | Django auth | partiel | utilisateur + securite interne | `email_transactional` + `dashboard_alert` |
| `PASSWORD_RESET_BY_IT` | `it_reset_password` | workflow actif non notifie | utilisateur cible + IT | `email_transactional` + `dashboard_alert` |
| `PASSWORD_CHANGE_REQUIRED` | `must_change_password` | non notifie | utilisateur cible | `in_app` + `dashboard_alert` + `email_transactional` |
| `ACCOUNT_SUSPENDED` | support account state | a formaliser | utilisateur cible + IT | `email_transactional` + `dashboard_alert` |
| `ACCOUNT_REACTIVATED` | support account state | a formaliser | utilisateur cible + IT | `email_transactional` + `dashboard_alert` |
| `ACCOUNT_BLOCKED` | support account state | a formaliser | utilisateur cible + IT | `dashboard_alert` + `sms_future` |

Variables templates prioritaires :

- `user_name`
- `reset_link`
- `temporary_password`
- `branch_name`
- `support_contact`
- `security_reason`
- `must_change_password`

Automatisations officielles :

- reset par IT -> email immediat avec mot de passe temporaire ou lien securise
- `must_change_password=True` -> alerte persistante en portail
- comptes bloques multiples echecs -> notification securite interne

UX/dashboard :

- alertes critiques pour blocage compte
- bandeau obligatoire "changer le mot de passe"
- historique des actions support

### 9. Academique / Resultats / Dashboards

Flux metier presents mais peu ou pas encore notifies :

- validation des resultats semestriels
- publication des resultats
- rejet pour correction
- supervision presence enseignant
- journaux de cours et etat pedagogique

Evenements officiels a formaliser :

| Canonique | Source actuelle | Statut | Destinataire principal | Canaux recommandes |
|---|---|---|---|---|
| `RESULTS_VALIDATED` | `director_results_action` | workflow actif non notifie | direction | `dashboard_alert` |
| `RESULTS_PUBLISHED` | `director_results_action` | workflow actif non notifie | etudiants + direction | `email_transactional` + `in_app` + `websocket` + `dashboard_alert` |
| `RESULTS_RETURNED_FOR_CORRECTION` | `director_results_action` | workflow actif non notifie | enseignants/direction | `email_transactional` + `dashboard_alert` |
| `TEACHER_ATTENDANCE_MARKED` | supervision | workflow actif non notifie | supervision | `dashboard_alert` |
| `PEDAGOGY_CRITICAL_ALERT` | etat cours/absence | derive cible | supervision + direction | `dashboard_alert` + `websocket` |

Variables templates prioritaires :

- `semester_label`
- `academic_class`
- `publication_date`
- `results_url`
- `teacher_name`
- `course_label`
- `alert_reason`

Automatisations officielles :

- `RESULTS_PUBLISHED` -> informer etudiants concernes
- `RESULTS_RETURNED_FOR_CORRECTION` -> notifier les responsables pedagogiques
- absence enseignant avec cours planifie -> alerte temps reel supervision

UX/dashboard :

- centre d'alertes direction
- cartes critiques pedagogiques
- badges de publication resultats

## Matrice Des Canaux

Regles pragmatiques d'allocation :

| Type de workflow | Email | In-app | Websocket | Dashboard | SMS futur |
|---|---|---|---|---|---|
| decision d'admission | oui | oui si compte existe | oui si compte existe | optionnel | non |
| etape d'inscription | oui | oui | oui | optionnel | relance eventuelle |
| paiement / recu | oui | oui | oui | oui pour finance | oui pour retard critique |
| creation compte | oui | optionnel | non prioritaire | oui interne | non |
| community faible | non ou optionnel | oui | oui | non | non |
| securite critique | oui | oui | optionnel | oui | oui a terme |
| publication resultats | oui | oui | oui | oui | non |
| contact public | oui | non | non | oui interne | non |

## Familles De Templates Officielles

### Admissions

- soumission candidature
- candidature en analyse
- admission acceptee
- admission sous reserve
- candidature a completer
- candidature rejetee

Variables communes :

- `brand_name`
- `logo_url`
- `recipient_name`
- `programme`
- `academic_year`
- `dashboard_url`
- `support_email`

### Payments / Finance

- confirmation paiement
- premier paiement valide
- recu disponible
- facture disponible
- relance impaye

Variables communes :

- `student_name`
- `payment_reference`
- `receipt_number`
- `amount`
- `currency`
- `due_date`
- `receipt_url`
- `invoice_url`

### Onboarding

- compte etudiant cree
- compte enseignant cree
- acces portail
- changement mot de passe requis

Variables communes :

- `username`
- `temporary_password`
- `portal_url`
- `branch_name`
- `support_contact`

### Securite

- reset mot de passe
- compte suspendu
- compte reactive
- tentative critique ou action IT

Variables communes :

- `user_name`
- `reset_link`
- `temporary_password`
- `security_reason`
- `support_contact`

### Academique

- resultats publies
- resultats a corriger
- alerte pedagogique

Variables communes :

- `academic_class`
- `semester_label`
- `results_url`
- `teacher_name`
- `alert_reason`

### Community

- nouvelle reponse
- reponse a une reponse
- reponse acceptee
- mention

Variables communes :

- `topic_title`
- `topic_url`
- `actor_name`
- `excerpt`

## Regles UX / Realtime

- Priorite `critical` : securite, blocage compte, impayes critiques, alertes SLA.
- Priorite `high` : admission a completer, inscription suspendue, resultats publies, contact en retard.
- Priorite `normal` : confirmation paiement, creation compte, reponses community importantes.
- Priorite `low` : signaux communautaires faibles et rappels non critiques.

Regles de regroupement :

- regrouper les upvotes community
- regrouper les relances finance par echeance
- regrouper les notifications multi-evenements d'un meme dossier uniquement si la lecture reste claire

Regles dashboard :

- un centre d'alertes par role vaut mieux qu'un melange global
- les compteurs doivent pouvoir filtrer par priorite, domaine et statut
- les liens de redirection doivent toujours ouvrir le bon ecran metier

## Ecart Entre Existant Et Cible

Existant deja robuste :

- admissions
- inscriptions
- paiement de base et onboarding etudiant
- creation compte enseignant par email
- contact public
- community centralise
- Brevo SMTP et pipeline transactionnel

Points a formaliser ensuite sans casser l'existant :

- nomenclature canonique des evenements
- couche `dashboard_alert`
- workflows securite/auth centralises
- publication des resultats
- notifications finance avancees : impayes, factures, relances
- workflow enseignant : contrat, documents, affectations
- mentions community

## Ordre De Mise En Oeuvre Recommande

1. Stabiliser le catalogue officiel des evenements et leurs alias actuels.
2. Factoriser les familles de templates transactionnels.
3. Implementer les workflows securite/auth manquants.
4. Industrialiser payments/finance : recus, factures, relances.
5. Ajouter resultats publies et alertes pedagogiques.
6. Etendre le workflow enseignant.
7. Finaliser dashboard alerts et futures relances SMS.

## References Code

Flux actuellement confirmes dans le code :

- `admissions/signals.py`
- `inscriptions/signals.py`
- `payments/models.py`
- `students/services/create_student.py`
- `students/services/email.py`
- `community/services/notifications.py`
- `core/views.py`
- `core/admin.py`
- `portal/services/director/teacher_management_service.py`
- `portal/views/views.py`
- `communication/models/events.py`
- `communication/models/notifications.py`
- `communication/services/email_service.py`
- `communication/services/notification_service.py`

Ce blueprint doit servir de base officielle avant toute implementation massive de nouveaux templates, automatisations ou integrations provider.
