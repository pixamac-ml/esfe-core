# Logique Frontend — Système de Notes (après refactoring moteur)

Ce document décrit les impacts frontend des 11 modifications backend du moteur de notes, pour guider la mise à jour des templates, dashboards et rapports.

---

## 1. Décision annuelle : nouveau vocabulaire

**Backend** (`academics/services/year.py`) :
- `DECISION_VALIDE` = "VALIDÉ"
- `DECISION_ADMISSIBLE` = "ADMISSIBLE"
- `DECISION_NON_ADMIS` = "NON ADMIS"

**Frontend** — Partout où une décision annuelle est affichée :

| Ancien | Nouveau |
|--------|---------|
| Promu / Réussi | **VALIDÉ** |
| *(inexistant)* | **ADMISSIBLE** |
| Redoublant / Échoué | **NON ADMIS** |

### Templates à vérifier
- `students/templates/students/student_detail.html` — décision annuelle
- `academics/templates/academics/bulletin.html` — mention "Résultat"
- `portal/templates/portal/student_dashboard.html` — statut année
- `secretary/templates/secretary/` — rapports de classe
- `reporting/` — exports Excel/PDF

### Couleurs recommandées
- VALIDÉ → vert (`bg-green-100 text-green-800`)
- ADMISSIBLE → orange (`bg-yellow-100 text-yellow-800`)
- NON ADMIS → rouge (`bg-red-100 text-red-800`)

---

## 2. Pas de moyenne annuelle

**Backend** : `compute_annual_result()` retourne `average: None`.
- Bulletin annuel n'affiche plus de moyenne générale.
- On affiche uniquement :
  - Semestre 1 (moyenne + résultats EC/UE)
  - Semestre 2 (moyenne + résultats EC/UE)
  - Décision annuelle (VALIDÉ / ADMISSIBLE / NON ADMIS)

### Templates impactés
- `academics/templates/academics/bulletin_annuel.html` — supprimer la ligne "Moyenne annuelle"
- `documents/bulletins/bulletin_annuel_pdf.html` — idem
- `portal/templates/portal/dashboard_partials/academic_summary.html` — enlever moyenne annuelle

---

## 3. Affichage des EC avec seuil par coefficient

**Backend** : `resolve_ec_threshold(coeff)` → 1→8, 2→10, ≥3→12.

### Affichage recommandé
Dans la colonne "Seuil" ou "Note minimale" du tableau des notes :
```
Coefficient 1 → seuil 8/20
Coefficient 2 → seuil 10/20
Coefficient ≥3 → seuil 12/20
```

Ajouter une indication visuelle quand `note < seuil` (ex. texte en rouge, icône warning).

---

## 4. Validation notes 0-20

**Backend** : `ECGrade.save()` lève `ValidationError` si note hors [0, 20].

### Frontend
- Le formulaire de saisie de notes doit déjà avoir `min=0 max=20` en HTML5.
- Ajouter un message d'erreur clair côté template : *"La note doit être comprise entre 0 et 20."*
- Vérifier `forms.py` de l'app `academics` : si `clean_note()` existe, s'assurer qu'il attrape `ValidationError`.

---

## 5. `admissibility_gap` paramétrable

**Backend** : Nouveau champ `AcademicClass.admissibility_gap` (Decimal, default=2.00).

### Admin
Déjà exposé dans `AcademicClassAdmin.list_display` + `fieldsets`.

### Dashboard gestionnaire
Si un formulaire de configuration de classe existe, ajouter le champ `admissibility_gap` avec une aide :
> "Écart autorisé entre la moyenne d'un semestre et le seuil de validation pour être déclaré ADMISSIBLE. Défaut : 2.00."

---

## 6. Bulletins PDF / Impression

### `generate_annual_bulletin()`
- N'inclut plus `average_display` dans le contexte.
- Inclut désormais : `dettes`, `admissibility_gap`, `raisons` (liste des raisons de non-validation).
- Le snapshot (`SemesterSnapshot`) stocke les décisions par semestre.

### Template PDF (`documents/bulletins/bulletin_annuel_pdf.html`)
```
Élève : {{ eleve.nom }}
Classe : {{ classe.nom }}
Année : {{ annee }}

Semestre 1 : {{ s1_moyenne }} /20 — {{ s1_decision }}
Semestre 2 : {{ s2_moyenne }} /20 — {{ s2_decision }}

Décision annuelle : {{ decision }}
Gap appliqué : {{ admissibility_gap }}
Raisons : {{ raisons|join:", " }}
```

