# Bootstrap institutionnel

`institution.json` est volontairement vide tant que les référentiels officiels
ne sont pas fournis. Il ne contient aucune donnée de démonstration.

Chaque entrée future de `objects` suit cette forme :

```json
{
  "id": "annexe.bamako",
  "model": "branches.Branch",
  "lookup": {"code": "BKO"},
  "fields": {"name": "..."}
}
```

Les modèles autorisés appartiennent à `core`, `branches`, `formations` ou
`academics`. Une relation vers un objet déjà créé peut utiliser :

```json
{"$ref": "annexe.bamako"}
```

Le manifeste est appliqué par upsert, dans une transaction :

```powershell
python manage.py bootstrap_institution --dry-run
python manage.py bootstrap_institution
```

Avant une reconstruction locale, exécuter dans cet ordre : backup PostgreSQL,
`reset_business_data`, puis `bootstrap_institution`.
