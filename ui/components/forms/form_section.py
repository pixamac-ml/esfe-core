from django_components import component


@component.register("form_section")
class FormSection(component.Component):
    template_name = "forms/form_section.html"

    def get_context_data(self, title="", description="", class_str="", **kwargs):
        return {
            "title": title,
            "description": description,
            "class_str": class_str,
            **kwargs,
        }
