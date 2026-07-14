from django_components import component


@component.register("academic_timeline")
class AcademicTimeline(component.Component):
    """Fil chronologique scolaire : validations, paiements, inscriptions."""

    template_name = "academic/academic_timeline.html"

    def get_context_data(self, items=None, class_str="", **kwargs):
        return {
            "items": items or [],
            "class_str": class_str,
            **kwargs,
        }
