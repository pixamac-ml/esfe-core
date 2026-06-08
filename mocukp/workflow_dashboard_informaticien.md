# Workflow Dashboard Informaticien — ESFE Core

## Architecture technique

Le dashboard informaticien repose sur un stack **100 % dynamique côté navigateur** :

| Technologie | Rôle |
|-------------|------|
| **HTMX** | Chargement des workspaces, actions CRUD, rechargement partiel |
| **Alpine.js** | Shell du dashboard (sidebar, drawers, modals, état local, dark mode) |
| **django-components** | Composants réutilisables (notes_workflow, ec_note_cell, grades_maquette, etc.) |
| **CSS Grid** | Maquette de saisie des notes (remplace les `<table>` lourdes) |

**Principe** : Aucun rechargement complet de page. Chaque action est un échange HTMX qui remplace un fragment. L'état est porté par le DOM et Alpine.js.

---

## Circuit complet du workflow notes

```
[1. VÉRIFICATION STRUCTURE]
        │
        ▼
[2. SAISIE NORMALE] ◄─── hx-post vers save_grade()
        │                    validation 0-20 temps réel
        ▼
[3. VERROUILLAGE NORMALE] ───► État : ready_to_publish_normal
        │
        ▼
[4. PUBLICATION NORMALE] ───► État : normal_published
        │
        ▼
[5. ACTIVATION RATTRAPAGE] ───► État : retake_in_progress
        │
        ▼
[6. SAISIE RATTRAPAGE] ◄─── hx-post vers save_grade(session=retake)
        │                    dettes apurées automatiquement
        ▼
[7. VERROUILLAGE RATTRAPAGE] ───► État : ready_to_publish_final
        │
        ▼
[8. PUBLICATION FINALE] ───► État : final_published
        │
        ▼
[9. DÉCISION ANNUELLE] ───► Auto-calculée par compute_annual_decision()
                             VALIDÉ / ADMISSIBLE / NON ADMIS
                             Dettes créées automatiquement
```

---

## 1. Vérification structure académique

Avant toute saisie, l'informaticien doit s'assurer que la maquette est correcte.

**Workspace** : `it_structure_workspace()` → `structure_workspace.html`

### Affichage

```
┌──────────────────────────────────────────────────────────┐
│  Classes │ Maquettes (UE/EC) │ Affectations enseignants  │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  Classe        Semestres   UE   EC   Statut notes        │
│  ───────       ─────────   ──   ──   ────────────        │
│  L1-IPA-1      2           6    24   INCOMPLET           │
│  L1-IPA-2      2           6    24   PRET                 │
│  L2-IPA        2           5    20   EN COURS             │
│  ...                                                      │
└──────────────────────────────────────────────────────────┘
```

**Indicateurs** :
- `INCOMPLET` → EC sans notes
- `PRET` → toutes les notes saisies
- `EN COURS` → saisie en cours
- `ANOMALIE` → EC sans enseignant, crédits incohérents

**Données** : `build_structure_context(branch)` dans `informaticien_workflows.py`

---

## 2. Saisie des notes — Session normale

**Point d'entrée** : La grille `grades_maquette` (CSS Grid) se charge via :
```
hx-get="/portal/it/workflows/notes/load/?class_id=X&semester_id=Y&session=normal"
hx-target="#notes-workspace"
```

### Composants impliqués

```
notes_maquette.html
  └── grades_maquette (CSS Grid)
        ├── notes_header (en-têtes UE / EC)
        ├── notes_actions_bar (pills Normale/Rattrapage + publier)
        ├── student_identity_column (N° / Nom / Prénom)
        ├── ec_note_cell (cellule note éditable)
        └── semester_summary (moyenne, % , crédits)
```

### Saisie temps réel

Chaque champ `<input>` dans `ec_note_cell` a :
```html
hx-post="{% url 'accounts_portal:save_grade' %}"
hx-trigger="blur, changed delay:150ms, keyup[key=='Enter']"
hx-target="closest tr"
hx-swap="outerHTML"
```

**La validation 0-20 est double** :
1. **HTML5** : `min="0" max="20" step="0.01"` → blocage navigateur
2. **Backend** : `calculate_ec_grade()` lève `ValidationError` si note hors intervalle

### Comportement par session

- **Session normale** : `edit_score = grade.normal_score` — champ édite la note normale
- **Session rattrapage** : `edit_score = grade.retake_score` — champ édite la note de rattrapage
- Si `is_retake_editable = False` (EC déjà validé en normale), le champ est `disabled`

