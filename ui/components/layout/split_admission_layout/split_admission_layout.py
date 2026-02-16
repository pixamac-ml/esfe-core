from django_components import component


@component.register("split_admission_layout")
class SplitAdmissionLayout(component.Component):
    template_name = "components/layout/split_admission_layout/split_admission_layout.html"

    def get_context_data(self, image_url, image_text_title=None, image_text_subtitle=None):
        return {
            "image_url": image_url,
            "image_text_title": image_text_title,
            "image_text_subtitle": image_text_subtitle,
        }
