# Raffinement DE - Enseignants et Documents

## Périmètre

Cette vague retravaille les sections **Enseignants** et **Documents** du dashboard du Directeur des études. La section Emploi du temps n'a pas été modifiée.

## Enseignants

- cinq sous-vues HTMX : vue d'ensemble, répertoire, affectations, dossiers et transferts ;
- compteurs de pilotage : enseignants actifs, affectés, non affectés et pièces à vérifier ;
- recherche par nom, email, code ou spécialité et filtres opérationnels ;
- création d'un enseignant avec affectation initiale facultative ;
- chargement dynamique des matières selon la classe ;
- ajout et modification d'une affectation avec salle, volume horaire et dates ;
- dépôt de pièces limité aux formats autorisés et à 10 Mo ;
- consultation et validation des pièces dans une modale large ;
- accès rapide au profil, au contrat, aux affectations et au dossier.

Tous les querysets et toutes les mutations restent strictement limités à l'annexe du Directeur des études.

## Documents

- trois sous-vues HTMX : vue d'ensemble, rédaction et archives ;
- indicateurs total, brouillons et documents publiés ;
- formulaire Django conservant les valeurs et affichant les erreurs au niveau des champs ;
- reprise d'un brouillon existant, publication et export PDF ;
- recherche et filtres par type et statut ;
- pagination des archives ;
- refus de toute lecture ou mutation inter-annexes.

## Interface

- composants UI Core pour les en-têtes, onglets, statistiques, alertes et états vides ;
- modale large de 896 px sur desktop pour les formulaires riches ;
- adaptation à 334 px sur un écran mobile de 390 px ;
- listes sans cartes imbriquées, commandes compactes avec icônes et info-bulles ;
- retours HTMX ciblés : aucune reconstruction complète du dashboard après les actions principales.

## Vérifications

- `python manage.py test --keepdb --settings=config.settings_test_local portal` : **83/83 réussis** ;
- `python manage.py test --keepdb --settings=config.settings_test_local ui` : **110/110 réussis** ;
- suite ciblée `portal.test_director_teacher_document_refinement` : **6/6 réussis** ;
- trois tests historiques de création/affectation enseignant : réussis ;
- `python manage.py check --settings=config.settings_test_local` : aucun problème ;
- `python manage.py makemigrations --check --dry-run --settings=config.settings_test_local` : aucun changement ;
- `npm run build:css` : réussi.

Le contrôle Playwright est archivé dans `_audit/director_teachers_documents_refinement/`. Il valide les navigations HTMX, les erreurs de formulaire, la création d'un enseignant, l'affectation, le brouillon, la publication, les largeurs desktop/mobile, l'absence de débordement horizontal et l'absence d'erreur JavaScript.

La régression complète `accounts` compte actuellement 6 échecs sur 248 tests dans des zones hors de cette vague : gestionnaire, progression étudiant, profil/préférences et une action Programme. Les scénarios Enseignants et Documents concernés par ce travail sont verts.
