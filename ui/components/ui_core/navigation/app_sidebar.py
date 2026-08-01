from django_components import component


@component.register("ui_core.app_sidebar")
class AppSidebar(component.Component):
    template_name = "ui_core/navigation/app_sidebar.html"

    def get_context_data(
        self,
        groups=None,
        brand="ESFE",
        subtitle="Portail",
        user_name="",
        user_meta="",
        collapsed=False,
        **kwargs,
    ):
        return {
            "groups": groups or [],
            "brand": brand,
            "subtitle": subtitle,
            "user_name": user_name,
            "user_meta": user_meta,
            "collapsed": collapsed,
            **kwargs,
        }
