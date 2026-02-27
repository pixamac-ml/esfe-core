from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        import ui.components.layout.section.section
        import ui.components.layout.navbar.navbar
        import ui.components.cards.base_card.base_card
        import ui.components.ui.button.button
        import ui.components.about.hero
        import ui.components.about.sections