from django_components import component


@component.register("academic_student_live_status")
class AcademicStudentLiveStatus(component.Component):
    """Reusable, role-neutral view of a student's academic situation now."""

    template_name = "academic/student_live_status.html"

    def get_context_data(self, snapshot=None, variant="compact", actions=None, **kwargs):
        return {
            "snapshot": snapshot or {},
            "variant": variant if variant in {"compact", "detail"} else "compact",
            "actions": actions or [],
            **kwargs,
        }
