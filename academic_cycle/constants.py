BRANCH_CYCLE_DRAFT = "draft"
BRANCH_CYCLE_PREPARATION = "preparation"
BRANCH_CYCLE_REGISTRATION_OPEN = "registration_open"
BRANCH_CYCLE_ACTIVE = "active"
BRANCH_CYCLE_EXAMS = "exams"
BRANCH_CYCLE_DELIBERATION = "deliberation"
BRANCH_CYCLE_CLOSING = "closing"
BRANCH_CYCLE_CLOSED = "closed"
BRANCH_CYCLE_ARCHIVED = "archived"

BRANCH_CYCLE_STATUS_CHOICES = [
    (BRANCH_CYCLE_DRAFT, "Brouillon"),
    (BRANCH_CYCLE_PREPARATION, "Preparation"),
    (BRANCH_CYCLE_REGISTRATION_OPEN, "Reinscriptions ouvertes"),
    (BRANCH_CYCLE_ACTIVE, "Active"),
    (BRANCH_CYCLE_EXAMS, "Examens"),
    (BRANCH_CYCLE_DELIBERATION, "Deliberation"),
    (BRANCH_CYCLE_CLOSING, "Cloture en cours"),
    (BRANCH_CYCLE_CLOSED, "Cloturee"),
    (BRANCH_CYCLE_ARCHIVED, "Archivee"),
]

CLASS_TEACHING = "teaching"
CLASS_SEMESTER_1_COMPLETED = "semester_1_completed"
CLASS_SEMESTER_2_COMPLETED = "semester_2_completed"
CLASS_GRADES_COMPLETED = "grades_completed"
CLASS_BULLETINS_GENERATED = "bulletins_generated"
CLASS_READY_FOR_DELIBERATION = "ready_for_deliberation"
CLASS_DELIBERATED = "deliberated"
CLASS_CLOSED = "closed"

CLASS_CYCLE_STATUS_CHOICES = [
    (CLASS_TEACHING, "Cours"),
    (CLASS_SEMESTER_1_COMPLETED, "Semestre 1 termine"),
    (CLASS_SEMESTER_2_COMPLETED, "Semestre 2 termine"),
    (CLASS_GRADES_COMPLETED, "Notes terminees"),
    (CLASS_BULLETINS_GENERATED, "Bulletins generes"),
    (CLASS_READY_FOR_DELIBERATION, "Prete pour deliberation"),
    (CLASS_DELIBERATED, "Deliberee"),
    (CLASS_CLOSED, "Cloturee"),
]

CLOSURE_REPORT_DRAFT = "draft"
CLOSURE_REPORT_VALID = "valid"
CLOSURE_REPORT_INVALID = "invalid"

CLOSURE_REPORT_STATUS_CHOICES = [
    (CLOSURE_REPORT_DRAFT, "Brouillon"),
    (CLOSURE_REPORT_VALID, "Valide"),
    (CLOSURE_REPORT_INVALID, "Invalide"),
]

DECISION_PROMOTED = "promoted"
DECISION_PROMOTED_WITH_ACADEMIC_DEBT = "promoted_with_academic_debt"
DECISION_REPEATED = "repeated"
DECISION_GRADUATED = "graduated"
DECISION_DROPPED = "dropped"
DECISION_TRANSFERRED = "transferred"
DECISION_PENDING = "pending"

STUDENT_DECISION_CHOICES = [
    (DECISION_PROMOTED, "Promu"),
    (DECISION_PROMOTED_WITH_ACADEMIC_DEBT, "Promu avec dette academique"),
    (DECISION_REPEATED, "Redouble"),
    (DECISION_GRADUATED, "Diplome"),
    (DECISION_DROPPED, "Abandon"),
    (DECISION_TRANSFERRED, "Transfere"),
    (DECISION_PENDING, "En attente"),
]

DEBT_CREDITS = "credits"
DEBT_UE = "ue"
DEBT_EC = "ec"
DEBT_SEMESTER = "semester"

ACADEMIC_DEBT_TYPE_CHOICES = [
    (DEBT_CREDITS, "Credits"),
    (DEBT_UE, "UE"),
    (DEBT_EC, "EC"),
    (DEBT_SEMESTER, "Semestre"),
]

DEBT_PENDING = "pending"
DEBT_SCHEDULED = "scheduled"
DEBT_IN_PROGRESS = "in_progress"
DEBT_RESOLVED = "resolved"
DEBT_CANCELLED = "cancelled"

ACADEMIC_DEBT_STATUS_CHOICES = [
    (DEBT_PENDING, "En attente"),
    (DEBT_SCHEDULED, "Planifiee"),
    (DEBT_IN_PROGRESS, "En cours"),
    (DEBT_RESOLVED, "Resolue"),
    (DEBT_CANCELLED, "Annulee"),
]

FINANCIAL_CLEAR = "clear"
FINANCIAL_LIGHT_DEBT = "light_debt"
FINANCIAL_MEDIUM_DEBT = "medium_debt"
FINANCIAL_CRITICAL_DEBT = "critical_debt"
FINANCIAL_BLOCKED_DOCUMENTS = "blocked_documents"

FINANCIAL_STATUS_CHOICES = [
    (FINANCIAL_CLEAR, "A jour"),
    (FINANCIAL_LIGHT_DEBT, "Dette legere"),
    (FINANCIAL_MEDIUM_DEBT, "Dette moyenne"),
    (FINANCIAL_CRITICAL_DEBT, "Dette critique"),
    (FINANCIAL_BLOCKED_DOCUMENTS, "Documents bloques"),
]

ACCESS_FULL = "full"
ACCESS_VACATION = "vacation"
ACCESS_REENROLLMENT_REQUIRED = "reenrollment_required"
ACCESS_LIMITED = "limited"
ACCESS_RESTRICTED = "restricted"
ACCESS_ALUMNI = "alumni"
ACCESS_SUSPENDED = "suspended"

ACCESS_LEVEL_CHOICES = [
    (ACCESS_FULL, "Complet"),
    (ACCESS_VACATION, "Vacances"),
    (ACCESS_REENROLLMENT_REQUIRED, "Reinscription requise"),
    (ACCESS_LIMITED, "Limite"),
    (ACCESS_RESTRICTED, "Restreint"),
    (ACCESS_ALUMNI, "Alumni"),
    (ACCESS_SUSPENDED, "Suspendu"),
]
