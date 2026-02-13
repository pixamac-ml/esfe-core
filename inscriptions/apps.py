# inscriptions/apps.py
from django.apps import AppConfig

class InscriptionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "inscriptions"

    def ready(self):
        import inscriptions.signals
