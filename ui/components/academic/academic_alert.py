from django_components import component


@component.register("academic_alert")
class AcademicAlert(component.Component):
    """Message alerte scolaire : info, succès, avertissement, erreur."""

    template_name = "academic/academic_alert.html"

    def get_context_data(
        self,
        title="",
        message="",
        tone="info",
        variant="default",
        dismissible=False,
        icon="",
        class_str="",
        **kwargs,
    ):
        return {
            "title": title,
            "message": message,
            "tone": tone,
            "variant": variant,
            "dismissible": dismissible,
            "icon": icon,
            "class_str": class_str,
            **kwargs,
        }
