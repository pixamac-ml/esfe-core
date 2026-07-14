from django_components import component


@component.register("icon")
class Icon(component.Component):
    template_name = "atoms/icon.html"

    def get_context_data(self, name="", size=16, class_str="", **kwargs):
        aliases = {
            "file-circle-check": "file-check",
            "file-chart-column": "chart-column",
            "users-gear": "user-round-cog",
            "address-book": "contact-round",
            "arrows-rotate": "refresh-cw",
            "hand-holding-heart": "hand-heart",
            "birthday-cake": "cake",
            "sack-dollar": "circle-dollar-sign",
        }

        return {
            "name": aliases.get(name, name),
            "size": size,
            "class_str": class_str,
            **kwargs,
        }
