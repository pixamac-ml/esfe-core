from django_components import component


@component.register("academic_quick_action")
class AcademicQuickAction(component.Component):
    """Bouton d'action rapide scolaire : icône + label, compatible HTMX."""

    template_name = "academic/academic_quick_action.html"

    def get_context_data(
        self,
        label="",
        icon="",
        href="",
        variant="outline",
        tone="primary",
        size="md",
        hx_get="",
        hx_post="",
        hx_target="",
        hx_swap="innerHTML",
        hx_indicator="",
        **kwargs,
    ):
        return {
            "label": label,
            "icon": icon,
            "href": href,
            "variant": variant,
            "tone": tone,
            "size": size,
            "hx_get": hx_get,
            "hx_post": hx_post,
            "hx_target": hx_target,
            "hx_swap": hx_swap,
            "hx_indicator": hx_indicator,
            **kwargs,
        }
