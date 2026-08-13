# Raffinement Directeur des études — Programmes et classes

## Périmètre livré

La section `Programmes et classes` reprend désormais le même contrat visuel et HTMX que les sections d'évaluations déjà raffinées. Le shell, la barre supérieure et la navigation latérale n'ont pas été modifiés.

Trois sous-fenêtres séparent les usages :

- `Vue d'ensemble` : indicateurs de structure et accès directs ;
- `Classes` : recherche, filtres, pagination, création et modification ;
- `Maquettes pédagogiques` : lecture par classe des semestres, UE, EC et crédits.

## Architecture

- `portal/services/director/programme_service.py` construit un contexte exclusivement limité à l'annexe du Directeur des études.
- `portal/forms.py` porte les formulaires de classe, semestre, UE et EC avec des querysets bornés à la classe et à l'annexe lorsque nécessaire.
- `director_programme_subcontent` sert les trois fragments sans recharger le dashboard complet.
- `director_programme_class_modal` gère la création et la modification d'une classe dans le modal large.
- `director_programme_action` réutilise les services métier existants pour enregistrer classes, semestres, UE et EC, et pour archiver les EC.

## Corrections métier

- Une classe créée par le Directeur est toujours rattachée à son annexe ; ses semestres 1 et 2 sont préparés automatiquement.
- Les formulaires n'exposent plus les semestres 3 et 4, absents de `Semester.SEMESTER_CHOICES`.
- Le champ `total_required_credits` de l'ancien formulaire, qui n'était pas enregistré, a été retiré.
- Les UE, EC et classes d'une autre annexe ne peuvent être sélectionnés ni modifiés.
- La suppression visuelle d'un EC correspond à un archivage et respecte les contrôles d'utilisation existants.
- Les UE et EC archivés sont exclus des indicateurs et de la maquette active.

## Interface

- Les listes et filtres restent dans la zone centrale pour faciliter le balayage et la comparaison.
- Le modal large est réservé au formulaire de classe.
- Le drawer `wide` est réservé à la maquette complète et mesure 896 px sur un viewport desktop de 1440 px.
- Sur mobile, le drawer se replie à 366 px pour un viewport de 390 px, sans débordement horizontal.
- Les erreurs de formulaire conservent les valeurs saisies ; les succès actualisent la sous-fenêtre active par événement HTMX.

## Vérifications

- `python manage.py check --settings=config.settings_test_local`
- `python manage.py makemigrations --check --dry-run --settings=config.settings_test_local`
- `python manage.py test --settings=config.settings_test_local portal --noinput --keepdb` : 77 tests réussis.
- `python manage.py test --settings=config.settings_test_local ui --noinput --keepdb` : 110 tests réussis.
- Audit Playwright : navigation HTMX, erreurs et succès des formulaires, création de classe, ajout d'EC, drawer desktop/mobile, responsive 1440/820/390 px.
- Audit navigateur : aucune erreur console, aucune erreur de page et aucun débordement horizontal.

Les captures et le résultat structuré sont conservés dans `_audit/director_programmes_refinement/`.
