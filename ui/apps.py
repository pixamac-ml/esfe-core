from django.apps import AppConfig


class UiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ui"

    def ready(self):
        # The UI app is the single owner of component registration.
        import ui.components  # noqa: F401
