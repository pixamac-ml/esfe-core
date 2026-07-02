from django_components import component


@component.register("page_header")
class PageHeader(component.Component):
    template_name = "dashboard/page_header.html"

    def get_context_data(
        self,
        title="",
        subtitle="",
        breadcrumb_items=None,
        class_str="",
        **kwargs,
    ):
        return {
            "title": title,
            "subtitle": subtitle,
            "breadcrumb_items": breadcrumb_items or [],
            "class_str": class_str,
            **kwargs,
        }
