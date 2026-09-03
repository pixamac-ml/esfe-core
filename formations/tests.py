from django.test import TestCase

from .models import Cycle, Diploma, Filiere, Programme


class ProgrammeCatalogueStateTests(TestCase):
    def setUp(self):
        self.cycle = Cycle.objects.create(
            name="Licence test", min_duration_years=3, max_duration_years=3,
        )
        self.filiere = Filiere.objects.create(name="Filière test")
        self.diploma = Diploma.objects.create(name="Diplôme test", level="superieur")

    def programme(self, **overrides):
        values = {
            "title": "Programme test",
            "filiere": self.filiere,
            "cycle": self.cycle,
            "diploma_awarded": self.diploma,
            "duration_years": 3,
            "short_description": "Description de test",
            "description": "Description complète de test",
        }
        values.update(overrides)
        return Programme.objects.create(**values)

    def test_public_and_admissions_states_are_distinct(self):
        programme = self.programme()
        self.assertIn(programme, Programme.objects.public())
        self.assertIn(programme, Programme.objects.accepting_admissions())

        programme.admissions_open = False
        programme.save(update_fields=["admissions_open"])
        self.assertIn(programme, Programme.objects.public())
        self.assertNotIn(programme, Programme.objects.accepting_admissions())

    def test_archive_preserves_record_and_hides_it_from_public_flows(self):
        programme = self.programme()
        programme.archive()
        programme.refresh_from_db()
        self.assertTrue(programme.is_archived)
        self.assertFalse(programme.is_active)
        self.assertFalse(programme.admissions_open)
        self.assertIsNotNone(programme.archived_at)
        self.assertNotIn(programme, Programme.objects.public())

# Create your tests here.
