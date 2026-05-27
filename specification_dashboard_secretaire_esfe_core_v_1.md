# SPÉCIFICATION MÉTIER ET TECHNIQUE
# DASHBOARD SECRÉTAIRE — ESFE CORE V1

---

# OBJECTIF DU DOCUMENT

Ce document définit précisément la logique métier, les workflows, les règles fonctionnelles, l’architecture UX/UI et les comportements intelligents attendus pour le dashboard secrétaire dans ESFE Core.

Le but n’est PAS de construire un simple dashboard CRUD.

Le but est de construire un véritable :

# SYSTÈME D’ACCUEIL ADMINISTRATIF INTELLIGENT

Le dashboard secrétaire doit devenir le point central de circulation des flux humains, administratifs et informationnels de chaque annexe.

La secrétaire n’est pas une administratrice technique.
Elle est :

- le point d’accueil ;
- le point d’orientation ;
- le point de traçabilité ;
- le point de déclenchement des workflows ;
- le point de communication interne ;
- le centre de circulation administrative.

---

# PHILOSOPHIE MÉTIER DU DASHBOARD

Le dashboard secrétaire ne doit jamais fonctionner comme un simple formulaire administratif.

Chaque action doit être :

- intelligente ;
- contextuelle ;
- orientée métier ;
- liée à une finalité ;
- connectée à un workflow.

Le système doit comprendre :

- pourquoi une personne est venue ;
- pour qui ;
- vers quel service ;
- quelle action doit être déclenchée ;
- quelles notifications envoyer ;
- quels documents préparer ;
- quel historique conserver ;
- quelles informations afficher.

Le système doit réduire les clics inutiles.

Le système doit anticiper les actions.

Le système doit fluidifier le travail administratif.

---

# LE VRAI CŒUR DU DASHBOARD

Le vrai cœur du dashboard secrétaire est :

# LE REGISTRE ADMINISTRATIF INTELLIGENT

Le registre n’est PAS un simple cahier numérique.

Le registre devient :

# LE MOTEUR CENTRAL DES ÉVÉNEMENTS ADMINISTRATIFS.

Toutes les interactions humaines passent par le registre.

---

# TYPES D’ÉVÉNEMENTS GÉRÉS PAR LE REGISTRE

Le registre doit permettre de gérer plusieurs types d’événements.

Chaque type possède :

- ses propres champs ;
- ses propres règles ;
- ses propres workflows ;
- ses propres notifications ;
- ses propres actions.

---

# TYPES PRINCIPAUX

## 1. Visite parent

Exemples :
- voir un enfant ;
- discuter ;
- urgence ;
- échange ;
- accompagnement.

---

## 2. Paiement scolarité

Exemples :
- paiement inscription ;
- paiement tranche ;
- paiement reliquat ;
- paiement frais administratifs.

---

## 3. Dépôt colis

Exemples :
- nourriture ;
- documents ;
- effets personnels ;
- matériels.

---

## 4. Livraison école

Exemples :
- matériels ;
- fournitures ;
- équipements ;
- ordinateurs ;
- documents officiels.

---

## 5. Demande rendez-vous

Exemples :
- DG ;
- directeur des études ;
- gestionnaire ;
- enseignant ;
- administration.

---

## 6. Retrait diplôme

Exemples :
- diplôme ;
- attestation ;
- relevé ;
- certificat.

---

## 7. Réclamation

Exemples :
- erreur note ;
- problème paiement ;
- problème administratif ;
- dossier perdu.

---

## 8. Visiteur externe

Exemples :
- entreprise ;
- prestataire ;
- partenaire ;
- fournisseur.

---

# STRUCTURE DU REGISTRE

Chaque entrée registre doit posséder :

- numéro automatique ;
- date ;
- heure ;
- annexe ;
- secrétaire responsable ;
- type événement ;
- statut ;
- priorité ;
- nom visiteur ;
- téléphone ;
- email ;
- étudiant concerné ;
- personnel concerné ;
- classe ;
- motif ;
- description ;
- actions liées ;
- pièces jointes ;
- historique ;
- heure sortie ;
- clôture.

---

# NUMÉROTATION AUTOMATIQUE

Le système doit générer automatiquement :

- numéro registre ;
- numéro journée ;
- numéro annexe ;
- identifiant événement.

Format recommandé :

ESFE-ANNEXE-DATE-NUMERO

Exemple :

ESFE-BKO-2026-000245

---

# ÉTATS DU REGISTRE

Chaque entrée doit posséder un état intelligent.

États possibles :

- en attente ;
- en cours ;
- transféré ;
- traité ;
- clôturé ;
- annulé ;
- archivé.

---