### Affichage des métriques par EC

Chaque cellule EC affiche :
```
┌──────────────────┐
│  [ 12.50 ]       │  ← champ éditable
│  N 12.00         │  ← note normale
│  R 14.00  F 14.00│  ← rattrapage + finale (visible qu'en session retake)
│  badge: R        │  ← "R" si retake fait (visible qu'en session retake)
└──────────────────┘
```

Couleurs de fond :
- `cell-ok` (vert) → EC validé (note ≥ seuil)
- `cell-bad` (rouge) → EC échoué (note < seuil)
- `cell-empty` (gris) → pas encore de note

---

## 3. Workflow states (machine à états)

Gérée par `notes_workflow.py` (service) + `notes_workflow` (composant).

```
EMPTY
  │  ACTION_START → STATUS_NORMAL_ENTRY
  ▼
IN_PROGRESS
  │  Toutes les notes saisies → ACTION_VERIFY
  ▼
READY_TO_PUBLISH_NORMAL
  │  ACTION_PUBLISH_NORMAL
  ▼
NORMAL_PUBLISHED
  │  ACTION_PREVIEW_RETAKE (vérifie les rattrapages possibles)
  │  ACTION_ACTIVATE_RETAKE → STATUS_RETAKE_ENTRY
  ▼
RETAKE_IN_PROGRESS
  │  Tous les rattrapages faits → ACTION_VERIFY
  ▼
READY_TO_PUBLISH_FINAL
  │  ACTION_PUBLISH_FINAL
  ▼
FINAL_PUBLISHED
```

**Composant workflow** (`notes_workflow`):
```
┌──────────────────────────────────────────────────────┐
│  [Normale]  [Rattrapage]      ← pills de session     │
├──────────────────────────────────────────────────────┤
│  État : Saisie en cours                               │
│  Progression : 85% (22/26 notes)                      │
│  Notes manquantes : 4                                 │
│  Alertes : Coefficient 0 sur EC "XXX"                 │
├──────────────────────────────────────────────────────┤
│  [Vérifier]  [Publier]  [Ouvrir rattrapage]          │
└──────────────────────────────────────────────────────┘
```

Les actions disponibles sont déterminées par `get_available_actions(state)` qui retourne une liste d'actions possibles selon l'état courant ET les permissions.

---

## 4. Publication

Déclenchée par `apply_notes_workflow_action()`.

### Publication normale
- Vérifie que toutes les notes sont saisies (`can_publish_semester()`)
- Passe le semestre en `STATUS_NORMAL_PUBLISHED`
- Génère les bulletins semestriels (`generate_semester_bulletins_for_class()`)
- Les rattrapages deviennent possibles

### Activation rattrapage
- Vérifie que la normale est publiée
- Passe le semestre en `STATUS_RETAKE_ENTRY`
- Affiche la modale de preview (`retake_modal.html`) :
  ```
  ┌──────────────────────────────────────────────┐
  │  Rattrapage — L1-IPA-1 — S1                  │
  ├──────────────────────────────────────────────┤
  │  Étudiant      Matières échouées    Actions   │
  │  Dupont Jean   Anatomie, Biochimie  [OK]     │
  │  Martin Sara   Pharmacologie        [OK]     │
  │  Total : 12 candidats, 18 matières           │
  ├──────────────────────────────────────────────┤
  │           [Activer le rattrapage]             │
  └──────────────────────────────────────────────┘
  ```

### Publication finale
- Vérifie que tous les rattrapages sont saisis
- Passe le semestre en `STATUS_FINALIZED`
- Dernière génération de bulletins
- Verrouille toute modification

---

## 5. Décision annuelle

**Automatique et non modifiable par l'informaticien.**

Calculée par `compute_annual_decision(enrollment)` dans `year.py` :

```
S1 validé ET S2 validé          → VALIDÉ       (passe, 0 dette)
S1 validé ET S2 proche seuil    → ADMISSIBLE   (passe avec dettes)
S2 validé ET S1 proche seuil    → ADMISSIBLE   (passe avec dettes)
Sinon                           → NON ADMIS    (redouble)
```

La marge d'admissibilité (`admissibility_gap`, défaut 2.00) est paramétrable sur la classe dans l'admin.

### Création automatique des dettes
- Quand `ADMISSIBLE` → `create_academic_debts()` crée un `AcademicDebt` par EC échoué
- Ces dettes sont visibles dans le dashboard informaticien (section supervision)

