# components/about/block.py

from django_components import component


@component.register("about_block")
class AboutBlock(component.Component):
    """
    Composant Bloc À propos.

    Props :
        - block (instance AboutContentBlock déjà filtrée)
    """

    template_name = "about/block.html"

    def get_context_data(self, block):
        return {
            "block": block,
            "layout": block.layout,
            "title": block.title,
            "content": block.content,
            "image": block.image,
            "images": block.images.all(),
        }