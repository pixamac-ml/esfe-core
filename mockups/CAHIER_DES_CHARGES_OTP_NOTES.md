# Cahier des charges — Verrouillage OTP des notes après clôture de session

## 1. Diagnostic (ce qui existe déjà — ne pas refaire)

Le système distingue déjà correctement session normale et rattrapage :

- **`academics/models.py` → `ECGrade`** (lignes ~690-798) : la note est stockée
  dans deux champs séparés, `normal_score` (session normale) et
  `retake_score` (session de rattrapage), avec `final_score` calculé
  automatiquement comme le maximum des deux.
- **`academics/models.py` → `Semester`** (lignes ~349-415) : le statut du
  semestre pilote ce qui est autorisé :
  `DRAFT → NORMAL_ENTRY → NORMAL_LOCKED → RETAKE_ENTRY → FINALIZED → PUBLISHED`.
- **`academics/services/workflow.py` → `get_semester_permissions(semester)`** :
  renvoie `can_enter_normal` (vrai seulement si `status == NORMAL_ENTRY`) et
  `can_enter_retake` (vrai si `status` est `NORMAL_LOCKED` ou
  `RETAKE_ENTRY`).
- **`portal/views/admin_grades.py` → `save_grade()`** (lignes ~396-518) :
  l'endpoint de saisie vérifie déjà ces permissions et refuse (HTTP 403) la
  saisie normale si la session normale est clôturée, et la saisie de
  rattrapage si le rattrapage n'est pas encore ouvert.
- **`portal/services/notes_workflow.py` → `apply_notes_workflow_action()`** :
  gère les transitions de clôture (`ACTION_PUBLISH_NORMAL`,
  `ACTION_ACTIVATE_RETAKE`, `ACTION_PUBLISH_FINAL`).

**Donc le blocage de base existe déjà.** Ce qui manque : un mécanisme pour
qu'un informaticien/gestionnaire puisse *exceptionnellement* corriger une
note déjà saisie dans une session clôturée, mais uniquement avec
l'autorisation du Directeur des Études (ou du DG), via un code OTP — exactement
comme le système déjà construit pour les corrections de paiement.

## 2. Pattern de référence à réutiliser (déjà fonctionnel, ne pas réinventer)

Le workflow OTP est déjà implémenté pour les paiements et doit servir de
modèle exact :

- `accounts/models.py` → `SensitiveActionRequest` (demande + code OTP haché
  sha256, expiration 5 min) et `FinancialAuditLog` (trace immuable).
