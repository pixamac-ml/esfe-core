# Raffinement DE - Emploi du temps

## Objectif

La section **Emploi du temps** du Directeur des études a été reconstruite autour du parcours quotidien le plus court : choisir une classe, placer les cours dans une grille hebdomadaire, contrôler le rendu puis imprimer.

## Nouvelle organisation

Trois sous-vues HTMX sont disponibles sans rechargement complet du dashboard :

- **Vue d'ensemble** : état des classes, nombre de grilles prêtes et accès direct à chaque classe ;
- **Construire** : sélection de la classe puis édition directe de la grille du lundi au samedi ;
- **Aperçu et impression** : contrôle en lecture seule et ouverture de la version A4.

La classe sélectionnée reste conservée lors du passage de la construction à l'aperçu.

## Construction de la grille

- quatre créneaux usuels sont proposés immédiatement sur une classe vide ;
- navigation semaine précédente, semaine actuelle et semaine suivante sans perdre la classe sélectionnée ;
- dates du lundi au samedi visibles dans la grille et transmises à l'impression ;
- chaque cellule libre ouvre le drawer avec le jour et les horaires préremplis ;
- un cours existant peut être modifié ou retiré depuis sa cellule ;
- le formulaire conserve les valeurs invalides et place les erreurs sous les champs concernés ;
- les matières sont limitées à la maquette active de la classe ;
- les enseignants sont limités aux comptes actifs de l'annexe du DE ;
- les conflits de classe, d'enseignant et de salle restent contrôlés par le service académique canonique ;
- la salle est visible dans la grille et signalée lorsqu'elle manque ;
- l'action **Actualiser les 4 prochaines semaines** matérialise la grille récurrente dans les agendas datés.

## Impression

La version imprimable utilise directement la grille hebdomadaire officielle. Elle ne dépend donc pas d'une génération préalable des cours datés.

- format `A4 landscape` ;
- en-tête ESFE, annexe, classe, programme et année académique ;
- tableau lundi-samedi avec horaires, matières, enseignants et salles ;
- couleurs et bordures conservées à l'impression ;
- commandes d'impression masquées sur le papier ;
- rendu adapté à l'affichage sur le tableau de l'école.

## Sécurité métier

Les classes, matières, enseignants, créneaux, mutations et impressions sont tous vérifiés avec l'annexe du Directeur des études. Une classe ou une ressource d'une autre annexe n'est ni proposée ni modifiable, et son impression est refusée.

## Vérifications

- suite ciblée `portal.test_director_timetable_refinement` : **6/6 réussis** ;
- suite complète `portal` : **89/89 réussis** ;
- sélection de régression DE + UI : **172/172 réussis** ;
- `python manage.py check --settings=config.settings_test_local` : aucun problème ;
- `python manage.py makemigrations --check --dry-run --settings=config.settings_test_local` : aucun changement ;
- `npm run build:css` : réussi.

Le contrôle Playwright est archivé dans `_audit/director_timetable_refinement/`. Il valide la navigation HTMX, le passage à la semaine suivante puis le retour à la précédente, la conservation de la classe, le formulaire invalide, la création d'un cours, l'aperçu, l'impression A4, le drawer large à **896 px** sur desktop, son adaptation à **366 px** sur mobile, l'absence de débordement global et l'absence d'erreur JavaScript.
