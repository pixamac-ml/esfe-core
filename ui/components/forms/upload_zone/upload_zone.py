from django_components import component


@component.register("upload_zone")
class UploadZone(component.Component):
    template_name = "components/forms/upload_zone/upload_zone.html"

    def get_context_data(self, name, label, required=False):
        return {
            "name": name,
            "label": label,
            "required": required,
        }