# ÉVÉNEMENTS INTELLIGENTS

Le système doit adapter automatiquement son comportement selon le type d’événement.

---

# CAS MÉTIER — PAIEMENT SCOLARITÉ

## Workflow

### Étape 1
Parent arrive.

### Étape 2
Secrétaire crée entrée registre.

### Étape 3
Type = paiement scolarité.

### Étape 4
Système comprend automatiquement :

- cible = gestionnaire ;
- priorité = immédiate ;
- workflow = financier.

### Étape 5
Notification envoyée à la gestionnaire.

### Étape 6
Notification contient :

- nom étudiant ;
- classe ;
- parent ;
- annexe.

### Étape 7
Gestionnaire clique.

### Étape 8
Ouverture automatique du dossier financier étudiant.

### Étape 9
Workflow paiement prêt.

### Étape 10
Paiement effectué.

### Étape 11
Reçu imprimé.

### Étape 12
Historique enregistré.

---

# CAS MÉTIER — DÉPÔT COLIS

## Workflow

### Étape 1
Parent arrive.

### Étape 2
Type = dépôt colis.

### Étape 3
Recherche étudiant.

### Étape 4
Association colis ↔ étudiant.

### Étape 5
Nature colis.

### Étape 6
Statut dépôt.

### Étape 7
Notification étudiant/surveillant.

### Étape 8
Suivi remise.

### Étape 9
Confirmation remise.

### Étape 10
Clôture.

---

# CAS MÉTIER — DEMANDE RENDEZ-VOUS DG

## Workflow

### Étape 1
Entreprise arrive.

### Étape 2
Entrée registre.

### Étape 3
Type = demande rendez-vous.

### Étape 4
Collecte informations.

### Étape 5
Consultation agenda DG.

### Étape 6
Validation créneau.

### Étape 7
Création rendez-vous.

### Étape 8
Envoi notification.

### Étape 9
Envoi email.

### Étape 10
Confirmation téléphonique.

### Étape 11
Historique.

---

# CAS MÉTIER — RETRAIT DIPLÔME

## Workflow

### Étape 1
Étudiant arrive.

### Étape 2
Entrée registre.

### Étape 3
Type = retrait diplôme.

### Étape 4
Vérification identité.

### Étape 5
Vérification disponibilité diplôme.

### Étape 6
Impression formulaire.

### Étape 7
Signature.

### Étape 8
Scan document.

### Étape 9
Archivage.

### Étape 10
Historique retrait.

---

# NOTION DE ROUTAGE ADMINISTRATIF

Chaque entrée doit automatiquement être routée vers le bon service.

---

# EXEMPLES DE ROUTAGE

## Paiement
→ Gestionnaire

## Rendez-vous DG
→ DG / secrétariat direction

## Retrait diplôme
→ Direction études

## Problème discipline
→ Surveillant

## Réclamation administrative
→ Administration

## Livraison matériel
→ Gestionnaire / logistique

---

# FICHE ÉTUDIANT

La fiche étudiant est une pièce centrale du dashboard secrétaire.

La fiche étudiant NE DOIT PAS être une modal.

Elle doit être :

# UN DRIVER / DRAWER LATÉRAL LARGE.

Pourquoi :

- beaucoup d’informations ;
- besoin de concentration ;
- besoin de navigation ;
- consultation rapide.

---

# CONTENU FICHE ÉTUDIANT

## Informations principales

- photo ;
- nom ;
- prénom ;
- matricule ;
- formation ;
- cycle ;
- classe ;
- annexe ;
- année académique ;
- téléphone ;
- email ;
- parent.

---

## Situation académique

- statut ;
- présence ;
- emploi du temps ;
- examens ;
- documents.

---

## Situation financière

- frais ;
- paiements ;
- reste ;
- historique.

---

## Historique administratif

- visites ;
- rendez-vous ;
- dépôts ;
- retraits ;
- réclamations.

---

# MODALS VS DRIVERS

---

# MODALS

Utilisation :

- création rapide ;
- confirmation ;
- validation ;
- actions courtes.

Exemples :

- nouvelle entrée ;
- notification ;
- rendez-vous ;
- dépôt rapide.

---

# DRIVERS

Utilisation :

- consultation profonde ;
- dossier ;
- historique ;
- fiche étudiant ;
- workflow complexe.

---

# DASHBOARD TEMPS RÉEL

Le dashboard doit afficher :

- visiteurs du jour ;
- rendez-vous du jour ;
- paiements attendus ;
- dépôts colis ;
- tâches urgentes ;
- notifications.

---

# BARRE ACTIONS RAPIDES

Actions :