---

## 7. Dashboard étudiant

Dans `portal/student-dashboard/` :

### Avant
```
Moyenne annuelle : 12.5 → Promu
```

### Après
```
Semestre 1 : 11.2 → ADMISSIBLE
Semestre 2 : 13.0 → VALIDÉ
Décision annuelle : ADMISSIBLE
```

---

## 8. Dashboard gestionnaire / secrétaire

### Liste des élèves par classe
Ajouter colonne "Décision" :
| Élève | S1 | S2 | Décision |
|-------|----|----|----------|
| Dupont | 11.2 | 13.0 | ADMISSIBLE |
| Martin | 8.5 | 9.0 | NON ADMIS |
| Durand | 14.0 | 15.5 | VALIDÉ |

---

## 9. Mapping réinscription (ancien → nouveau vocabulaire)

| Nouvelle décision | Ancienne (StudentYearDecision) |
|-------------------|-------------------------------|
| VALIDÉ            | promoted                      |
| ADMISSIBLE        | promoted                      |
| NON ADMIS         | repeated                      |

Le frontend du portail de réinscription (`portal/templates/portal/reenrollment.html`) utilise déjà `promoted`/`repeated`. Aucun changement nécessaire — le mapping est fait côté service (`reenrollment_service.py`).

---

## 10. Tests de non-régression frontend

Après modifications des templates, vérifier :
1. Bulletin annuel PDF : absence de moyenne annuelle, présence des 2 semestres + décision
2. Dashboard étudiant : aucune erreur de template due à `average` manquant
3. Dashboard gestionnaire : colonnes de décision correctes
4. Admin classe : champ `admissibility_gap` visible et modifiable
5. Réinscription : le mapping VALIDÉ/ADMISSIBLE → promoted fonctionne (pas d'étudiant ADMISSIBLE refusé)

---

## Résumé des fichiers frontend à modifier

| Fichier | Modification |
|---------|-------------|
| `academics/templates/academics/bulletin_annuel.html` | Supprimer moyenne annuelle, ajouter gap + raisons |
| `documents/bulletins/bulletin_annuel_pdf.html` | Idem |
| `portal/templates/portal/student_dashboard.html` | Afficher S1/S2 + décision au lieu de moyenne annuelle |
| `portal/templates/portal/dashboard_partials/academic_summary.html` | Même logique |
| `students/templates/students/student_detail.html` | Mettre à jour vocabulaire décision |
| `secretary/templates/secretary/class_list.html` | Ajouter colonne décision |
| `academics/forms.py` (si existant) | Validation note 0-20 |

---

## 11. Dettes académiques (AcademicDebt)

Le modèle `AcademicDebt` a été implémenté pour le suivi persistant inter-années.

### Création automatique
- Quand un étudiant est déclaré **ADMISSIBLE**, `compute_annual_decision()` appelle `create_academic_debts()` dans `year.py`
- Un enregistrement `AcademicDebt` est créé pour chaque EC non validé du semestre échoué
- Champs : `enrollment`, `ec`, `semester`, `academic_year`, `academic_class`, `score_original`, `status` (pending/cleared)

### Report vers l'année supérieure
- Dans `reenrollment_service.py`, `_carry_forward_debts()` est appelé lors de `apply_student_decision()`
- Les dettes `pending` sont marquées avec `carry_forward_to` = nouvelle année académique

### Apurement (clear)
- Dans `grading.py`, `_clear_debts_on_validation()` est appelée dans `apply_ec_grade()`
- Quand un EC est validé (note ≥ seuil), on cherche une dette `pending` pour ce couple `enrollment`+`ec`
- Si trouvée, `mark_cleared()` passe le statut à `cleared` et enregistre `score_retake`

### Admin
- Enregistré sous `academics.AcademicDebt` avec filtre par statut, année, classe
- Visible dans l'interface d'administration Django

### Templates
- Dashboard secrétaire/gestionnaire : ajouter une section "Dettes en cours" avec :
  - Étudiant, EC, Semestre, Note originale, Statut, Année de report
- Profil étudiant : afficher les dettes non soldées
- Export : inclure le statut des dettes dans les rapports de classe

---

*Document généré le 04/06/2026 — se référer à `analyze_systeme_notes_academics.md` pour le détail des 11 modifications backend et du modèle AcademicDebt.*
