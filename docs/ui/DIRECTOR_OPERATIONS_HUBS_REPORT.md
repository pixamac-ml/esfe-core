# Modules opérationnels du Directeur des études

## Périmètre livré

- **Transferts** est désormais une section indépendante de la sidebar.
- **Messagerie interne** dispose d'une boîte de réception, des messages envoyés, des archives, d'une lecture détaillée et d'un formulaire de réponse/envoi.
- **Finance** regroupe le suivi mensuel de la caisse, des salaires, des honoraires et des dépenses.

## Règles métier sécurisées

- Toutes les données de transfert et de finance sont filtrées par l'annexe du DE.
- La validation d'un transfert de classe met à jour l'inscription académique et l'inscription administrative dans une transaction unique.
- Le transfert vers une autre école clôture et archive l'inscription sans supprimer l'historique.
- Les destinataires de la messagerie sont limités aux comptes actifs de la même annexe.
- Le DE ne peut pas provoquer directement une sortie de caisse : il transmet une demande aux gestionnaires ou agents financiers habilités.
- Les salaires du personnel et les honoraires enseignants restent deux circuits distincts.

## Vérifications

- `python manage.py check --settings=config.settings_test_local`
- `python manage.py makemigrations --check --dry-run --settings=config.settings_test_local`
- `python manage.py test --settings=config.settings_test_local --keepdb --noinput portal` : **102 tests réussis**.
- Suite ciblée finale des modules DE : **43 tests réussis**.
- `python manage.py test --settings=config.settings_test_local --keepdb --noinput ui` : **110 tests réussis**.
- `npm run build:css`
- Playwright sur desktop `1440x1000` et mobile `390x844` : aucun débordement horizontal, aucune erreur console ou JavaScript.

Captures et résultat automatisé : `_audit/director_operations_hubs/`.






# Correction et approfondissement des modules opérationnels du Directeur des Études

Les modules actuellement créés pour le dashboard du Directeur des Études constituent une bonne base, mais trois points métier doivent être corrigés et approfondis avant de considérer cette partie comme finalisée.

---

## 1. Corriger complètement la section Finance / Salaires

### Problème constaté

La section actuelle a été conçue comme si le Directeur des Études participait à la gestion financière de l’annexe, notamment au suivi global de la caisse, des salaires, des honoraires et des dépenses.

Cette interprétation est incorrecte.

Le Directeur des Études est un employé de l’établissement. Il perçoit un salaire, mais il ne gère pas les salaires du personnel.

La gestion des salaires relève exclusivement de la gestionnaire ou des agents financiers habilités.

### Responsabilités de la gestionnaire

La gestionnaire est responsable de :

* la préparation des salaires ;
* la validation des paiements ;
* l’enregistrement des paiements ;
* la génération des fiches de paie ;
* la génération des reçus ou justificatifs de salaire ;
* la gestion des retenues, avances ou régularisations ;
* le suivi global des salaires du personnel ;
* le suivi des honoraires des enseignants ;
* la gestion de la caisse, des dépenses et des sorties financières.

Ces fonctionnalités ne doivent pas être accessibles au Directeur des Études.

### Nouvelle fonction de la section du Directeur des Études

Dans le dashboard du Directeur des Études, la section `Finance` doit être supprimée ou renommée en :

* `Mon salaire`
* ou simplement `Salaire`

Cette section doit uniquement permettre au Directeur des Études de consulter les informations relatives à sa propre rémunération.

### Informations à afficher

Le Directeur des Études doit pouvoir consulter :

* son salaire mensuel de référence ;
* le mois concerné ;
* l’année concernée ;
* le montant brut ;
* les éventuelles retenues ;
* les éventuelles primes ;
* le montant net ;
* la date de préparation du salaire ;
* la date de paiement ;
* le mode de paiement ;
* la référence du paiement ;
* le statut du salaire.

### Statuts possibles

Prévoir des statuts explicites, par exemple :

* `En attente`
* `En préparation`
* `Prêt pour paiement`
* `Payé`
* `Paiement échoué`
* `Annulé`
* `Régularisé`

