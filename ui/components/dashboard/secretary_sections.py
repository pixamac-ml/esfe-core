from django_components import component


class _SecretarySection(component.Component):
    section_name = ""

    def get_context_data(self, **kwargs):
        return {"active_section": self.section_name, **kwargs}


@component.register("secretary_workspace")
class SecretaryWorkspace(component.Component):
    template_name = "dashboard/secretary_workspace.html"

    def get_context_data(self, **kwargs):
        return kwargs


@component.register("secretary_overview_section")
class SecretaryOverviewSection(_SecretarySection):
    section_name = "overview"
    template_name = "dashboard/secretary_overview_section.html"


@component.register("secretary_registry_section")
class SecretaryRegistrySection(_SecretarySection):
    section_name = "registry"
    template_name = "dashboard/secretary_registry_section.html"


@component.register("secretary_visits_section")
class SecretaryVisitsSection(_SecretarySection):
    section_name = "visits"
    template_name = "dashboard/secretary_visits_section.html"


@component.register("secretary_appointments_section")
class SecretaryAppointmentsSection(_SecretarySection):
    section_name = "appointments"
    template_name = "dashboard/secretary_appointments_section.html"


@component.register("secretary_deposits_section")
class SecretaryDepositsSection(_SecretarySection):
    section_name = "deposits"
    template_name = "dashboard/secretary_deposits_section.html"


@component.register("secretary_meetings_section")
class SecretaryMeetingsSection(_SecretarySection):
    section_name = "meetings"
    template_name = "dashboard/secretary_meetings_section.html"


@component.register("secretary_tasks_section")
class SecretaryTasksSection(_SecretarySection):
    section_name = "tasks"
    template_name = "dashboard/secretary_tasks_section.html"


@component.register("secretary_reports_section")
class SecretaryReportsSection(_SecretarySection):
    section_name = "reports"
    template_name = "dashboard/secretary_reports_section.html"


@component.register("secretary_salary_section")
class SecretarySalarySection(_SecretarySection):
    section_name = "salary"
    template_name = "dashboard/secretary_salary_section.html"


@component.register("secretary_notifications_section")
class SecretaryNotificationsSection(_SecretarySection):
    section_name = "notifications"
    template_name = "dashboard/secretary_notifications_section.html"


@component.register("secretary_settings_section")
class SecretarySettingsSection(_SecretarySection):
    section_name = "settings"
    template_name = "dashboard/secretary_settings_section.html"
