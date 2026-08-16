# Atoms
from .atoms.icon import Icon
from .atoms.label import Label
from .atoms.avatar import Avatar
from .atoms.pill import Pill
from .atoms.spinner import Spinner
from .atoms.skeleton import Skeleton
from .atoms.badge import Badge
from .atoms.tooltip import Tooltip
from .atoms.divider import Divider
from .atoms.avatar_group import AvatarGroup

# Layout components
from .layout.navbar.navbar import Navbar
from .layout.footer.footer import Footer
from .layout.breadcrumb import Breadcrumb
from .layout.panel import Panel

# Section components
from .sections.section_header.section_header import SectionHeader
from .sections.hero.hero import Hero

# UI components
from .ui.button.button import Button
from .interactive.dropdown.dropdown import Dropdown
from .interactive.modal.modal import Modal
from .interactive.accordion.accordion import Accordion
from .interactive.popover.popover import Popover
from .dashboard.dashboard_card import DashboardCard
from .dashboard.empty_state import EmptyState
from .dashboard.info_field import InfoField
from .dashboard.metric_card import MetricCard
from .dashboard.progress_bar import ProgressBar
from .dashboard.status_badge import StatusBadge
from .dashboard.class_picker import ClassPicker
from .dashboard.drawer import Drawer
from .dashboard.form_field import FormField
from .dashboard.search_bar import SearchBar
from .dashboard.tabs import Tabs
from .dashboard.widget_card import WidgetCard
from .dashboard.kpi_row import KpiRow
from .dashboard.skeleton_card import SkeletonCard
from .dashboard.page_header import PageHeader
from .dashboard.toolbar import Toolbar
from .dashboard.data_table import DataTable
from .dashboard.pagination import Pagination
from .dashboard.toast import Toast
from .dashboard.stat_card import StatCard
from .dashboard.progress_ring import ProgressRing
from .dashboard.mini_stat import MiniStat
from .dashboard.loading_overlay import LoadingOverlay
from .dashboard.filter_bar import FilterBar
from .dashboard.timeline import Timeline
from .dashboard.chart_card import ChartCard
from .dashboard.alert import Alert
from .dashboard.confirm_dialog import ConfirmDialog
from .dashboard.status_cell import StatusCell
from .dashboard.amount_cell import AmountCell
from .dashboard.actions_cell import ActionsCell
from .dashboard.avatar_name_cell import AvatarNameCell
from .dashboard.schedule import Schedule
from .dashboard.teacher_overview_section import TeacherOverviewSection
from .dashboard.teacher_sections import (
    TeacherClassesSection,
    TeacherLogsSection,
    TeacherNotificationsSection,
    TeacherSalarySection,
    TeacherScheduleSection,
    TeacherSettingsSection,
    TeacherSupportsSection,
    TeacherWorkspace,
)
from .dashboard.secretary_sidebar import SecretarySidebar
from .dashboard.secretary_topbar import SecretaryTopbar
from .dashboard.secretary_sections import (
    SecretaryWorkspace,
    SecretaryOverviewSection,
    SecretaryRegistrySection,
    SecretaryVisitsSection,
    SecretaryAppointmentsSection,
    SecretaryDepositsSection,
    SecretaryMeetingsSection,
    SecretaryTasksSection,
    SecretaryReportsSection,
    SecretarySalarySection,
    SecretaryNotificationsSection,
    SecretarySettingsSection,
)
from .dashboard.supervisor_sidebar import SupervisorSidebar
from .dashboard.supervisor_topbar import SupervisorTopbar
from .dashboard.supervisor_workspace import SupervisorWorkspace

# Portal shared components — réutilisables dans tous les dashboards
from .dashboard.portal_notification_bell import PortalNotificationBell
from .dashboard.portal_salary_section import PortalSalarySection
from .dashboard.portal_notifications_section import PortalNotificationsSection
from .dashboard.portal_settings_section import PortalSettingsSection

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
from .notes.ec_note_cell_live import ECNoteCellLive
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
from .forms.input import Input
from .forms.textarea import Textarea
from .forms.select import Select
from .forms.checkbox import Checkbox
from .forms.radio_group import RadioGroup
from .forms.amount_input import AmountInput
from .forms.form_actions import FormActions
from .forms.combobox import Combobox
from .forms.date_picker import DatePicker
from .forms.switch import Switch
from .forms.form_section import FormSection
from .forms.stepper import Stepper

from .layout.section import section

from .formation_learning_outcomes.formation_learning_outcomes import FormationLearningOutcomes
from .formation_career_opportunities.formation_career_opportunities import FormationCareerOpportunities

from .formation_overview.formation_overview import FormationOverview

from .alerts_panel import AlertsPanel
from .attendance_workflow import AttendanceWorkflow
from .timetable_view import TimetableView

# Calendar components — frontend Calendrier Académique
from .calendar import (
    CalendarEntryCard,
    CalendarMiniList,
    CalendarMonthGrid,
    CalendarYearGrid,
)

# Academic wrappers — composants scolaires réutilisables pour tous les dashboards
from .academic import (
    AcademicAlert,
    AcademicBadge,
    AcademicButton,
    AcademicCalendar,
    AcademicCard,
    AcademicDrawer,
    AcademicEmptyState,
    AcademicFilterBar,
    AcademicModal,
    AcademicPageHeader,
    AcademicPageLayout,
    AcademicProgress,
    AcademicQuickAction,
    AcademicSectionHeader,
    AcademicSidebar,
    AcademicStudentLiveStatus,
    AcademicStatCard,
    AcademicStepper,
    AcademicTable,
    AcademicTabs,
    AcademicTimeline,
    AcademicToolbar,
)

# UI Core foundation. Existing components remain registered for compatibility.
from .ui_core import (
    Alert as UiCoreAlert,
    AppShell,
    AppSidebar,
    AppTopbar,
    Breadcrumb as UiCoreBreadcrumb,
    ChartPanel as UiCoreChartPanel,
    ConfirmDialog as UiCoreConfirmDialog,
    ContentGrid,
    DataTable as UiCoreDataTable,
    Drawer as UiCoreDrawer,
    DropdownMenu as UiCoreDropdownMenu,
    EmptyState as UiCoreEmptyState,
    DjangoFormField as UiCoreDjangoFormField,
    FilterBar as UiCoreFilterBar,
    FormField as UiCoreFormField,
    LoadingOverlay as UiCoreLoadingOverlay,
    Modal as UiCoreModal,
    NavGroup,
    NavItem,
    PageHeader as UiCorePageHeader,
    PageSection,
    Panel as UiCorePanel,
    ProgressBar as UiCoreProgressBar,
    StatCard as UiCoreStatCard,
    StatusBadge as UiCoreStatusBadge,
    Tabs as UiCoreTabs,
    Timeline as UiCoreTimeline,
    Toast as UiCoreToast,
)

# Shared domain components — composants métier partagés réutilisables dans tous les dashboards
from .account.profile_card import ProfileCard
from .account.profile_dropdown import ProfileDropdown
from .account.profile_view import ProfileView
from .account.profile_editor import ProfileEditor
from .account.security_settings import SecuritySettings
from .account.preference_settings import PreferenceSettings

from .notifications.bell import NotificationBell
from .notifications.badge import NotificationBadge
from .notifications.item import NotificationItem
from .notifications.list import NotificationList
from .notifications.drawer import NotificationDrawer

from .student.identity_card import StudentIdentityCard
from .student.status_card import StudentStatusCard
from .student.progress_card import StudentProgressCard

from .shop.product_card import ProductCard
from .shop.product_grid import ProductGrid
from .shop.product_detail_drawer import ProductDetailDrawer