### Historique personnel

Le Directeur des Études doit disposer d’un historique mensuel de ses propres paiements.

Exemple :

| Mois         |  Montant net | Statut             | Date de paiement | Action      |
| ------------ | -----------: | ------------------ | ---------------- | ----------- |
| Janvier 2026 | 150 000 FCFA | Payé               | 31/01/2026       | Télécharger |
| Février 2026 | 150 000 FCFA | Payé               | 28/02/2026       | Télécharger |
| Mars 2026    | 150 000 FCFA | Payé               | 31/03/2026       | Télécharger |
| Août 2026    | 150 000 FCFA | Prêt pour paiement | —                | Voir        |

### Documents téléchargeables

Lorsque le salaire est payé ou validé, le Directeur des Études doit pouvoir télécharger :

* sa fiche de paie ;
* son reçu de paiement ;
* éventuellement une attestation de salaire si ce document est prévu par le système.

### Règle de sécurité impérative

Le Directeur des Études :

* ne voit que ses propres informations salariales ;
* ne voit pas les salaires des autres employés ;
* ne prépare aucun salaire ;
* ne valide aucun salaire ;
* ne modifie aucun montant ;
* ne déclenche aucun paiement ;
* ne consulte pas la caisse ;
* ne consulte pas les dépenses globales ;
* ne gère pas les honoraires enseignants.

La gestion complète des salaires reste exclusivement dans le dashboard de la gestionnaire.

---

## 2. Transformer la messagerie actuelle en système global de communication interne

### État actuel

La messagerie interne déjà créée est une bonne base.

Elle possède notamment :

* une boîte de réception ;
* des messages envoyés ;
* des archives ;
* une lecture détaillée ;
* un formulaire d’envoi ;
* un système de réponse.

Il ne faut pas supprimer cette base. Il faut la peaufiner, la généraliser et la transformer en véritable module central de communication interne.

### Principe d’architecture

Ce système de communication ne doit pas être conçu uniquement pour le Directeur des Études.

Il doit devenir un module réutilisable dans tous les dashboards :

* Directeur Général ;
* Directeur des Études ;
* Surveillant Général ;
* Gestionnaire ;
* Secrétaire ;
* Informaticien ;
* Enseignants ;
* Étudiants ;
* autres membres du staff.

Il faut éviter de recréer une messagerie différente pour chaque dashboard.

Créer un moteur central de communication et des composants UI réutilisables.

### Sélection des destinataires

Lors de l’envoi d’un message, l’utilisateur habilité doit pouvoir cibler :

* un utilisateur précis ;
* plusieurs utilisateurs ;
* tous les utilisateurs d’un rôle ;
* tous les étudiants ;
* tous les enseignants ;
* tout le staff ;
* les étudiants et les enseignants ;
* une ou plusieurs classes ;
* un niveau ;
* une filière ;
* une annexe ;
* une école ;
* plusieurs groupes combinés.

### Exemples d’utilisation

Le Directeur des Études doit pouvoir :

* envoyer un message à tous les membres du staff ;
* envoyer un message uniquement aux étudiants ;
* envoyer un message uniquement aux enseignants ;
* sélectionner simultanément les étudiants et les enseignants ;
* envoyer un message aux étudiants d’une classe précise ;
* envoyer une information aux enseignants d’une filière ;
* contacter individuellement un utilisateur.

### Interface de sélection

Prévoir une interface claire avec :

* filtres par type d’utilisateur ;
* filtres par rôle ;
* filtres par annexe ;
* filtres par école ;
* filtres par filière ;
* filtres par niveau ;
* filtres par classe ;
* recherche par nom, matricule ou adresse électronique ;
* sélection multiple ;
* bouton `Tout sélectionner` ;
* compteur du nombre de destinataires ;
* possibilité de retirer certains destinataires avant l’envoi.

### Fonctionnalités attendues

Le module doit progressivement inclure :

