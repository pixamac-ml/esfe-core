from django_components import component


@component.register("secretary_sidebar")
class SecretarySidebar(component.Component):
    template_name = "dashboard/secretary_sidebar.html"

    def get_context_data(
        self,
        nav_items=None,
        active_section="overview",
        **kwargs,
    ):
        return {
            "nav_items": nav_items or [],
            "active_section": active_section,
            **kwargs,
        }
