from django_components import component


@component.register("ui_core.nav_item")
class NavItem(component.Component):
    template_name = "ui_core/navigation/nav_item.html"

    def get_context_data(
        self,
        label="",
        url="#",
        icon="circle",
        active=False,
        badge=None,
        disabled=False,
        nested=False,
        external=False,
        icon_only=False,
        hx_get="",
        hx_target="",
        hx_swap="innerHTML",
        hx_push_url="",
        nav_key="",
        **kwargs,
    ):
        return {
            "label": label,
            "url": url or "#",
            "icon": icon or "circle",
            "active": bool(active),
            "badge": badge,
            "disabled": bool(disabled),
            "nested": bool(nested),
            "external": bool(external),
            "icon_only": bool(icon_only),
            "hx_get": hx_get,
            "hx_target": hx_target,
            "hx_swap": hx_swap,
            "hx_push_url": hx_push_url,
            "nav_key": nav_key,
            **kwargs,
        }