* boîte de réception ;
* messages envoyés ;
* brouillons ;
* archives ;
* corbeille ;
* messages lus et non lus ;
* accusé de lecture ;
* pièces jointes ;
* réponses ;
* transfert de message ;
* conversations ou fils de discussion ;
* notifications internes ;
* recherche ;
* filtrage ;
* pagination ;
* messages épinglés ;
* priorité normale, importante ou urgente ;
* archivage ;
* suppression logique ;
* historique des actions.

### Permissions

Le ciblage collectif doit être contrôlé par permissions.

Par exemple :

* un étudiant ne doit pas pouvoir envoyer un message à toute l’école ;
* un enseignant ne doit pas pouvoir sélectionner tous les utilisateurs sans autorisation ;
* le Directeur des Études peut communiquer avec les groupes relevant de son périmètre ;
* le Directeur Général peut disposer d’un périmètre plus large ;
* les données doivent rester filtrées selon l’école et l’annexe lorsque cela est nécessaire.

### Objectif final

La messagerie doit devenir un système de communication interne central, propre, fiable, réutilisable et suffisamment modulaire pour être intégré dans tous les dashboards sans duplication de logique métier.

---

## 3. Reconcevoir le module de transferts autour de plusieurs cas métier

### Principe général

Le transfert ne doit pas être traité comme une simple modification de classe.

Il s’agit d’un véritable processus académique et administratif avec plusieurs scénarios distincts.

Le module doit rester dans une section indépendante du dashboard du Directeur des Études.

Il ne doit pas être noyé dans la gestion des enseignants, des inscriptions ou des classes.

Il faut prévoir au minimum les catégories suivantes :

1. transfert interne de filière ou de classe ;
2. transfert sortant vers une autre école ;
3. transfert entrant depuis une autre école.

---

# A. Transfert interne de filière ou de classe

## Définition

Le transfert interne concerne un étudiant qui reste dans le même établissement, mais change de filière, de programme ou de classe de rattachement.

### Règle fondamentale sur le niveau

Un transfert interne ne doit pas permettre à un étudiant de changer librement de niveau académique.

Le passage d’un niveau vers un niveau supérieur relève du processus de passage annuel, de promotion ou de redoublement.

Le transfert sert à modifier le rattachement de l’étudiant vers une autre filière ou une autre classe compatible avec son niveau académique validé.

### Cas 1 : étudiant redoublant

Exemple :

* l’étudiant était inscrit en Biologie médicale ;
* ses résultats ne lui permettent pas de poursuivre normalement ;
* il redouble ;
* après étude de son dossier, l’établissement l’oriente vers Sage-femme ;
* il reste dans un niveau équivalent ;
* le Directeur des Études effectue un transfert interne vers la nouvelle filière.

Dans ce cas :

* le niveau académique reste cohérent avec sa situation de redoublement ;
* l’ancienne inscription doit rester dans l’historique ;
* une nouvelle affectation académique est créée ;
* le motif du transfert est enregistré ;
* la décision d’orientation ou de réorientation doit pouvoir être jointe au dossier.

### Cas 2 : étudiant admis en classe supérieure qui change de filière

Exemple :

* l’étudiant était en Biologie médicale ;
* il a validé son année ;
* il doit passer dans le niveau supérieur ;
* en début d’année, il demande à poursuivre en Infirmier d’État ;
* le passage annuel détermine d’abord son nouveau niveau ;
* le transfert détermine ensuite sa nouvelle filière et sa nouvelle classe.

Le transfert ne doit pas être utilisé pour contourner le processus de passage annuel.

Le système doit distinguer :

* le niveau acquis par décision académique ;
* la filière demandée ;
* la classe de destination compatible avec ce niveau.

### Validations à prévoir

Avant validation d’un transfert interne, contrôler :

* l’école de rattachement ;
* l’annexe ;
* l’année académique ;
* le niveau actuel ;
* le niveau autorisé ;
* la filière actuelle ;
* la filière demandée ;
* la classe actuelle ;
* la classe de destination ;
* la capacité de la classe ;
* la compatibilité entre niveau, filière et classe ;
* la situation académique de l’étudiant ;
* la situation administrative ;
* la situation financière ;
* les éventuelles pièces justificatives ;
* le motif du transfert ;
* l’autorité ayant approuvé la demande.

