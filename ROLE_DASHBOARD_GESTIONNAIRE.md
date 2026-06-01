# Role et fonctionnement du dashboard Gestionnaire

Date d'analyse : 2026-05-28

## Resume clair

Le dashboard Gestionnaire est le poste de pilotage operationnel d'une annexe. Il sert a suivre et traiter toute la chaine locale : candidatures, inscriptions, paiements, caisse, salaires, depenses, rapports financiers et boutique.

Concretement, la gestionnaire n'est pas seulement en consultation. Elle peut agir sur les dossiers et sur les flux financiers de son annexe. Le dashboard centralise donc les operations quotidiennes qui transforment un candidat en inscrit, encaissent l'argent, enregistrent les sorties de caisse, paient les charges et donnent une lecture de la situation financiere.

## Acces et perimetre

L'acces est reserve aux utilisateurs du groupe `gestionnaire`.

La gestionnaire doit etre rattachee a une annexe. Si elle n'a pas d'annexe, l'acces est bloque. Les donnees chargees sont filtrees sur son annexe : candidatures de l'annexe, inscriptions de l'annexe, paiements de l'annexe, personnel de l'annexe, caisse de l'annexe, depenses de l'annexe.

La resolution de l'annexe passe par la couche d'acces centrale, avec priorite au profil utilisateur, au PaymentAgent, puis au rattachement manager d'une branche.

## A quoi sert le dashboard

Le dashboard sert a quatre choses principales.

1. Piloter le parcours etudiant

La gestionnaire voit les candidatures, les dossiers en attente, les dossiers acceptes, les dossiers a completer et les dossiers rejetes. Elle peut ouvrir le detail d'une candidature, verifier les informations et documents, puis prendre une decision.

Une candidature acceptee peut ensuite etre transformee en inscription. Le dashboard demande alors un positionnement academique : niveau, classe, frais correspondants. L'inscription creee devient payable.

2. Piloter l'encaissement

La gestionnaire suit les paiements de l'annexe : paiements valides, en attente, annules, montants du jour, de la semaine et du mois.

Elle peut valider un paiement en attente, l'annuler, corriger le montant d'un paiement valide avec justification, ou creer une session de paiement espece pour une inscription payable. Quand un paiement est valide, le systeme cree ou synchronise un mouvement de caisse entrant pour eviter que l'encaissement reste hors journal.

3. Piloter l'exploitation de l'annexe

Le dashboard gere les depenses locales : creation, approbation, rejet et paiement. Une depense payee genere une sortie de caisse.

Il gere aussi les salaires : preparation des fiches de paie, modification d'une fiche, avances, notification de disponibilite, paiement partiel ou total selon la caisse disponible. Chaque paiement de salaire genere une sortie de caisse.

La boutique est aussi branchee au dashboard : produits, stock, commandes, ventes et impact financier.

4. Lire la situation financiere

La gestionnaire dispose d'une vue caisse et rapport. Elle voit les entrees, sorties, recettes etudiantes, ventes boutique, depenses payees, salaires payes, solde net, solde estime et gain reel de l'annexe sur une periode.

Le dashboard calcule aussi des alertes et priorites : paiements valides non synchronises en caisse, paies manquantes, salaires restants, depenses approuvees a payer, inscriptions en attente de paiement, caisse insuffisante pour couvrir les engagements.

## Sections du dashboard

### Vue d'ensemble

Cette section resume la situation de l'annexe : candidatures en attente, inscriptions, paiements, encaissements du jour, recettes du mois, charges, caisse estimee, engagements et alertes.

Elle sert a savoir rapidement ce qui demande une action.

### Candidatures

Actions disponibles :

- voir le detail d'une candidature ;
- accepter une candidature ;
- rejeter une candidature avec motif ;
- renvoyer une candidature a completer avec message ;
- ouvrir le positionnement academique apres acceptation.

Impact metier : c'est la porte d'entree du dossier. Une candidature acceptee peut avancer vers l'inscription.

### Inscriptions

Actions disponibles :

- voir le detail d'une inscription ;
- suivre le statut administratif et financier ;
- creer une inscription depuis une candidature acceptee ;
- associer la classe et le niveau academique ;
- calculer les frais selon le niveau positionne ;
- voir si l'inscription est payable ou deja soldee.

Impact metier : la gestionnaire transforme un dossier accepte en dossier administratif payable.

### Paiements

Actions disponibles :

- voir le detail d'un paiement ;
- valider un paiement en attente ;
- annuler un paiement en attente ;
- corriger un paiement valide avec confirmation `CORRIGER` et justification ;
- creer une session espece avec code ;
- regenerer, completer ou annuler une session espece.

Impact metier : les paiements valides alimentent l'etat financier de l'inscription et le journal de caisse.

### Salaires

Actions disponibles :

- voir le detail de paie d'un employe ;
- creer ou modifier une fiche de paie ;
- preparer automatiquement les fiches manquantes du mois ;
- declarer les fiches pretes et notifier les employes ;
- enregistrer une avance ;
- payer une fiche partiellement ou totalement ;
- refuser le paiement si la caisse disponible est insuffisante.

