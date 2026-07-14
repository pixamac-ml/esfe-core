from django_components import component


@component.register("academic_tabs")
class AcademicTabs(component.Component):
    """Onglets scolaires avec support HTMX."""

    template_name = "academic/academic_tabs.html"

    def get_context_data(
        self,
        tabs=None,
        active_tab="",
        name="academic_tabs",
        hx_target="",
        id="academic-tabs",
        **kwargs,
    ):
        return {
            "tabs": tabs or [],
            "active_tab": active_tab,
            "name": name,
            "hx_target": hx_target,
            "id": id,
            **kwargs,
        }