### Historisation

La validation ne doit jamais supprimer l’ancienne inscription.

Le système doit conserver :

* l’ancienne classe ;
* l’ancienne filière ;
* la nouvelle classe ;
* la nouvelle filière ;
* la date de demande ;
* la date de validation ;
* le motif ;
* l’auteur de la demande ;
* l’agent ayant traité la demande ;
* l’autorité ayant validé ;
* les documents associés.

---

# B. Transfert sortant vers une autre école

## Définition

Le transfert sortant concerne un étudiant inscrit dans notre établissement qui souhaite poursuivre ses études dans une autre école.

Il ne suffit pas de clôturer son inscription.

Le système doit enregistrer les informations sur l’établissement de destination et préparer les documents nécessaires au départ de l’étudiant.

### Informations sur l’école de destination

Prévoir notamment :

* nom de l’établissement ;
* sigle ;
* pays ;
* ville ;
* adresse ;
* téléphone ;
* adresse électronique ;
* site Internet, si disponible ;
* filière demandée ;
* niveau demandé ;
* année académique concernée ;
* personne de contact ;
* motif du transfert.

### Documents pouvant être préparés

Selon les règles de l’établissement, le système doit pouvoir gérer ou générer :

* fiche de fréquentation ;
* attestation de scolarité ;
* relevés de notes ;
* bulletins ;
* attestation de niveau ;
* certificat de radiation ou de transfert ;
* état des unités d’enseignement validées ;
* situation financière ;
* copie du dossier administratif ;
* lettre de transmission ;
* bordereau de remise des documents.

### Processus suggéré

1. Création de la demande par le Directeur des Études.
2. Enregistrement du motif.
3. Enregistrement de l’école de destination.
4. Vérification du dossier académique.
5. Vérification du dossier administratif.
6. Vérification de la situation financière.
7. Sélection des documents à transmettre.
8. Génération ou téléversement des documents.
9. Validation par les autorités compétentes.
10. Remise des documents à l’étudiant.
11. Enregistrement de la date de remise.
12. Clôture et archivage de l’inscription.
13. Conservation complète de l’historique.

### Statuts possibles

* Brouillon
* Demande enregistrée
* Dossier en vérification
* Documents en préparation
* En attente de validation
* Validé
* Documents remis
* Transfert finalisé
* Refusé
* Annulé

---

# C. Transfert entrant depuis une autre école

## Définition

Le transfert entrant concerne un étudiant provenant d’une autre école et souhaitant poursuivre ses études dans notre établissement.

Cet étudiant ne doit pas être inscrit directement sans étude préalable de son dossier.

### Informations sur l’école d’origine

Prévoir :

* nom de l’établissement d’origine ;
* sigle ;
* pays ;
* ville ;
* adresse ;
* téléphone ;
* adresse électronique ;
* filière suivie ;
* niveau suivi ;
* dernière année académique fréquentée ;
* durée de fréquentation ;
* motif du départ.

### Documents requis

Le système doit permettre de récupérer et d’ajouter au dossier :

* fiche de fréquentation ;
* relevés de notes ;
* bulletins ;
* attestation de scolarité ;
* attestation de niveau ;
* certificat de transfert ou de radiation ;
* programme des cours suivis ;
* situation des unités d’enseignement ;
* justificatifs administratifs ;
* autres pièces exigées par l’établissement.

La fiche de fréquentation remise par l’ancienne école doit être enregistrée dans le dossier numérique de l’étudiant.

### Processus suggéré