### Affichage dashboard
```
┌──────────────────────────────────────────────┐
│  Décisions annuelles — L1-IPA — 2025-2026     │
├──────────────────────────────────────────────┤
│  VALIDÉ     ████████████  15  (vert)          │
│  ADMISSIBLE ████          4   (orange)        │
│  NON ADMIS  ██            2   (rouge)         │
│  INCOMPLET  █             1   (gris)          │
│  Total : 22 étudiants                          │
└──────────────────────────────────────────────┘
```

---

## 6. Import / Export

### Import Excel
- Point d'entrée : `it_import_workspace()` → `import_workspace.html`
- Upload via formulaire HTMX
- Backend : `import_notes_file()` dans `informaticien_workflows.py`
- Résultat :
  ```
  ┌──────────────────────────────────────────────┐
  │  Import terminé                                │
  │  Lignes lues : 120                             │
  │  Notes importées : 112                         │
  │  Anomalies : 8                                 │
  │    - Ligne 15 : note > 20                      │
  │    - Ligne 34 : EC introuvable                 │
  │    - Ligne 67 : étudiant non inscrit           │
  └──────────────────────────────────────────────┘
  ```

### Export Excel
- Point d'entrée : `it_export_notes_excel()`
- 3 onglets : Notes, Anomalies, Résultats
- Téléchargement direct (pas de HTMX, retour de fichier)

---

## 7. Dashboard Directeur des Études (lecture seule)

`portal/views/views.py:_render_director_dashboard()` → `director_dashboard.html`

### Ce qu'il voit

```
┌──────────────────────────────────────────────────────────┐
│  DASHBOARD DIRECTION DES ÉTUDES                           │
├──────────────────────────────────────────────────────────┤
│  Accueil │ Opérations │ Pédagogie │ Résultats │ Pubs     │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  🏫 Classes : 12         📊 Moyenne générale : 11.2      │
│  👨‍🎓 Étudiants : 340      📈 Taux de réussite : 72%     │
│  👨‍🏫 Enseignants : 28     ⏳ Rattrapages en cours : 3    │
│                                                          │
│  📋 Décisions en attente de validation : 5               │
│                                                          │
│  Classes avec notes incomplètes : 2                       │
│    • L1-IPA-2 (4 notes manquantes)                       │
│    • L2-GB-1 (1 note manquante)                          │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### Actions possibles (limitées)
- Consulter les résultats
- Lancer une génération de bulletins (publish)
- Valider les décisions annuelles (workflow pédagogique)
- Voir les détails par classe/étudiant

### Pas possible
- Saisir ou modifier des notes
- Modifier la structure académique
- Activer/désactiver des comptes

---

## 8. Dashboard DG (lecture seule)

`portal/views/views.py:dg_portal()` → `portal/dg/dashboard.html`

### Architecture multi-annexes

```
┌──────────────────────────────────────────────────────────┐
│  DASHBOARD DIRECTION GÉNÉRALE                             │
├──────────────────────────────────────────────────────────┤
│  KPIs │ Alertes │ Workflow │ Finance │ Annexes │ RH      │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  Annexe de Bamako    ───  245 étudiants, 18 classes      │
│  Annexe de Sikasso   ───  180 étudiants, 14 classes      │
│  Annexe de Ségou     ───  95 étudiants, 8 classes        │
│                                                          │
│  📊 Synthèse financière par annexe                       │
│  ⚠ Alertes prioritaires : 3                             │
│  📋 Workflow passages : VALIDÉ 45 | ADMISSIBLE 12 | ... │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### Section Versements bancaires
Le DG doit voir les versements par annexe (banque, référence, date, montant, justificatif).

### Pas possible
- Modifier une note ou un résultat
- Modifier la structure
- Voir les données d'une seule annexe sans跨 (tout est consolidé)

### Source de données
`build_dg_dashboard_context()` dans `portal/dg/services.py` (1012 lignes) :
- Branch summaries (finance, students, classes, alerts)
- Priority alerts (attendance, student cases, pending payments)
- Workflow pipeline (year decisions)
- Finance summary (cash position, monthly trends)
- Analytics (risk breakdown, performance)
- RH summary (teacher load, staff counts)

---

## 9. Les dashboards — différences clés

