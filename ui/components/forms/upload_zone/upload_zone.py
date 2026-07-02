from django_components import component


@component.register("upload_zone")
class UploadZone(component.Component):
    template_name = "components/forms/upload_zone/upload_zone.html"

    def get_context_data(
        self,
        name="file",
        label="",
        accept="",
        multiple=False,
        max_size_mb=5,
        required=False,
        disabled=False,
        class_str="",
        **kwargs,
    ):
        return {
            "name": name,
            "label": label,
            "accept": accept,
            "multiple": multiple,
            "max_size_mb": max_size_mb,
            "required": required,
            "disabled": disabled,
            "class_str": class_str,
            **kwargs,
        }
