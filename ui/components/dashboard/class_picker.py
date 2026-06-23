from django_components import component


@component.register("class_picker")
class ClassPicker(component.Component):
    template_name = "dashboard/class_picker.html"

    def get_context_data(
        self,
        id="sg-class-selector",
        name="class_id",
        items=None,
        selected_id="",
        placeholder="Choisir une classe",
        hx_get="",
        hx_target="#supervisor-workspace",
        **kwargs,
    ):
        return {
            "id": id,
            "name": name,
            "items": items or [],
            "selected_id": selected_id,
            "placeholder": placeholder,
            "hx_get": hx_get,
            "hx_target": hx_target,
            **kwargs,
        }
