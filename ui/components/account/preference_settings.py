from django_components import component


@component.register("account.preference_settings")
class PreferenceSettings(component.Component):
    template_name = "account/preference_settings.html"

    def get_context_data(
        self,
        form=None,
        hx_post="",
        hx_target="",
        notification_preferences=None,
        **kwargs,
    ):
        return {
            "form": form,
            "hx_post": hx_post,
            "hx_target": hx_target,
            "notification_preferences": notification_preferences or [],
        }
