from django_components import component


@component.register("avatar_name_cell")
class AvatarNameCell(component.Component):
    template_name = "dashboard/avatar_name_cell.html"

    def get_context_data(self, initials="", photo_url="", name="", subtitle="", **kwargs):
        return {
            "initials": initials,
            "photo_url": photo_url,
            "name": name,
            "subtitle": subtitle,
            **kwargs,
        }
