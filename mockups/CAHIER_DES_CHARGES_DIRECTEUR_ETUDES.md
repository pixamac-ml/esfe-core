# Cahier des charges — Renforcement du Dashboard Directeur des Études

## Note sur le périmètre git

Ce document ne couvre QUE le développement. **Ne pas pousser (`git push`) le
résultat** — s'arrêter au commit local. La mise en ligne sera décidée et
faite séparément.

## 1. Contexte

Le rôle `director_of_studies` (`accounts/models.py`, position dans
`Profile.POSITION_CHOICES`) gère le suivi pédagogique d'**une annexe**
(à ne pas confondre avec le DG/DGA, qui ont une vision globale
multi-annexes et un rôle financier/stratégique).

Fichiers existants à connaître avant de modifier quoi que ce soit :
- `portal/views/views.py` lignes ~310-1430 : toutes les vues du dashboard
  director (`_render_director_dashboard()`, `_build_director_workspace_context()`,
  `director_results_action`, `director_bulletin_action`,
  `director_teacher_*`, `director_transfer_*`, `director_planner_*`...).
- `portal/services/director/` : 5 modules de services
  (`teacher_assignment`, `classroom_ops`, `planning_assignment`,
  `document_workflow`, `transfer_workflow`).
- `templates/portal/staff/director_dashboard.html` : template unique,
  12 sections (home, operations, academic, teachers, assignments, results,
  publications, documents, stats, students, settings).
