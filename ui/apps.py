from django.apps import AppConfig

class UiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ui"

    def ready(self):
        import ui.components  # 👈 IMPORTANT
