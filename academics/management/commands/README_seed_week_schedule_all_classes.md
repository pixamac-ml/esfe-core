# Seed Week Schedule (All Classes)

Genere une semaine de cours pour chaque classe academique active.

## Commande rapide

```powershell
python manage.py seed_week_schedule_all_classes
```

## Options

```powershell
python manage.py seed_week_schedule_all_classes --week-start 2026-05-11 --days 5
```

- `--week-start`: date de reference (YYYY-MM-DD), normalisee au lundi.
- `--days`: nombre de jours de cours (1 a 6).

## Comportement

- Idempotent: met a jour les evenements seed existants, cree les manquants.
- Evite les conflits: ignore les slots deja occupes pour la classe.
- Cree automatiquement jusqu'a 3 enseignants seed par annexe si necessaire.

