from django_components import component


@component.register("avatar")
class Avatar(component.Component):
    template_name = "atoms/avatar.html"

    def get_context_data(self, initials="", photo_url="", size="md", **kwargs):
        sizes = {"sm": "w-8 h-8 text-xs", "md": "w-10 h-10 text-sm", "lg": "w-14 h-14 text-lg"}
        return {
            "initials": initials,
            "photo_url": photo_url,
            "size_class": sizes.get(size, sizes["md"]),
            **kwargs,
        }
