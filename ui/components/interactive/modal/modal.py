from django_components import component

@component.register("modal")
class Modal(component.Component):
    template_name = "interactive/modal/modal.html"

    def get_context_data(self, title, open_label):
        return {
            "title": title,
            "open_label": open_label,
        }
