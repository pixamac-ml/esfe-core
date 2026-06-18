"""
Tests carte étudiant ESFE.
Lance avec : python manage.py test students.tests_carte --settings=config.settings_test_local
"""

from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings

FAKE_KEY = "test-signing-key-esfe-2026"


@override_settings(CARD_SIGNING_KEY=FAKE_KEY)
class CardSecurityTests(TestCase):
    """Vérifie le socle HMAC : signature, vérification, code lisible."""

    def test_signer_et_verifier_token(self):
        from students.services.card_security import signer_carte, verifier_token

        token = signer_carte("ESFE-00001", "2026-2027", "BKO-MORIBA")
        self.assertTrue(token.startswith("v1."))
        payload = verifier_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["matricule"], "ESFE-00001")
        self.assertEqual(payload["annee"], "2026-2027")
        self.assertEqual(payload["annexe"], "BKO-MORIBA")

    def test_token_falsifie_rejete(self):
        from students.services.card_security import signer_carte, verifier_token

        token = signer_carte("ESFE-00001", "2026-2027", "BKO-MORIBA")
        parties = token.split(".")
        # Modifier la signature
        token_falsifie = f"{parties[0]}.{parties[1]}.AAAA"
        self.assertIsNone(verifier_token(token_falsifie))

    def test_token_format_invalide(self):
        from students.services.card_security import verifier_token

        self.assertIsNone(verifier_token("pas-un-token"))
        self.assertIsNone(verifier_token(""))
        self.assertIsNone(verifier_token("v2.abc.def"))  # mauvaise version

    def test_code_lisible_format(self):
        from students.services.card_security import generer_code_lisible, signer_carte

        token = signer_carte("ESFE-00001", "2026-2027", "BKO-MORIBA")
        code = generer_code_lisible(token)
        self.assertRegex(code, r"^[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}$")

    def test_code_lisible_deterministe(self):
        from students.services.card_security import generer_code_lisible, signer_carte

        token = signer_carte("ESFE-00001", "2026-2027", "BKO-MORIBA")
        self.assertEqual(generer_code_lisible(token), generer_code_lisible(token))

    def test_codes_differents_pour_etudiants_differents(self):
        from students.services.card_security import generer_code_lisible, signer_carte

        t1 = signer_carte("ESFE-00001", "2026-2027", "BKO-MORIBA")
        t2 = signer_carte("ESFE-00002", "2026-2027", "BKO-MORIBA")
        self.assertNotEqual(generer_code_lisible(t1), generer_code_lisible(t2))

    def test_qr_data_uri_png(self):
        from students.services.card_security import generer_qr_data_uri

        uri = generer_qr_data_uri("https://esfe-mali.org/carte/v/v1.abc.def")
        self.assertTrue(uri.startswith("data:image/png;base64,"))
        self.assertGreater(len(uri), 100)


@override_settings(CARD_SIGNING_KEY=FAKE_KEY)
class CarteEtudiantModelTests(TestCase):
    """Vérifie is_valide et revoquer."""

    def _make_carte(self, statut="active", delta_days=30):
        from students.models import CarteEtudiant, Student
        from django.contrib.auth import get_user_model
        from admissions.models import Candidature
        from inscriptions.models import Inscription
        from branches.models import Branch
        from formations.models import Programme

        User = get_user_model()
        # Minimal objects — utilise get_or_create pour éviter les doublons
        branch, _ = Branch.objects.get_or_create(
            code="TST",
            defaults={"name": "Annexe Test", "slug": "annexe-test"},
        )
        programme = Programme.objects.first()
        if not programme:
            self.skipTest("Aucun programme en base — seed requis.")

        user = User.objects.create_user(username=f"testcarte_{delta_days}_{statut}", password="x")
        candidature = Candidature.objects.create(
            programme=programme,
            branch=branch,
            academic_year="2026-2027",
            first_name="Test",
            last_name="Carte",
            birth_date=date(2000, 1, 1),
            birth_place="Bamako",
            gender="male",
            phone="00000000",
            email=f"test_{delta_days}_{statut}@esfe.ml",
            status="accepted",
        )
        inscription = Inscription.objects.create(
            candidature=candidature,
            status="active",
        )
        student = Student.objects.create(
            user=user,
            inscription=inscription,
            matricule=f"ESFE-TST-{delta_days}-{statut}",
        )
        carte = CarteEtudiant.objects.create(
            etudiant=student,
            annee="2026-2027",
            code_annexe="BKO-MORIBA",
            date_expiration=date.today() + timedelta(days=delta_days),
            statut=statut,
        )
        return carte

    def test_carte_active_valide(self):
        carte = self._make_carte(statut="active", delta_days=30)
        self.assertTrue(carte.is_valide)

    def test_carte_expiree_invalide(self):
        carte = self._make_carte(statut="active", delta_days=-1)
        self.assertFalse(carte.is_valide)

    def test_carte_revoquee_invalide(self):
        carte = self._make_carte(statut="revoquee", delta_days=30)
        self.assertFalse(carte.is_valide)

    def test_revoquer(self):
        carte = self._make_carte(statut="active", delta_days=30)
        carte.revoquer("perdue")
        carte.refresh_from_db()
        self.assertEqual(carte.statut, "perdue")
        self.assertFalse(carte.is_valide)


