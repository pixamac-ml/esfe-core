from django_components import component


@component.register("ui_core.page_header")
class PageHeader(component.Component):
    template_name = "ui_core/layout/page_header.html"

    def get_context_data(self, title="", subtitle="", eyebrow="", **kwargs):
        return {"title": title, "subtitle": subtitle, "eyebrow": eyebrow, **kwargs}
