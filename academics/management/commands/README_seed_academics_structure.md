# Seed Academics Structure

Cette commande initialise la structure academique de base a partir des inscriptions existantes, sans changer l'architecture.

## Commande

```powershell
python manage.py seed_academics_structure
```

## Option de nettoyage (facultative)

```powershell
python manage.py seed_academics_structure --strict-clean-ecs
```

Utiliser `--strict-clean-ecs` uniquement si des EC hors blueprint ont ete ajoutes par d'anciens seeds et que vous voulez revenir a une structure stricte.

## Ce qui est cree/mis a jour

- `AcademicYear` (depuis `candidature.academic_year`)
- `AcademicClass` (programme + annexe + annee + niveau)
- `Semester` (S1, S2)
- `UE` et `EC` (blueprint academique commun)
- `AcademicEnrollment` (liaison des inscriptions vers classes)
- Referentiels `Language` et `Profession`

## Notes

- Idempotent: relance possible sans duplication.
- Fallback niveau: si `entry_year` est non standard, la commande utilise la table legacy (`L1/L2/L3/M1/M2`) pour ne pas bloquer le provisioning.
- Cette commande n'invente pas de nouvelle architecture et reutilise les modeles existants.
