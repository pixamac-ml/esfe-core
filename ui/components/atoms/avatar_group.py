from django_components import component


@component.register("avatar_group")
class AvatarGroup(component.Component):
    template_name = "atoms/avatar_group.html"

    def get_context_data(self, avatars=None, max_display=4, size="md", **kwargs):
        sizes = {"sm": "w-7 h-7 text-[10px]", "md": "w-9 h-9 text-xs", "lg": "w-12 h-12 text-sm"}
        total = len(avatars or [])
        display = (avatars or [])[:max_display]
        overflow = total - max_display if total > max_display else 0
        return {
            "avatars": display,
            "overflow": overflow,
            "size_class": sizes.get(size, sizes["md"]),
            "size": size,
            **kwargs,
        }
