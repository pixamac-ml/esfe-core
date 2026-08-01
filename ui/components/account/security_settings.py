from django_components import component


@component.register("account.security_settings")
class SecuritySettings(component.Component):
    template_name = "account/security_settings.html"

    def get_context_data(
        self,
        password_form=None,
        hx_post="",
        hx_target="",
        sessions=None,
        security_events=None,
        **kwargs,
    ):
        return {
            "password_form": password_form,
            "hx_post": hx_post,
            "hx_target": hx_target,
            "sessions": sessions or [],
            "security_events": security_events or [],
        }