- `academics/permissions.py` : `BULLETIN_MANAGEMENT_POSITIONS = {super_admin, director_of_studies}`.
- `academic_cycle/models.py` : `BranchAcademicCycle`, `AcademicCorrectionRequest`,
  `AcademicAuditLog` (déjà existant mais jamais appelé pour les validations
  de semestre — seulement esquissé pour d'autres usages).
- Pattern OTP de référence (déjà fonctionnel pour les paiements) :
  `accounts/models.py:SensitiveActionRequest`,
  `accounts/services/sensitive_actions.py`,
  `accounts/dashboards/htmx_paiements.py`.
- **Important** : si le cahier des charges `CAHIER_DES_CHARGES_OTP_NOTES.md`
  (verrouillage OTP des notes de session normale/rattrapage post-clôture)
  est déjà en cours d'implémentation ou terminé, réutiliser **les mêmes**
  modèles/services qui y sont créés (`GradeModificationRequest` et le
  service `academic_cycle/services/grade_modifications.py`) plutôt que d'en
  recréer des équivalents. Vérifier leur existence avant de commencer.

## 2. Ce qu'il faut construire — par ordre de priorité

### 2.1 PRIORITÉ HAUTE — OTP sur la validation/publication de semestre

**Problème :** `director_results_action` (action `validate` / `publish` /
`reject`) change l'état d'un `Semester` sans aucun contrôle externe. Une
seule personne peut, seule, publier des résultats définitifs.

**A construire :**
- Étendre `SensitiveActionRequest.ACTION_CHOICES` (`accounts/models.py`)
  avec une nouvelle valeur `ACTION_SEMESTER_PUBLISH = "semester_publish"`
  (et `ACTION_SEMESTER_VALIDATE` si on veut aussi protéger l'étape
  `validate`, à décider selon le niveau de friction voulu — recommandation :
  protéger seulement l'action **`publish`**, qui est irréversible, pas
  `validate` qui est une étape intermédiaire).
- Dans `director_results_action()` (`portal/views/views.py`), quand
  `action == "publish"` :
  1. Au lieu d'appliquer directement le changement de statut, appeler
     `request_sensitive_action()` (réutiliser le service existant
     `accounts/services/sensitive_actions.py`) avec
     `target_model="Semester"`, `target_id=semester.pk`,
     `previous_state={"status": semester.status}`,
     `requested_state={"status": Semester.STATUS_PUBLISHED}`.
  2. Déterminer les approbateurs : le DG/DGA de l'annexe (réutiliser
     `_approvers_for_branch()` déjà présent dans
     `accounts/services/sensitive_actions.py`).
  3. Afficher un écran "Code envoyé au DG/DGA pour validation finale de
     la publication" avec saisie du code.
  4. Nouvel endpoint `director_results_confirm_otp` : vérifie le code via
     `confirm_sensitive_action()`, applique réellement le changement de
     statut (callback qui fait ce que faisait l'ancien code direct), et
     déclenche la génération des bulletins comme avant.
- Mettre à jour le template `director_dashboard.html` (section "results")
  avec le même type de bloc que `payment_modal.html` (saisie du code OTP).

### 2.2 PRIORITÉ HAUTE — Audit académique des validations

**Problème :** aucune trace de qui a validé/publié/rejeté un semestre, ni
de l'état avant/après.

**A construire :**
- Utiliser le modèle déjà existant `academic_cycle/models.py:AcademicAuditLog`
  (champs : `actor`, `branch`, `academic_year`, `action`, `object_type`,
  `object_id`, `old_values`, `new_values`, `reason`, `created_at`).
- Dans `director_results_action()` (et dans le callback de confirmation
  OTP du point 2.1), créer systématiquement une entrée
  `AcademicAuditLog` à chaque transition de statut de `Semester` :
  `action="semester.validated"`, `"semester.published"`,
  `"semester.rejected"`, avec `old_values={"status": ancien}` /
  `new_values={"status": nouveau}`.
- Vérifier qu'il existe déjà un service utilitaire pour créer ces logs
  (`academic_cycle/services/audit_service.py` — confirmé présent lors de
  l'analyse précédente, fonction `log_action()` ou équivalent) ; sinon,
  créer une fonction simple `log_academic_action(actor, branch, academic_year, action, obj, old_values, new_values, reason="")`.

### 2.3 PRIORITÉ HAUTE — Centre de tâches pédagogique

**Problème :** le directeur doit naviguer manuellement entre 12 sections
pour repérer les blocages (classes sans notes, enseignants sans EC
assignés, anomalies).

**A construire :**
- Nouvelle fonction dans `portal/services/director/` (ou un nouveau module
  `portal/services/director/tasks_center.py`) :
  `build_director_tasks_center(branch, academic_year)` qui retourne une
  liste structurée de tâches à traiter, par exemple :
  - Classes dont la saisie des notes normale n'est pas terminée (statut
    semestre encore `NORMAL_ENTRY` alors que la date limite est dépassée —
    si une date limite existe, sinon juste lister celles encore ouvertes).
  - Enseignants sans aucun EC assigné pour le semestre en cours.
  - Classes en attente de validation (`STATUS_NORMAL_LOCKED` ou
    `STATUS_RETAKE_ENTRY` prêtes mais pas encore `FINALIZED`).
  - Documents enseignants en attente de validation (déjà géré par
    `director_teacher_document_review`, juste à lister les en-attente).
  - Demandes de transfert étudiant en attente.
  - Anomalies de notes déjà détectées par le code existant
    (`result_anomalies`) — mais sans la limite arbitraire de 12 (corriger
    aussi ce point, voir 2.5).
- Afficher ce centre de tâches en première section du dashboard ("home"),
  avec un compteur par catégorie et un lien direct vers la section
  correspondante.

### 2.4 PRIORITÉ MOYENNE — Notifications

**Problème :** aucune notification ne prévient le directeur d'un
événement pédagogique (notes soumises par un enseignant, classe prête à
valider, document en attente).

**A construire :**
- Réutiliser le système de notification déjà existant dans le projet
  (`NotificationService`, déjà utilisé dans
  `accounts/services/sensitive_actions.py` — vérifier son interface exacte
  avant de l'utiliser : `communication/services` ou équivalent).
- Déclencher une notification au directeur de l'annexe concernée quand :
  - un enseignant termine la saisie de toutes les notes d'une classe pour
    une session (normale ou rattrapage),
  - un document enseignant est uploadé et nécessite validation,
  - une demande de transfert est créée.
- Ces déclenchements peuvent se faire via signal `post_save` (sur
  `ECGrade`, `TeacherDocument`, transfert) ou directement dans les vues
  concernées — choisir l'option la plus simple à intégrer sans dupliquer
  de logique.

### 2.5 PRIORITÉ MOYENNE — Corrections ponctuelles

- Supprimer la limite arbitraire `result_anomalies[:12]` (chercher dans
  `portal/services/director/` ou `portal/views/views.py`) et la remplacer
  par une pagination réelle, ou au minimum afficher le nombre total
  ("12 affichées sur 47").
- Ajouter la pagination sur les listes de classes/semestres/enseignants/
  étudiants dans le dashboard director (actuellement tout est rendu sans
  pagination — réutiliser le composant `dg-pagination` déjà utilisé dans
  le dashboard gestionnaire si disponible/partagé).
- Vérifier et corriger les requêtes N+1 dans
  `_build_director_workspace_context()` (`portal/views/views.py`) : utiliser
  `select_related`/`prefetch_related` partout où des relations sont
  parcourues en boucle.
- Ajouter un verrou explicite empêchant la modification d'une note après
  publication du semestre, **en dehors du flux OTP** déjà spécifié dans
  `CAHIER_DES_CHARGES_OTP_NOTES.md` — s'assurer que les deux mécanismes
  (clôture de session normale/rattrapage + clôture de semestre publié)
  sont cohérents entre eux et ne se contredisent pas.

### 2.6 PRIORITÉ BASSE — Rapports pédagogiques

- Ajouter un export (Excel, en réutilisant le pattern déjà existant dans
  `accounts/services/excel_reports.py` pour le dashboard gestionnaire) avec :
  taux de réussite par classe, moyenne par classe/programme, nombre
  d'abandons, comparatif par semestre.
- Cette tâche peut être traitée en dernier, elle n'a pas d'impact sur la
  fiabilité/sécurité du système, seulement sur le confort de pilotage.

## 3. Vérifications à faire avant de considérer la tâche terminée

- `python manage.py makemigrations --check --dry-run`
- `python manage.py migrate`
- `python manage.py check` (0 erreur)
- Test manuel du flux complet : saisie notes → clôture normale →
  rattrapage → validation semestre → tentative de publication (doit
  déclencher l'OTP) → saisie du bon code → publication effective → vérifier
  qu'une entrée `AcademicAuditLog` a été créée.
- Vérifier que le centre de tâches (2.3) reflète bien l'état réel après
  ces actions (les tâches résolues disparaissent de la liste).

## 4. Hors périmètre de cette tâche

- Ne pas toucher au dashboard du DG (`accounts/dashboards/executive_dashboard.py`).
- Ne pas dupliquer le travail déjà demandé dans
  `CAHIER_DES_CHARGES_OTP_NOTES.md` (verrouillage des notes elles-mêmes) —
  ce document-ci concerne la validation/publication du **semestre dans son
  ensemble**, pas la note individuelle.
- Ne pas pousser sur GitHub (`git push`) — s'arrêter au commit local, comme
  précisé en introduction.
