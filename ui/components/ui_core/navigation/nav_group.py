from django_components import component


@component.register("ui_core.nav_group")
class NavGroup(component.Component):
    template_name = "ui_core/navigation/nav_group.html"

    def get_context_data(self, label="", items=None, open=True, count=None, **kwargs):
        return {
            "label": label,
            "items": items or [],
            "open": bool(open),
            "count": count,
            **kwargs,
        }
