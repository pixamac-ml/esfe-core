from django_components import component


@component.register("sections")
class Section(component.Component):
    """
    Composant Section dédié à la page About.

    Props :
        - label (str | None)
        - title (str | None)
        - subtitle (str | None)
        - content (str | None) -> HTML autorisé
        - image (ImageField | None)
        - reverse (bool)
        - highlights (list[str])
        - background (str) -> white | light | primary | dark
        - icon (str | None) -> classes icônes (FontAwesome, Lucide, etc.)
    """

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
            # Helpers pour le template
            "has_media": bool(image),
            "has_highlights": bool(highlights),
        }