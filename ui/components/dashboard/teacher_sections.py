from django_components import component


class _TeacherSection(component.Component):
    section_name = ""

    def get_context_data(self, **kwargs):
        return {"active_section": self.section_name, **kwargs}


@component.register("teacher_workspace")
class TeacherWorkspace(component.Component):
    template_name = "dashboard/teacher_workspace.html"

    def get_context_data(self, **kwargs):
        return kwargs


@component.register("teacher_classes_section")
class TeacherClassesSection(_TeacherSection):
    section_name = "classes"
    template_name = "dashboard/teacher_classes_section.html"


@component.register("teacher_supports_section")
class TeacherSupportsSection(_TeacherSection):
    section_name = "supports"
    template_name = "dashboard/teacher_supports_section.html"


@component.register("teacher_schedule_section")
class TeacherScheduleSection(_TeacherSection):
    section_name = "schedule"
    template_name = "dashboard/teacher_schedule_section.html"


@component.register("teacher_logs_section")
class TeacherLogsSection(_TeacherSection):
    section_name = "logs"
    template_name = "dashboard/teacher_logs_section.html"


@component.register("teacher_salary_section")
class TeacherSalarySection(_TeacherSection):
    section_name = "salary"
    template_name = "dashboard/teacher_salary_section.html"


@component.register("teacher_notifications_section")
class TeacherNotificationsSection(_TeacherSection):
    section_name = "notifications"
    template_name = "dashboard/teacher_notifications_section.html"


@component.register("teacher_settings_section")
class TeacherSettingsSection(_TeacherSection):
    section_name = "settings"
    template_name = "dashboard/teacher_settings_section.html"