| Aspect | Informaticien | Dir. Études | DG |
|--------|---------------|-------------|-----|
| **Filtrage** | Annexe unique | Annexe unique | Toutes annexes |
| **Saisie notes** | Oui | Non | Non |
| **Structure** | CRUD complet | Lecture seule | Lecture seule |
| **Publication** | Oui (via workflow) | Validation | — |
| **Décisions** | Non (calcul auto) | Validation péda | Supervision |
| **Finance** | Non | Non | Oui |
| **RH** | Non | Enseignants | Tout staff |
| **Dashboard** | HTMX + Alpine | Alpine + Chart.js | Alpine + Chart.js |
| **Données** | Temps réel | Temps réel | Consolidé |

---

## 10. Les hx-trigger patterns utilisés

### Saisie notes (ec_note_cell)
```html
hx-trigger="blur, changed delay:150ms, keyup[key=='Enter']"
```
→ Sauvegarde au blur, après 150ms de pause, ou sur Entrée.

### Changement de session (normal/rattrapage)
```html
hx-get="/portal/it/workflows/notes/load/?class_id={{...}}&semester={{...}}&session=retake"
hx-target="#notes-workspace"
hx-swap="innerHTML"
```
→ Recharge toute la grille dans le nouveau mode.

### Workflow actions (publier, activer rattrapage)
```html
hx-post="/portal/it/workflows/notes/action/"
hx-vals='{"action": "publish_normal", "class_id": "...", "semester_id": "..."}'
hx-target="#workspace-content"
hx-swap="innerHTML"
```
→ action POST → serveur traite → retourne le workspace mis à jour.

### Navigation sidebar (dashboard informaticien)
```html
a @click.prevent="currentSection = 'notes'; $refs.notesWorkspace Load()"
```
→ Alpine.js bascule la section + HTMX charge le workspace.

### Drawers
```html
button @click="drawerOpen = true"
     hx-get="/portal/it/workflows/notes/load/?drawer=1&..."
     hx-target="#drawer-content"
```
→ Ouvre un drawer plein écran avec le contenu HTMX.

### Modals
```html
button hx-get="/portal/it/workflows/structure/modal/?action=edit_ec&ec_id=..."
         hx-target="#modal-content"
         @click="modalOpen = true"
```
→ Charge le formulaire dans la modale Alpine.

---

## 11. Pagination des structures (UE/EC)

La vue `it_structure_drawer()` pagine les EC par UE (10 max par écran) pour éviter les templates trop lourds :

```html
button hx-get="/portal/it/workflows/structure/drawer/?class_id=X&page=2"
         hx-target="#drawer-content"
         hx-swap="innerHTML"
```

---

## 12. Résumé des fichiers clés

| Fichier | Rôle |
|---------|------|
| `portal/views/it_workflows.py` | Toutes les views HTMX du dashboard informaticien |
| `portal/views/admin_grades.py` | Grille de notes, sauvegarde, contextes |
| `portal/services/informaticien_workflows.py` | Logique métier du dashboard informaticien |
| `portal/services/notes_workflow.py` | Machine à états du workflow notes |
| `portal/selectors/it_workflow_selectors.py` | Requêtes DB pour le dashboard |
| `academics/services/workflow.py` | Permissions semestre |
| `academics/services/year.py` | Calcul décision annuelle + dettes |
| `academics/services/grading.py` | Calcul EC, seuils, apurement dettes |
| `academics/services/documents.py` | Génération bulletins + logs |
| `academics/models.py` | AcademicDebt, AcademicDecisionLog |
| `ui/components/notes/ec_note_cell.py` | Cellule note éditable |
| `ui/components/notes/notes_workflow.py` | Composant workflow |
| `ui/components/grades/maquette/maquette.py` | Grille CSS Grid |
| `templates/portal/informaticien/dashboard.html` | Shell Alpine.js du dashboard informaticien |
| `templates/portal/informaticien/workflows/notes_workspace.html` | Workspace notes |
| `templates/portal/informaticien/drawers/notes_drawer.html` | Drawer notes |
| `templates/portal/informaticien/workflows/home_workspace.html` | Accueil du dashboard |
| `templates/portal/staff/director_dashboard.html` | Dashboard Dir. Études |
| `portal/dg/services.py` | Logique métier dashboard DG |
| `portal/views/views.py` | Views DG + Dir. Études |

---

*Document généré le 05/06/2026 — se référer à `analyse_systeme_notes_academics.md` pour le détail du moteur de calcul et à `logique_frontend_notes.md` pour les impacts frontend généraux.*
