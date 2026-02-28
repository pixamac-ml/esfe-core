# components/about/sections.py

from django_components import component


@component.register("sections")
class Section(component.Component):

    template_name = "about/sections.html"

    def get_context_data(
        self,
        label=None,
        title=None,
        subtitle=None,
        content=None,
        image=None,
        reverse=False,
        highlights=None,
        background="white",
        icon=None,
    ):
        return {
            "label": label,
            "title": title,
            "subtitle": subtitle,
            "content": content,
            "image": image,
            "reverse": reverse,
            "highlights": highlights or [],
            "background": background,
            "icon": icon,
            "has_media": bool(image),
            "has_highlights": bool(highlights),
        }