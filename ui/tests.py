from unittest.mock import patch

from django.template.loader import get_template
from django.test import RequestFactory, SimpleTestCase
from django_components import registry

from ui.components.formation_learning_outcomes.formation_learning_outcomes import (
    FormationLearningOutcomes,
)
from ui.components.ui.button.button import Button
from ui.views import gallery


class ComponentTemplateTests(SimpleTestCase):
    def test_every_registered_component_template_compiles(self):
        failures = []

        for name, component_class in sorted(registry.all().items()):
            try:
                template_name = component_class.template_name
                if template_name:
                    get_template(template_name)
            except Exception as exc:  # pragma: no cover - assertion reports details
                failures.append(f"{name}: {type(exc).__name__}: {exc}")

        self.assertEqual(failures, [], "\n".join(failures))

    def test_gallery_renders(self):
        with (
            patch("core.context_processors.Institution.objects.filter") as institution_filter,
            patch("core.context_processors.SiteConfiguration.objects.first") as site_configuration_first,
        ):
            institution_filter.return_value.first.return_value = None
            site_configuration_first.return_value = None
            response = gallery(RequestFactory().get("/ui/galerie/"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Galerie des composants UI")

    def test_button_defaults_to_a_real_button(self):
        html = Button.render(kwargs={"label": "Enregistrer"})

        self.assertIn("<button", html)
        self.assertNotIn('href="#"', html)

    def test_learning_outcomes_builds_items(self):
        html = FormationLearningOutcomes.render(
            kwargs={"learning_outcomes": "Premier objectif\n\nDeuxième objectif"}
        )

        self.assertIn("Premier objectif", html)
        self.assertIn("Deuxième objectif", html)
