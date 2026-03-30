from django.apps import AppConfig


class CommunityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "community"
    verbose_name = "Communauté"

    def ready(self):
        # Ensure signal receivers (XP/gamification hooks) are registered at startup.
        from . import signals  # noqa: F401
