# Backlog - Gestion des cas de surveillance

Objectif: créer plus tard un module léger de suivi des cas pour le surveillant général.

## Cas à gérer

- Absences répétées d'un étudiant.
- Retards fréquents.
- Absence longue justifiée ou non justifiée.
- Signalement comportemental.
- Convocation étudiant.
- Convocation parent ou tuteur.
- Suivi pédagogique demandé.
- Étudiant absent à une évaluation.
- Enseignant absent sur plusieurs cours.
- Plusieurs signalements sur le même étudiant.

## Statuts proposés

- Nouveau
- En cours
- En attente parent
- En observation
- Résolu
- Escaladé direction

## Priorités proposées

- Faible
- Normale
- Urgente
- Critique

## Actions dans un cas

- Ajouter une note interne.
- Joindre un justificatif.
- Convoquer l'étudiant.
- Convoquer le parent ou tuteur.
- Marquer comme justifié.
- Planifier un rappel.
- Escalader à la direction.

## Modèles envisagés

- StudentCase
- StudentCaseNote

## MVP proposé

- Créer un cas depuis le drawer étudiant.
- Afficher les cas ouverts dans le drawer étudiant.
- Ajouter une section "Cas à traiter" dans le dashboard surveillant.
- Changer le statut d'un cas.
- Ajouter des notes internes.
- Créer automatiquement un cas depuis les alertes d'assiduité répétées.
