# Layout components
from .layout.navbar.navbar import Navbar
from .layout.footer.footer import Footer

# Section components
from .sections.section_header.section_header import SectionHeader
from .sections.hero.hero import Hero

# UI components
from .ui.button.button import Button
from .interactive.dropdown.dropdown import Dropdown
from .interactive.modal.modal import Modal
from .interactive.accordion.accordion import Accordion
from .dashboard.dashboard_card import DashboardCard
from .dashboard.empty_state import EmptyState
from .dashboard.info_field import InfoField
from .dashboard.metric_card import MetricCard
from .dashboard.progress_bar import ProgressBar
from .dashboard.status_badge import StatusBadge

# Card components
from .cards.base_card.base_card import BaseCard
from .cards.formation_card.formation_card import FormationCard

# Formation detail components
from .formation_hero.formation_hero import FormationHero
from .formation_overview.formation_overview import FormationOverview

# Informaticien workflow components
from .notes.notes_actions import NotesActions
from .notes.notes_progress import NotesProgress
from .notes.notes_grid import NotesGrid
from .notes.notes_state import NotesState
from .notes.notes_state_banner import NotesStateBanner
from .notes.notes_table import NotesTable
from .notes.notes_workflow import NotesWorkflow
from .notes.notes_header import NotesHeader
from .notes.student_identity_column import StudentIdentityColumn
from .notes.ec_note_cell import ECNoteCell
from .notes.semester_summary import SemesterSummary
from .notes.notes_validation_panel import NotesValidationPanel
from .notes.notes_anomaly_panel import NotesAnomalyPanel
from .notes.notes_actions_bar import NotesActionsBar
from .informaticien.audit_log_table import AuditLogTable
from .informaticien.import_panel import ImportPanel
from .informaticien.settings_panel import SettingsPanel
from .informaticien.supervision_panel import SupervisionPanel
from .informaticien.support_panel import SupportPanel
from .formation_finance.formation_finance import FormationFinance
from .formation_documents.formation_documents import FormationDocuments
from .formation_trust_block.formation_trust_block import FormationTrustBlock
from .formation_admission_card.formation_admission_card import FormationAdmission


# Admission
from .admission.admission_hero.admission_hero import AdmissionHero
from .admission.admission_form_card.admission_form_card import AdmissionFormCard
from .admission.step_indicator.step_indicator import StepIndicator

# Layout
from .layout.split_admission_layout.split_admission_layout import SplitAdmissionLayout

# Forms
from .forms.upload_zone.upload_zone import UploadZone

from .layout.section import section

from .formation_learning_outcomes.formation_learning_outcomes import FormationLearningOutcomes
from .formation_career_opportunities.formation_career_opportunities import FormationCareerOpportunities

from .formation_overview.formation_overview import FormationOverview

from .alerts_panel import AlertsPanel
from .attendance_workflow import AttendanceWorkflow
from .timetable_view import TimetableView