- nouvelle entrée ;
- nouveau rendez-vous ;
- recherche étudiant ;
- nouveau dépôt ;
- impression registre ;
- voir agenda.

---

# RECHERCHE ÉTUDIANT

Recherche HTMX temps réel.

Recherche par :

- nom ;
- prénom ;
- matricule ;
- téléphone ;
- email.

---

# IMPRESSION JOURNALIÈRE

Fonction critique.

Chaque fin de journée :

- génération rapport ;
- PDF ;
- impression ;
- archivage.

---

# CONTENU RAPPORT JOURNALIER

Colonnes :

- N° ;
- heure ;
- type ;
- visiteur ;
- étudiant ;
- service ;
- motif ;
- action ;
- statut ;
- heure sortie.

---

# EXPORTS

Le système doit permettre :

- PDF ;
- Excel ;
- impression directe.

---

# ARCHIVAGE

Le système doit archiver automatiquement :

- rapports ;
- entrées ;
- historiques ;
- pièces jointes ;
- scans.

---

# MODE DÉGRADÉ

Le système doit prévoir :

- panne réseau ;
- panne courant ;
- interruption serveur.

La secrétaire doit pouvoir continuer manuellement.

Puis :

- resynchronisation ;
- saisie différée.

---

# ACCÈS ET PERMISSIONS

La secrétaire doit pouvoir :

- consulter ;
- rechercher ;
- orienter ;
- créer événements ;
- créer rendez-vous ;
- notifier ;
- consulter agendas.

---

# LA SECRÉTAIRE NE DOIT PAS

- modifier structure académique ;
- modifier paiements validés ;
- gérer notes ;
- administrer système ;
- modifier données critiques.

---

# MODULES À RETIRER

À retirer du dashboard secrétaire :

- boutique ;
- graphiques inutiles ;
- analytics lourds ;
- gestion académique avancée ;
- administration technique ;
- UE/EC ;
- dashboards complexes.

---

# MODULES À CONSERVER

Modules conservés :

- registre ;
- visiteurs ;
- rendez-vous ;
- recherche étudiant ;
- dépôts ;
- tâches simples ;
- notifications ;
- historique.

---

# TÂCHES SIMPLES

Le système tâches doit rester léger.

Pas de système complexe type Jira.

---

# CONTENU TÂCHES

- titre ;
- priorité ;
- date ;
- statut ;
- responsable.

---

# NOTIFICATIONS

Les notifications seront traitées dans une phase dédiée.

Mais le dashboard doit déjà être pensé pour :

- recevoir ;
- envoyer ;
- router.

---

# PROFIL ET PARAMÈTRES

La secrétaire doit posséder :

- profil ;
- photo ;
- informations personnelles ;
- historique ;
- salaire ;
- situation RH ;
- notifications.

---

# DESIGN UI/UX

Le design doit être :

- propre ;
- moderne ;
- professionnel ;
- rapide ;
- responsive ;
- orienté productivité.

---

# TECHNOLOGIES FRONTEND

Utiliser :

- HTMX ;
- Alpine.js ;
- Tailwind ;
- Django Components.

---

# TECHNOLOGIES À ÉVITER

Éviter :

- lourdeurs JS inutiles ;
- graphiques inutiles ;
- animations excessives.

---

# TABLEAUX

Les tableaux doivent :

- être lisibles ;
- être filtrables ;
- être paginés ;
- supporter recherche ;
- supporter export.

---

# STRUCTURE SIDEBAR RECOMMANDÉE

## Accueil
- dashboard

## Registre administratif
- entrées
- visiteurs
- dépôts
- livraisons

## Rendez-vous
- agenda
- demandes
- historique

## Étudiants
- recherche
- fiches

## Organisation
- tâches
- rapports

## Communication
- notifications
- messages internes

## Profil
- paramètres
- informations RH

---

# OBJECTIF FINAL

Le dashboard secrétaire doit devenir :

# UN CENTRE D’ACCUEIL ADMINISTRATIF INTELLIGENT, FLUIDE ET PROFESSIONNEL.

Le système doit :

- réduire les pertes de temps ;
- réduire les erreurs ;
- réduire les oublis ;
- améliorer la traçabilité ;
- améliorer la communication ;
- fluidifier les workflows.

---

# CONCLUSION

Le dashboard secrétaire n’est pas un simple dashboard.

C’est :

# LE CŒUR HUMAIN ET OPÉRATIONNEL DE L’ANNEXE.

Toutes les interactions doivent être pensées :

- métier ;
- terrain ;
- humain ;
- intelligent ;
- contextuel ;
- fluide.

Ce document doit servir de référence principale pour la conception, l’architecture et l’implémentation du dashboard secrétaire ESFE Core V1.