1. Création d’un dossier de transfert entrant.
2. Identification de l’étudiant.
3. Enregistrement de l’école d’origine.
4. Téléversement des pièces reçues.
5. Vérification administrative.
6. Analyse académique du dossier.
7. Étude des équivalences.
8. Détermination du niveau admissible.
9. Détermination de la filière admissible.
10. Détermination de la classe d’affectation.
11. Décision d’acceptation, d’acceptation sous réserve ou de refus.
12. Création de la candidature ou de l’inscription.
13. Intégration dans le workflow normal d’inscription.
14. Conservation des documents d’origine dans le dossier étudiant.

### Décisions possibles

* Accepté
* Accepté sous réserve
* Pièces complémentaires requises
* Réorientation proposée
* Niveau inférieur proposé
* Refusé
* Annulé

### Point important

Le transfert entrant ne doit pas créer automatiquement un étudiant actif.

Il doit d’abord passer par :

* la vérification du dossier ;
* la décision académique ;
* l’affectation dans une filière ;
* l’affectation dans un niveau ;
* l’affectation dans une classe ;
* le workflow administratif d’inscription ;
* le workflow de paiement applicable.

---

## 4. Modélisation recommandée du module de transfert

Éviter de stocker tous les cas dans quelques champs génériques difficiles à maintenir.

Prévoir une structure claire, par exemple :

* `TransferRequest`
* `InternalTransfer`
* `IncomingTransfer`
* `OutgoingTransfer`
* `TransferSchool`
* `TransferDocument`
* `TransferDecision`
* `TransferHistory`

Une autre solution acceptable est un modèle principal avec un champ `transfer_type`, complété par des modèles spécifiques liés en `OneToOneField`.

### Types de transfert

* `INTERNAL`
* `INCOMING`
* `OUTGOING`

### Données communes

Le modèle principal peut contenir :

* étudiant ;
* type de transfert ;
* école ;
* annexe ;
* année académique ;
* statut ;
* motif ;
* date de demande ;
* demandeur ;
* agent chargé du traitement ;
* valideur ;
* date de validation ;
* décision ;
* observations ;
* date de clôture.

### Journal d’audit

Toutes les actions doivent être tracées :

* création ;
* modification ;
* ajout de document ;
* changement de statut ;
* validation ;
* refus ;
* annulation ;
* changement de classe ;
* archivage de l’inscription ;
* remise de documents.

---

## 5. Corrections attendues dans le document de livraison

Le périmètre actuel ne doit plus indiquer que la section du Directeur des Études regroupe le suivi mensuel de la caisse, des salaires, des honoraires et des dépenses.

La formulation correcte doit être :

### Salaire

Le Directeur des Études dispose d’un espace personnel lui permettant de consulter l’état de préparation et de paiement de son propre salaire, son historique mensuel et ses documents de paie.

### Communication interne

Le Directeur des Études dispose d’un accès au système central de communication interne. Ce système doit être réutilisable dans tous les dashboards et permettre une communication individuelle ou groupée selon les rôles, classes, filières, écoles et annexes autorisées.

### Transferts

Le module de transferts est une section métier indépendante couvrant les transferts internes, entrants et sortants. Chaque cas doit disposer de son propre workflow, de ses documents, de ses contrôles, de ses statuts et de son historique.

---

## 6. Résultat attendu avant validation

La livraison ne pourra être considérée comme métierement finalisée que lorsque :

* le Directeur des Études n’aura plus accès à la gestion globale des finances ;
* la section salaire sera limitée à ses propres paiements ;
* la gestion complète des salaires sera réservée à la gestionnaire ;
* la messagerie sera transformée en composant global réutilisable ;
* la sélection des destinataires sera suffisamment avancée ;
* les permissions de communication seront contrôlées ;
* les transferts internes, entrants et sortants seront clairement distingués ;
* les changements de niveau seront séparés des transferts de filière ou de classe ;
* les documents de transfert seront gérés ;
* toutes les anciennes inscriptions resteront historisées ;
* les décisions et actions seront auditables ;
* les tests couvriront chaque scénario métier critique.

Avant toute nouvelle implémentation importante, commencer par analyser les modèles, vues, services et composants déjà créés afin de réutiliser l’existant sans provoquer de duplication ni casser les workflows d’inscription, de passage annuel ou de paiement.
