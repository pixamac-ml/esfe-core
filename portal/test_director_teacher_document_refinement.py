from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from academics.models import AcademicClass, AcademicYear, EC, Semester, UE
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme
from portal.models import AdministrativeDocument, DirectorTeacherAssignment, TeacherDocument


class DirectorTeacherDocumentRefinementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(name="Annexe DE", code="ADE", slug="annexe-de")
        cls.other_branch = Branch.objects.create(name="Annexe Cachee", code="ACH", slug="annexe-cachee")
        cycle = Cycle.objects.create(name="Cycle DE", min_duration_years=1, max_duration_years=4)
        diploma = Diploma.objects.create(name="Diplome DE", level="superieur")
        filiere = Filiere.objects.create(name="Filiere DE")
        programme = Programme.objects.create(
            title="Gestion pedagogique",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="Programme DE",
            description="Programme de test du DE.",
        )
        academic_year = AcademicYear.objects.create(
            name="2030-2031",
            start_date=date(2030, 10, 1),
            end_date=date(2031, 7, 31),
            is_active=True,
        )
        cls.academic_class = AcademicClass.objects.create(
            name="L1 Annexe DE",
            programme=programme,
            branch=cls.branch,
            academic_year=academic_year,
            level="L1",
            study_level="LICENCE",
        )
        cls.other_class = AcademicClass.objects.create(
            name="L1 Annexe Cachee",
            programme=programme,
            branch=cls.other_branch,
            academic_year=academic_year,
            level="L1",
            study_level="LICENCE",
        )
        semester = Semester.objects.create(academic_class=cls.academic_class, number=1)
        other_semester = Semester.objects.create(academic_class=cls.other_class, number=1)
        ue = UE.objects.create(semester=semester, code="UE-DE", title="UE DE")
        other_ue = UE.objects.create(semester=other_semester, code="UE-X", title="UE cachee")
        cls.ec = EC.objects.create(ue=ue, title="Matiere DE", credit_required=3, coefficient=2)
        cls.other_ec = EC.objects.create(ue=other_ue, title="Matiere cachee", credit_required=3, coefficient=2)

        User = get_user_model()
        cls.director = User.objects.create_user(username="director_refinement", password="password")
        cls.director.profile.position = "director_of_studies"
        cls.director.profile.role = "executive"
        cls.director.profile.branch = cls.branch
        cls.director.profile.save(update_fields=["position", "role", "branch", "updated_at"])
        cls.teacher = cls._teacher("teacher_visible", cls.branch, "Visible Professeur")
        cls.other_teacher = cls._teacher("teacher_hidden", cls.other_branch, "Cache Professeur")
        cls.document = AdministrativeDocument.objects.create(
            branch=cls.branch,
            doc_type=AdministrativeDocument.TYPE_NOTE_SERVICE,
            reference="DE/001",
            title="Document visible",
            recipients="Equipe pedagogique",
            body="Contenu visible",
            created_by=cls.director,
        )
        cls.other_document = AdministrativeDocument.objects.create(
            branch=cls.other_branch,
            doc_type=AdministrativeDocument.TYPE_AVIS,
            title="Document cache",
            body="Contenu cache",
        )

    @classmethod
    def _teacher(cls, username, branch, full_name):
        first_name, last_name = full_name.split(" ", 1)
        user = get_user_model().objects.create_user(
            username=username,
            email=f"{username}@test.test",
            first_name=first_name,
            last_name=last_name,
            password="password",
        )
        user.profile.position = "teacher"
        user.profile.role = "teacher"
        user.profile.branch = branch
        user.profile.save(update_fields=["position", "role", "branch", "updated_at"])
        return user

    def setUp(self):
        self.client.force_login(self.director)

    def test_teacher_workspace_and_directory_are_branch_scoped(self):
        response = self.client.get(
            reverse("accounts_portal:director_workspace"), {"section": "enseignants"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Répertoire")
        self.assertContains(response, "Affectations")
        self.assertContains(response, "Dossiers")
        self.assertNotContains(response, "Transferts")

        transfers = self.client.get(
            reverse("accounts_portal:director_workspace"), {"section": "transferts"}
        )
        self.assertContains(transfers, "Transferts")
        self.assertContains(transfers, "Nouveau transfert")

        directory = self.client.get(
            reverse("accounts_portal:director_teachers_subcontent"),
            {"view": "directory"},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(directory, "Visible Professeur")
        self.assertNotContains(directory, "Cache Professeur")
        self.assertIn("view=directory", directory.headers["HX-Push-Url"])

    def test_invalid_teacher_creation_keeps_entered_values(self):
        response = self.client.post(
            reverse("accounts_portal:director_teacher_create"),
            {"first_name": "Awa", "last_name": "Keita", "email": "incorrect"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Awa"')
        self.assertContains(response, 'value="Keita"')
        self.assertContains(response, "Saisissez une adresse de courriel valide")

    def test_ec_options_and_assignment_reject_cross_branch_targets(self):
        options = self.client.get(
            reverse("accounts_portal:director_teacher_ec_options"),
            {"mode": "assignment", "class_id": self.academic_class.pk},
        )
        self.assertContains(options, self.ec.title)
        self.assertNotContains(options, self.other_ec.title)

        response = self.client.post(
            reverse("accounts_portal:director_teacher_assign"),
            {
                "teacher_id": self.teacher.pk,
                "class_id": self.other_class.pk,
                "ec_id": self.other_ec.pk,
                "room_label": "Salle X",
                "planned_hours": "12",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DirectorTeacherAssignment.objects.filter(teacher=self.teacher).exists())

    def test_teacher_document_upload_and_review_are_branch_scoped(self):
        upload = self.client.post(
            reverse("accounts_portal:director_teacher_document_upload"),
            {
                "teacher_id": self.teacher.pk,
                "document_type": TeacherDocument.DOCUMENT_DIPLOMA,
                "note": "Original",
                "file": SimpleUploadedFile("diplome.pdf", b"pdf", content_type="application/pdf"),
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(upload.status_code, 200)
        self.assertEqual(upload.headers["HX-Retarget"], "#director-teacher-subcontent")
        document = TeacherDocument.objects.get(teacher=self.teacher)

        review = self.client.post(
            reverse("accounts_portal:director_teacher_document_review"),
            {"teacher_id": self.teacher.pk, "document_id": document.pk, "action": "verify"},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(review, "Vérifié")
        document.refresh_from_db()
        self.assertTrue(document.is_verified)

        invalid = self.client.post(
            reverse("accounts_portal:director_teacher_document_upload"),
            {
                "teacher_id": self.other_teacher.pk,
                "document_type": TeacherDocument.DOCUMENT_CV,
                "file": SimpleUploadedFile("cv.pdf", b"pdf", content_type="application/pdf"),
            },
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertFalse(TeacherDocument.objects.filter(teacher=self.other_teacher).exists())

    def test_document_archives_and_draft_editing_are_branch_scoped(self):
        archives = self.client.get(
            reverse("accounts_portal:director_documents_subcontent"),
            {"view": "archives"},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(archives, self.document.title)
        self.assertNotContains(archives, self.other_document.title)

        edit_cross_branch = self.client.get(
            reverse("accounts_portal:director_correspondance_create"),
            {"document_id": self.other_document.pk},
        )
        self.assertEqual(edit_cross_branch.status_code, 400)

        publish_cross_branch = self.client.post(
            reverse("accounts_portal:director_correspondance_publish", args=[self.other_document.pk])
        )
        self.assertEqual(publish_cross_branch.status_code, 400)

    def test_document_form_keeps_values_and_supports_draft_then_publish(self):
        invalid = self.client.post(
            reverse("accounts_portal:director_correspondance_create"),
            {
                "doc_type": AdministrativeDocument.TYPE_LETTRE,
                "reference": "DE/099",
                "title": "Objet conserve",
                "recipients": "Enseignants",
                "body": "",
                "action": "draft",
            },
        )
        self.assertContains(invalid, 'value="Objet conserve"')
        self.assertContains(invalid, "Ce champ est obligatoire")

        created = self.client.post(
            reverse("accounts_portal:director_correspondance_create"),
            {
                "doc_type": AdministrativeDocument.TYPE_LETTRE,
                "reference": "DE/100",
                "title": "Nouvelle lettre",
                "recipients": "Enseignants",
                "body": "Contenu de la lettre",
                "action": "draft",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(created.headers["HX-Retarget"], "#director-document-subcontent")
        document = AdministrativeDocument.objects.get(reference="DE/100")
        self.assertEqual(document.branch, self.branch)
        self.assertEqual(document.status, AdministrativeDocument.STATUS_DRAFT)

        published = self.client.post(
            reverse("accounts_portal:director_correspondance_publish", args=[document.pk]),
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(published, "Document publie")
        document.refresh_from_db()
        self.assertEqual(document.status, AdministrativeDocument.STATUS_PUBLISHED)