- `accounts/services/sensitive_actions.py` → `request_sensitive_action()`
  (crée la demande, notifie les approbateurs) et
  `confirm_sensitive_action()` (vérifie le code, applique la modification
  via un callback, écrit l'audit log).
- `accounts/dashboards/htmx_paiements.py` → `payment_correct()` (déclenche
  la demande OTP) et `payment_correct_confirm_otp()` (vérifie le code et
  applique).
- `accounts/templates/accounts/dashboard/partials/payment_modal.html` →
  bloc UI "Validation DG/DGA requise" avec saisie du code.

## 3. Ce qu'il faut construire

### 3.1 Nouveau modèle `GradeModificationRequest`

Dans `academic_cycle/models.py` (à côté de `AcademicAuditLog` déjà présent) :

```python
class GradeModificationRequest(TimeStampedModel):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_EXPIRED = "expired"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "En attente"),
        (STATUS_APPROVED, "Approuvee"),
        (STATUS_EXPIRED, "Expiree"),
        (STATUS_CANCELLED, "Annulee"),
    ]

    SESSION_NORMAL = "normal"
    SESSION_RETAKE = "retake"
    SESSION_CHOICES = [
        (SESSION_NORMAL, "Normale"),
        (SESSION_RETAKE, "Rattrapage"),
    ]

    OTP_VALIDITY_MINUTES = 5

    branch = models.ForeignKey("branches.Branch", on_delete=models.CASCADE)
    ec_grade = models.ForeignKey("academics.ECGrade", on_delete=models.CASCADE,
                                  related_name="modification_requests")
    session_type = models.CharField(max_length=10, choices=SESSION_CHOICES)

    previous_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    requested_score = models.DecimalField(max_digits=5, decimal_places=2)
    reason = models.TextField(blank=True)

    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                      related_name="grade_modification_requests")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                     null=True, blank=True,
                                     related_name="approved_grade_modifications")

    otp_code_hash = models.CharField(max_length=128)
    attempts = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    expires_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)
```

Générer la migration correspondante.

### 3.2 Nouveau service `academic_cycle/services/grade_modifications.py`

Copier exactement la structure de `accounts/services/sensitive_actions.py` :

- `request_grade_modification(*, branch, ec_grade, session_type, requested_score, requested_by, reason="")` :
  - vérifie qu'il existe au moins un approbateur actif avec la position
    `director_of_studies` (à défaut, `executive_director` /
    `deputy_executive_director` en repli),
  - génère un code OTP à 6 chiffres, le hache en sha256,
  - crée la `GradeModificationRequest` (expiration 5 minutes),
  - notifie l'approbateur (in-app + email) avec : nom de l'informaticien
    demandeur, étudiant concerné, EC concerné, type de session, ancienne
    note, note demandée, motif, code.
- `confirm_grade_modification(*, request_id, code, approver, apply_callback)` :
  - même logique que `confirm_sensitive_action` : `select_for_update`,
    vérification expiration, vérification du code haché, incrémentation
    `attempts`, application du callback, écriture d'un
    `AcademicAuditLog` (déjà existant dans `academic_cycle/models.py`,
    action `"grade.modified_post_closure"`).
- `expire_stale_requests()` : pour le futur scheduler.

### 3.3 Modification de l'endpoint `save_grade()` (`portal/views/admin_grades.py`)

Logique à ajouter, **seulement quand la session concernée est clôturée**
(c'est-à-dire `can_enter_normal` ou `can_enter_retake` est `False` pour le
type de session demandé) :

1. Au lieu de refuser directement avec un 403, créer une
   `GradeModificationRequest` via `request_grade_modification()` et
   renvoyer un fragment HTMX affichant : "Code envoyé au Directeur des
   Études. Saisissez-le pour confirmer la modification."
2. Nouvel endpoint `save_grade_confirm_otp()` (même fichier) : reçoit
   `request_id` + `otp_code`, appelle `confirm_grade_modification()` avec
   un callback qui met à jour `normal_score` ou `retake_score` selon
   `session_type`, recalcule `final_score` via `apply_ec_grade()` (déjà
   existant), puis sauvegarde.
3. Nouvelle URL nommée (ex: `htmx_save_grade_confirm_otp`) dans les urls de
   l'app `portal`/`academics` concernée.

**Important — ce qui ne doit PAS être permis même avec OTP** : si la
session normale n'a jamais été saisie du tout (pas de `normal_score`
existant), le rattrapage doit rester bloqué comme aujourd'hui
(`can_edit_retake_grade()` dans `portal/services/notes_workflow.py`) — l'OTP
ne sert qu'à débloquer une **correction** sur une note déjà entrée dans une
session déjà clôturée, pas à contourner l'ordre logique normal → rattrapage.

### 3.4 UI

Créer un partiel HTMX similaire à `payment_modal.html`, avec un bloc
"Validation du Directeur des Études requise" + champ de saisie du code, sur
l'écran/modale de saisie de note (fichier exact à identifier dans les
templates de `portal` — chercher le template utilisé par `save_grade`).

### 3.5 Vérifications à faire avant de considérer la tâche terminée

- `python manage.py makemigrations --check --dry-run` (pas de migration
  oubliée),
- `python manage.py migrate` (OK),
- `python manage.py check` (0 erreur),
- Test manuel : saisir une note en session normale ouverte (doit marcher
  sans OTP, comme avant) ; clôturer la session ; tenter de modifier la même
  note (doit déclencher la demande OTP) ; saisir un mauvais code (doit
  être refusé) ; saisir le bon code (doit appliquer la modification et
  l'historiser dans `AcademicAuditLog`).

## 4. Hors-périmètre de cette tâche (ne pas toucher)

- La logique de calcul des notes (`apply_ec_grade`, `compute_ec_status`)
  ne change pas.
- Les transitions de statut du semestre (`apply_notes_workflow_action`) ne
  changent pas — seule la possibilité de *corriger après clôture* est
  ajoutée, en parallèle, via OTP.
- `AcademicCorrectionRequest` (demandes de correction post-publication,
  visibles par l'étudiant) est un système différent, ne pas fusionner avec
  `GradeModificationRequest`.