Impact metier : le dashboard gere la paie du personnel de l'annexe et trace les sorties de caisse liees aux salaires.

### Depenses

Actions disponibles :

- creer une depense ;
- ajouter un fournisseur, une categorie, un montant, une date et un justificatif ;
- approuver une depense ;
- rejeter une depense ;
- payer une depense approuvee ;
- generer la reference comptable.

Impact metier : toute depense payee devient une sortie de caisse tracee.

### Caisse

Actions disponibles :

- consulter toutes les entrees et sorties ;
- filtrer par type, source ou recherche ;
- creer un mouvement manuel ;
- synchroniser les paiements etudiants valides absents du journal ;
- generer et telecharger une piece de caisse PDF.

Sources de mouvements :

- paiement etudiant ;
- salaire ;
- depense ;
- boutique ;
- ajustement caisse ;
- saisie manuelle.

Impact metier : c'est le journal financier local de l'annexe.

### Rapport

La section rapport donne une lecture financiere par periode et par annee.

Elle calcule notamment :

- total entrees ;
- total sorties ;
- paiements scolaires ;
- ventes boutique ;
- depenses ;
- salaires ;
- autres charges ;
- autres entrees ;
- solde net ;
- gain reel annexe ;
- recettes annuelles et evolution par rapport a l'annee precedente.

Impact metier : elle permet de comprendre combien l'annexe genere, combien elle depense, et ce qu'il reste apres charges.

### Boutique

La boutique permet de gerer les articles vendus par l'annexe, le stock, les commandes, les ventes et la remise des commandes.

Impact metier : les ventes boutique participent aux recettes de l'annexe et doivent etre suivies avec le stock et la caisse.

## Ce que la gestionnaire fait concretement

Au quotidien, elle peut :

- traiter les candidatures de son annexe ;
- demander des complements sur un dossier ;
- accepter ou rejeter une candidature ;
- creer une inscription a partir d'une candidature acceptee ;
- suivre les inscriptions actives, partielles ou en attente de paiement ;
- encaisser ou valider des paiements ;
- corriger un paiement deja valide avec tracabilite ;
- generer des codes de paiement espece ;
- suivre les recettes du jour, de la semaine et du mois ;
- creer et payer des depenses ;
- preparer, notifier et payer les salaires ;
- enregistrer des avances sur salaire ;
- suivre la caisse disponible ;
- synchroniser les paiements avec la caisse ;
- produire des pieces de caisse ;
- suivre les ventes boutique et le stock ;
- lire un rapport financier de l'annexe.

## Garde-fous et tracabilite

Le dashboard contient plusieurs garde-fous :

- acces limite au groupe `gestionnaire` ;
- annexe obligatoire ;
- filtrage systematique par annexe ;
- validation des montants avant paiement ;
- blocage si le paiement depasse le solde d'une inscription ;
- blocage si la caisse ne couvre pas un salaire ou une avance ;
- correction de paiement valide seulement avec confirmation explicite ;
- logs financiers pour les validations, annulations et corrections ;
- references comptables automatiques ;
- mouvements de caisse crees automatiquement pour les paiements, salaires et depenses ;
- pieces de caisse PDF possibles pour les mouvements sensibles.

## Limites actuelles reperees

Le fichier historique `dash_gestionnaire_suivi.txt` indique que le dashboard etait deja avance, mais mentionnait encore des pistes d'evolution :

- cloture mensuelle ou cloture par periode ;
- exports comptables plus propres ;
- workflow salaire enseignant plus specifique si necessaire ;
- enrichissement boutique avec variantes et stock plus fin.

Dans le code actuel, une section `rapport` existe deja et donne un bilan de periode plus clair. Les exports comptables et la cloture formelle restent a confirmer ou a completer selon le besoin metier.

## Fichiers sources principaux

- `accounts/dashboards/manager_dashboard.py` : construit tout le contexte du dashboard, les statistiques, les sections, les filtres et les indicateurs.
- `accounts/dashboards/htmx_manager.py` : contient les actions concretes de la gestionnaire : candidatures, inscriptions, paiements, salaires, depenses, caisse.
- `accounts/dashboards/helpers.py` : verifie le groupe gestionnaire et recupere l'annexe utilisateur.
- `accounts/models.py` : definit les fiches de paie, depenses d'annexe, mouvements de caisse et sequences comptables.
- `accounts/services/manager_intelligence.py` : calcule les alertes, priorites, solde caisse, synchronisation paiements et logique de paie.
- `accounts/templates/accounts/dashboard/manager_dashboard.html` : interface visible du dashboard et sections.
- `accounts/urls.py` : routes `manager/` et `htmx/manager/...`.
- `dash_gestionnaire_suivi.txt` : ancien memo de suivi du dashboard gestionnaire.

## Conclusion

Le dashboard Gestionnaire est le centre de controle local d'une annexe. Son role est de faire avancer les dossiers etudiants et de tenir la realite financiere de l'annexe a jour : admissions, inscriptions, encaissements, caisse, salaires, depenses, boutique et rapports.

Il est donc a la fois un dashboard operationnel, un outil de caisse, un outil RH de base pour les salaires, et un outil de controle financier local.
