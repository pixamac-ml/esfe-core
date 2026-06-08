# Résumé — Correctifs Bloquants Production (Secrétariat)

## Bloqueur 1 : Vues d'édition (5 modèles)

### services.py
- `update_appointment()` — met à jour un rendez-vous avec vérification des conflits
- `update_visitor()` — met à jour un visiteur
- `update_document()` — met à jour un document
- `update_task()` — met à jour une tâche

### views.py
- `registry_update` — formulaire pré-rempli avec instance, routage ré-appliqué
- `appointment_update`, `visitor_update`, `document_receipt_update`, `task_update`
- Même pattern HTMX/drawer que les vues de création

### urls.py
- 5 routes ajoutées : `registry/<int:pk>/update/`, `appointment/<int:pk>/update/`, etc.

### forms.py
- `title` ajouté à `RegistryEntryForm.Meta.fields` (manquait, empêchait la modification du titre)

### form_modal.html
- Support de `form_action_pk` pour résoudre les URL d'édition avec PK

### Templates (listes)
- Bouton "Modifier" dans la colonne Actions de chaque template de liste

---

## Bloqueur 2 : Tests

**Avant** : 1 test (46 lignes)  
**Après** : 66 tests, couvrant :

- Modèles (création, validation, `__str__`, comportement save) — 5 classes de test
- Services (création, mise à jour, archivage, clôture, complétion, chemins d'erreur) — 5 classes
- Vues d'édition (GET, POST, mode HTMX, permissions, scope annexe) — 5 classes
- Permissions (profil, groupe, superuser, utilisateur non autorisé) — 1 classe
- Scope/filtrage (isolation par annexe pour chaque modèle) — 1 classe

**Tous les 66 tests passent** avec `--settings=config.settings_test_local`.

---

## Autres modifications

- `urls_test_local.py` : inclusion des routes `secretary/` (manquait pour les tests)
