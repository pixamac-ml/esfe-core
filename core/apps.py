from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        import ui.components.atoms.icon
        import ui.components.atoms.label
        import ui.components.atoms.avatar
        import ui.components.atoms.pill
        import ui.components.dashboard.form_field
        import ui.components.dashboard.search_bar
        import ui.components.dashboard.tabs
        import ui.components.dashboard.kpi_row
        import ui.components.dashboard.data_table
        import ui.components.dashboard.toast
        import ui.components.layout.section.section
        import ui.components.layout.navbar.navbar
        import ui.components.cards.base_card.base_card
        import ui.components.ui.button.button
        import ui.components.about.about_hero
        import ui.components.about.about_staff
        import ui.components.about.about_presentation
        import ui.components.about.about_values
        import ui.components.about.about_stats
        import ui.components.about.about_cta
        import ui.components.grades.maquette.maquette