@override_settings(CARD_SIGNING_KEY=FAKE_KEY)
class StudentPinTests(TestCase):
    """Vérifie set_pin / check_pin / has_pin."""

    def _make_student(self):
        from students.models import Student
        from django.contrib.auth import get_user_model
        from admissions.models import Candidature
        from inscriptions.models import Inscription
        from branches.models import Branch
        from formations.models import Programme

        User = get_user_model()
        branch, _ = Branch.objects.get_or_create(
            code="TST2",
            defaults={"name": "Annexe Test2", "slug": "annexe-test2"},
        )
        programme = Programme.objects.first()
        if not programme:
            self.skipTest("Aucun programme en base — seed requis.")

        user = User.objects.create_user(username="testpin_student", password="x")
        candidature = Candidature.objects.create(
            programme=programme, branch=branch, academic_year="2026-2027",
            first_name="Pin", last_name="Test", birth_date=date(2000, 1, 1),
            birth_place="Bamako", gender="male", phone="00000000",
            email="pin_test@esfe.ml", status="accepted",
        )
        inscription = Inscription.objects.create(candidature=candidature, status="active")
        return Student.objects.create(user=user, inscription=inscription, matricule="ESFE-PIN-001")

    def test_no_pin_par_defaut(self):
        s = self._make_student()
        self.assertFalse(s.has_pin)
        self.assertFalse(s.check_pin("1234"))

    def test_set_et_check_pin(self):
        s = self._make_student()
        s.set_pin("1234")
        s.refresh_from_db()
        self.assertTrue(s.has_pin)
        self.assertTrue(s.check_pin("1234"))
        self.assertFalse(s.check_pin("0000"))

    def test_pin_hash_non_en_clair(self):
        s = self._make_student()
        s.set_pin("5678")
        s.refresh_from_db()
        self.assertNotEqual(s.pin_hash, "5678")
        self.assertNotIn("5678", s.pin_hash)


@override_settings(CARD_SIGNING_KEY=FAKE_KEY)
class RateLimitingTests(TestCase):
    """Vérifie le rate limiting PIN et portail."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()

    def test_pin_rate_limit(self):
        from students.services.card_security import (
            carte_pin_verrouillee,
            incrementer_tentatives_pin,
            reinitialiser_tentatives_pin,
        )

        for _ in range(5):
            incrementer_tentatives_pin(carte_id=42)
        self.assertTrue(carte_pin_verrouillee(42))

    def test_reinitialiser_debarre(self):
        from students.services.card_security import (
            carte_pin_verrouillee,
            incrementer_tentatives_pin,
            reinitialiser_tentatives_pin,
        )

        for _ in range(5):
            incrementer_tentatives_pin(carte_id=99)
        reinitialiser_tentatives_pin(99)
        self.assertFalse(carte_pin_verrouillee(99))

    def test_verif_rate_limit(self):
        from students.services.card_security import verif_rate_limitee

        ip = "1.2.3.4"
        for _ in range(10):
            verif_rate_limitee(ip)
        self.assertTrue(verif_rate_limitee(ip))


@override_settings(CARD_SIGNING_KEY=FAKE_KEY)
class PortailVerificationViewTests(TestCase):
    """Vérifie les URLs du portail de vérification (GET/POST)."""

    def test_portail_get(self):
        resp = self.client.get("/students/carte/verifier/")
        self.assertEqual(resp.status_code, 200)

    def test_portail_code_invalide(self):
        resp = self.client.post("/students/carte/verifier/", {"code": "0000-0000-0000"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "invalide")

    def test_portail_token_invalide(self):
        resp = self.client.get("/students/carte/v/token-bidon/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "non authentique")
