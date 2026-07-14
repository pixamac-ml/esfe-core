from django_components import component


@component.register("academic_sidebar")
class AcademicSidebar(component.Component):
    """Sidebar scolaire professionnelle avec sous-menus repliables."""

    template_name = "academic/academic_sidebar.html"

    def get_context_data(
        self,
        items=None,
        active_key="home",
        brand_title="ESFE",
        brand_subtitle="",
        user_name="",
        user_role="",
        user_initial="D",
        collapsed=False,
        **kwargs,
    ):
        items = items or []
        active_parent_keys = {
            item["key"]
            for item in items
            if item.get("children") and any(
                child.get("key") == active_key for child in item["children"]
            )
        }
        return {
            "items": items,
            "active_key": active_key,
            "active_parent_keys": active_parent_keys,
            "brand_title": brand_title,
            "brand_subtitle": brand_subtitle,
            "user_name": user_name,
            "user_role": user_role,
            "user_initial": user_initial,
            "collapsed": collapsed,
            **kwargs,
        }
