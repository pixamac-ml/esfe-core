from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase

from academics.services.director_monitoring_service import build_director_semester_monitoring


def _section(status="ok", message="Pret.", action="Aucune action."):
    return {"status": status, "message": message, "action": action}


class DirectorMonitoringServiceTests(SimpleTestCase):
    def setUp(self):
        self.actor = SimpleNamespace(id=1)
        self.academic_class = SimpleNamespace(
            id=10,
            branch=SimpleNamespace(id=2),
            programme_id=3,
            programme="Licence test",
            display_name="L1 test",
        )
        self.semester = SimpleNamespace(id=20, number=1, academic_class=self.academic_class)
        self.readiness = {
            "calendrier": _section(),
            "programme": _section(),
            "enseignants": _section(),
            "emploi_du_temps": _section(),
        }
        self.progress = {
            "planned_courses": 4,
            "completed_courses": 3,
            "not_completed_courses": 1,
            "postponed_courses": 0,
            "completed_hours": 6,
            "planned_hours": 8,
            "remaining_hours": 2,
        }

    @patch("academics.services.director_monitoring_service.get_results_summary")
    @patch("academics.services.director_monitoring_service.get_exam_events")
    @patch("academics.services.director_monitoring_service.get_teacher_absences")
    @patch("academics.services.director_monitoring_service.get_course_progress")
    @patch("academics.services.director_monitoring_service.build_timetable_overview")
    @patch("academics.services.director_monitoring_service.build_semester_readiness")
    @patch("academics.services.director_monitoring_service.require_timetable_access")
    def test_indicators_alerts_and_read_only_summary(
        self, access, readiness, timetable, progress, absences, exams, results
    ):
        readiness.return_value = self.readiness
        timetable.return_value = {"state": "published"}
        progress.return_value = self.progress
        absences.return_value = MagicMock(exists=lambda: True, count=lambda: 1)
        exams.return_value = MagicMock(exists=lambda: False, count=lambda: 0)
        results.return_value = {
            "imported_grades": 12,
            "validated_results": 10,
            "published_bulletins": 0,
            "generated_bulletins": 10,
        }

        report = build_director_semester_monitoring(actor=self.actor, semester=self.semester)

        access.assert_called_once_with(self.actor, self.academic_class.branch)
        readiness.assert_called_once_with(actor=self.actor, semester=self.semester)
        self.assertTrue(report["read_only"])
        self.assertEqual(report["indicateurs"]["examens"]["statut"], "Bloqué")
        self.assertEqual(report["indicateurs"]["progression_cours"]["statut"], "Attention")
        self.assertEqual(report["indicateurs"]["notes_importees"]["statut"], "OK")
        self.assertEqual(len(report["alertes_bloquantes"]), 1)
        self.assertTrue(report["actions_prioritaires"])
        for indicator in report["indicateurs"].values():
            self.assertTrue({"statut", "couleur", "message", "action_recommandee"} <= indicator.keys())

    @patch("academics.services.director_monitoring_service.require_timetable_access")
    def test_permission_denial_is_propagated_before_any_read(self, access):
        access.side_effect = PermissionDenied("Acces refuse a cette annexe.")
        with self.assertRaises(PermissionDenied):
            build_director_semester_monitoring(actor=self.actor, semester=self.semester)

    @patch("academics.services.director_monitoring_service.get_results_summary")
    @patch("academics.services.director_monitoring_service.get_exam_events")
    @patch("academics.services.director_monitoring_service.get_teacher_absences")
    @patch("academics.services.director_monitoring_service.get_course_progress")
    @patch("academics.services.director_monitoring_service.build_timetable_overview")
    @patch("academics.services.director_monitoring_service.build_semester_readiness")
    @patch("academics.services.director_monitoring_service.require_timetable_access")
    def test_coherent_all_ok_summary(
        self, access, readiness, timetable, progress, absences, exams, results
    ):
        readiness.return_value = self.readiness
        timetable.return_value = {"state": "published"}
        progress.return_value = {**self.progress, "completed_courses": 4, "not_completed_courses": 0, "remaining_hours": 0}
        absences.return_value = MagicMock(exists=lambda: False, count=lambda: 0)
        exams.return_value = MagicMock(exists=lambda: True, count=lambda: 2)
        results.return_value = {
            "imported_grades": 12,
            "validated_results": 12,
            "published_bulletins": 12,
            "generated_bulletins": 12,
        }

        report = build_director_semester_monitoring(actor=self.actor, semester=self.semester)

        self.assertEqual(report["statut_global"]["statut"], "OK")
        self.assertFalse(report["alertes_bloquantes"])
        self.assertFalse(report["anomalies_pedagogiques"])
