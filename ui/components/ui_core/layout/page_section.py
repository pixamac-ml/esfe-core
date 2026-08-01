from django_components import component


@component.register("ui_core.page_section")
class PageSection(component.Component):
    template_name = "ui_core/layout/page_section.html"

    def get_context_data(self, title="", description="", labelled_by="", **kwargs):
        return {
            "title": title,
            "description": description,
            "labelled_by": labelled_by,
            **kwargs,
        }
