from django_components import component

@component.register("section_header")
class SectionHeader(component.Component):
    template_name = "sections/section_header/section_header.html"

    def get_context_data(
        self,
        title="",
        subtitle="",
        align="left"
    ):
        return {
            "title": title,
            "subtitle": subtitle,
            "align": align,
        }
