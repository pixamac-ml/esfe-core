# ui/components/about/about_presentation.py

from django_components import component


@component.register("about_presentation")
class AboutPresentation(component.Component):
    """
    Section présentation avec vision/mission.
    """

    template_name = "about/about_presentation.html"

    def get_context_data(
        self,
        about_title="",
        about_text="",
        about_image=None,
        vision_title="Notre Vision",
        vision_text="",
        mission_title="Notre Mission",
        mission_text="",
    ):
        return {
            "about_title": about_title,
            "about_text": about_text,
            "about_image": about_image,
            "vision_title": vision_title,
            "vision_text": vision_text,
            "mission_title": mission_title,
            "mission_text": mission_text,
        }