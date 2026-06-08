# Audit Dashboard Secrétaire — Problèmes corrigés

## Résumé des modifications

6 fichiers modifiés, 3 types de bugs corrigés.

---

## Bug #1 — Boutons d'action sur les pages liste (CLOSING / TERMINER / PRENDRE EN CHARGE / ARCHIVER)

**Fichiers concernés :**
- `appointment_list.html`
- `visitor_list.html`
- `registry_list.html`
- `task_list.html`
- `document_receipt_list.html`

**Problème :** Tous ces templates utilisaient :
```html
<form method="post" hx-post="..." hx-target="body" hx-swap="none">
```

**Conséquence :**
1. Le POST part, l'action s'exécute en base de données ✅
2. La vue renvoie `_refresh_response()` → `HttpResponse("")` avec `HX-Trigger`
3. `hx-swap="none"` → **aucun changement dans le DOM**
4. Les événements `HX-Trigger` (`secretary:X-updated`, etc.) sont bien dispatchés
5. **Mais personne ne les écoute** sur les pages liste (les partiels avec `hx-trigger` ne sont que dans `dashboard.html`)
6. **Résultat :** l'action est faite en base mais l'UI ne bouge pas → l'utilisateur pense que "le bouton ne fait rien"

**Correctif :** Remplacé `hx-post`/`hx-target`/`hx-swap` par `action="..."` classique :
```html
<form method="post" action="{% url '...' %}">
```
Les vues ont toutes un `redirect(...)` pour les requêtes non-HTMX. La page se recharge naturellement après l'action, affichant l'état à jour.

---

## Bug #2 — `item.student` au lieu de `item.related_student`

**Fichier :** `partials/dashboard_visits_open.html:16`

```diff
- <td>{% if item.student %}{{ item.student.full_name }}{% else %}-{% endif %}</td>
+ <td>{% if item.related_student %}{{ item.related_student.full_name }}{% else %}-{% endif %}</td>
```

Le champ du modèle `VisitorLog` s'appelle `related_student`, pas `student`. La colonne "Étudiant cible" dans les visites ouvertes était **toujours vide**.

J'en ai profité pour ajouter le nom de l'étudiant aussi dans `dashboard_overview_visits.html`.

---

## Bug #3 — `signals.py` toujours vide (RAPPEL)

`secretary/signals.py:1` n'a toujours aucun `post_save`/`post_delete`. Les modifications faites via l'admin Django, l'API, ou d'autres dashboards **ne déclenchent aucun rafraîchissement HTMX** du dashboard secrétaire.

---

## État du "Sortie" sur le dashboard

Le bouton "Sortie" dans les partiels dashboard (`dashboard_visits_open.html` ligne 18, `dashboard_overview_visits.html` ligne 11) utilise :
```html
hx-target="closest tr"    (ou closest .sg-action-card)
hx-swap="outerHTML swap:180ms"
data-sg-optimistic="fade-remove"
```

Ce pattern est **correct** :
1. La ligne/carte disparaît après 180ms (remplacée par la réponse vide)
2. Les événements `visits-updated` + `kpis-updated` + `sidebar-updated` sont dispatchés
3. Les partiels `#sg-visits-open`, `#sg-dashboard-kpis`, `#sg-sidebar-counters`, etc. se rafraîchissent

Si le "Sortie" ne fonctionne pas pour toi, vérifie dans la console navigateur (F12) si la requête POST renvoie une erreur. Le plus probable est un **CSRF périmé** si tu restes longtemps sur la page sans la recharger.

---

## Liste complète des fichiers modifiés

| Fichier | Ligne | Modification |
|---------|-------|-------------|
| `secretary/templates/secretary/appointment_list.html` | 51 | `hx-post` → `action` (Cloturer) |
| `secretary/templates/secretary/visitor_list.html` | 51 | `hx-post` → `action` (Cloturer) |
| `secretary/templates/secretary/registry_list.html` | 58,64,70 | `hx-post` → `action` (3 formulaires) |
| `secretary/templates/secretary/task_list.html` | 50,56 | `hx-post` → `action` (2 formulaires) |
| `secretary/templates/secretary/document_receipt_list.html` | 50,57 | `hx-post` → `action` (2 formulaires) |
| `secretary/templates/secretary/partials/dashboard_visits_open.html` | 16 | `item.student` → `item.related_student` |
| `secretary/templates/secretary/partials/dashboard_overview_visits.html` | 10 | Ajout `related_student.full_name` |
