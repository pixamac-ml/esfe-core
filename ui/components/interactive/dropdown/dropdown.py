from django_components import component

@component.register("dropdown")
class Dropdown(component.Component):
    template_name = "interactive/dropdown/dropdown.html"

    def get_context_data(self, label="Menu"):
        return {"label": label}
