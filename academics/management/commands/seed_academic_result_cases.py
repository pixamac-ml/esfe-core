from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from academics.models import AcademicClass, AcademicEnrollment, AcademicYear, EC, ECGrade, Semester, UE
from admissions.models import Candidature
from branches.models import Branch
from formations.models import Cycle, Diploma, Fee, Filiere, Programme, ProgrammeYear
from inscriptions.models import Inscription
from payments.models import Payment
from students.models import Student


User = get_user_model()


class Command(BaseCommand):
    help = "Cree un jeu de donnees de test pour verifier notes, rattrapage et passages."

    def add_arguments(self, parser):
        parser.add_argument("--branch-code", default="TRESULT")
        parser.add_argument("--year", default="2036-2037")
        parser.add_argument("--level", default="L3", help="L3 par defaut pour montrer le cas Cycle termine.")

    def handle(self, *args, **options):
        branch_code = options["branch_code"].upper()
        year_name = options["year"]
        level = options["level"].upper()

        with transaction.atomic():
            branch = self._branch(branch_code)
            programme = self._programme()
            academic_year = self._academic_year(year_name)
            academic_class = self._class(programme, branch, academic_year, level)
            semesters = self._semesters_and_subjects(academic_class)
            cases = self._students(branch, programme, academic_year, academic_class)
            self._clear_case_grades(cases)
            self._grades(semesters, cases)

        self.stdout.write(self.style.SUCCESS("Seed resultats academiques cree."))
        self.stdout.write(f"Annexe: {branch.name} ({branch.code})")
        self.stdout.write(f"Annee source: {academic_year.name}")
        self.stdout.write(f"Classe source: {academic_class.display_name}")
        self.stdout.write("Etudiants:")
        for key, data in cases.items():
            self.stdout.write(f"- {data['student'].matricule}: {data['label']}")
        self.stdout.write("")
        self.stdout.write("A ouvrir:")
        self.stdout.write("- Dashboard Informaticien > Notes")
        self.stdout.write("- /portal/workflows/reenrollment/")
        self.stdout.write("Filtres: annee source et classe de test ci-dessus.")

    def _branch(self, code):
        branch, _ = Branch.objects.get_or_create(
            code=code,
            defaults={
                "name": f"Annexe Test Resultats {code}",
                "slug": f"annexe-test-resultats-{code.lower()}",
                "city": "Bamako",
                "phone": "+223 70 00 00 01",
                "email": "test.resultats@esfe.local",
            },
        )
        return branch

    def _programme(self):
        cycle, _ = Cycle.objects.get_or_create(
            name="Licence Test Resultats",
            defaults={"min_duration_years": 3, "max_duration_years": 3, "is_active": True},
        )
        diploma, _ = Diploma.objects.get_or_create(
            name="Licence Test Resultats",
            defaults={"level": "superieur"},
        )
        filiere, _ = Filiere.objects.get_or_create(
            name="Filiere Test Resultats",
            defaults={"is_active": True},
        )
        programme, _ = Programme.objects.get_or_create(
            title="Programme Test Resultats",
            defaults={
                "filiere": filiere,
                "cycle": cycle,
                "diploma_awarded": diploma,
                "duration_years": 3,
                "short_description": "Programme de test pour calculs de notes.",
                "description": "Jeu de donnees isole pour verifier notes, rattrapage et passages.",
                "is_active": True,
            },
        )
        year, _ = ProgrammeYear.objects.get_or_create(programme=programme, year_number=3)
        Fee.objects.get_or_create(
            programme_year=year,
            label="Frais annuels test resultats",
            defaults={"amount": 100000, "due_month": "Octobre"},
        )
        return programme

    def _academic_year(self, name):
        start_year = int(name.split("-")[0])
        academic_year, _ = AcademicYear.objects.get_or_create(
            name=name,
            defaults={
                "start_date": date(start_year, 10, 1),
                "end_date": date(start_year + 1, 7, 31),
                "is_active": False,
            },
        )
        return academic_year

    def _class(self, programme, branch, academic_year, level):
        academic_class, _ = AcademicClass.objects.get_or_create(
            programme=programme,
            branch=branch,
            academic_year=academic_year,
            level=level,
            defaults={
                "study_level": "LICENCE" if level.startswith("L") else "MASTER",
                "validation_threshold": Decimal("10.00"),
                "is_active": True,
            },
        )
        updates = []
        if not academic_class.is_active:
            academic_class.is_active = True
            updates.append("is_active")
        if academic_class.validation_threshold != Decimal("10.00"):
            academic_class.validation_threshold = Decimal("10.00")
            updates.append("validation_threshold")
        if updates:
            academic_class.save(update_fields=updates)
        return academic_class

    def _semesters_and_subjects(self, academic_class):
        blueprints = {
            1: [
                ("TR-S1-UE1", "Socle clinique", [("Anatomie test", 3, 3), ("Soins test", 3, 3)]),
                ("TR-S1-UE2", "Sante publique", [("Epidemiologie test", 3, 3), ("Prevention test", 3, 3)]),
            ],
            2: [
                ("TR-S2-UE1", "Pratique avancee", [("Urgences test", 3, 3), ("Stage test", 3, 3)]),
                ("TR-S2-UE2", "Professionnalisation", [("Ethique test", 3, 3), ("Projet test", 3, 3)]),
            ],
        }
        semesters = {}
        for number, ues in blueprints.items():
            semester, _ = Semester.objects.get_or_create(
                academic_class=academic_class,
                number=number,
                defaults={"status": Semester.STATUS_RETAKE_ENTRY, "total_required_credits": Decimal("12.00")},
            )
            if semester.status != Semester.STATUS_RETAKE_ENTRY or semester.total_required_credits != Decimal("12.00"):
                semester.status = Semester.STATUS_RETAKE_ENTRY
                semester.total_required_credits = Decimal("12.00")
                semester.save(update_fields=["status", "total_required_credits"])
            semesters[number] = semester
            for code, title, ecs in ues:
                ue, _ = UE.objects.get_or_create(semester=semester, code=code, defaults={"title": title})
                if ue.title != title:
                    ue.title = title
                    ue.save(update_fields=["title"])
                for ec_title, credit, coefficient in ecs:
                    ec, _ = EC.objects.get_or_create(
                        ue=ue,
                        title=ec_title,
                        defaults={
                            "credit_required": Decimal(str(credit)),
                            "coefficient": Decimal(str(coefficient)),
                        },
                    )
                    if ec.credit_required != Decimal(str(credit)) or ec.coefficient != Decimal(str(coefficient)):
                        ec.credit_required = Decimal(str(credit))
                        ec.coefficient = Decimal(str(coefficient))
                        ec.save(update_fields=["credit_required", "coefficient"])
        return semesters

    def _students(self, branch, programme, academic_year, academic_class):
        specs = {
            "admitted": ("Awa", "Admise", "MAT-TEST-ADMIS", "Toutes les notes valides -> Cycle termine"),
            "incomplete": ("Binta", "Incomplete", "MAT-TEST-INCOMP", "Une note manquante -> resultat incomplet"),
            "retake": ("Cira", "Rattrapage", "MAT-TEST-RATT", "Rattrapage valide -> Cycle termine"),
            "failed": ("Djeneba", "Credits", "MAT-TEST-CREDIT", "Moyenne correcte mais credit manque -> redoublement"),
            "debt": ("Moussa", "Dette", "MAT-TEST-DETTE", "S1 valide et S2 a 9.50 -> passage avec dette si niveau non terminal"),
            "gap": ("Nafi", "Ecart", "MAT-TEST-ECART", "S1 valide et S2 a 9.40 -> ecart trop grand, redoublement"),
        }
        cases = {}
        for key, (first_name, last_name, matricule, label) in specs.items():
            username = f"test_results_{key}"
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": f"{username}@esfe.local",
                },
            )
            if created:
                user.set_password("Test@12345")
                user.save(update_fields=["password"])
            candidature, _ = Candidature.objects.get_or_create(
                email=f"{username}@esfe.local",
                programme=programme,
                academic_year=academic_year.name,
                defaults={
                    "branch": branch,
                    "entry_year": 3,
                    "first_name": first_name,
                    "last_name": last_name,
                    "birth_date": date(2000, 1, 1),
                    "birth_place": "Bamako",
                    "gender": "female",
                    "phone": f"70000{len(cases) + 10}",
                    "status": "accepted",
                },
            )
            if candidature.status != "accepted":
                candidature.status = "accepted"
                candidature.save(update_fields=["status", "updated_at"])
            inscription, _ = Inscription.objects.get_or_create(
                candidature=candidature,
                defaults={
                    "academic_class": academic_class,
                    "academic_level": academic_class.level,
                    "amount_due": 100000,
                    "status": Inscription.STATUS_ACTIVE,
                },
            )
            updates = []
            if inscription.academic_class_id != academic_class.id:
                inscription.academic_class = academic_class
                updates.append("academic_class")
            if inscription.academic_level != academic_class.level:
                inscription.academic_level = academic_class.level
                updates.append("academic_level")
            if inscription.status != Inscription.STATUS_ACTIVE:
                inscription.status = Inscription.STATUS_ACTIVE
                updates.append("status")
            if updates:
                updates.append("updated_at")
                inscription.save(update_fields=updates)
            Payment.objects.get_or_create(
                inscription=inscription,
                amount=100000,
                method=Payment.METHOD_CASH,
                status=Payment.STATUS_VALIDATED,
                defaults={"reference": f"PAY-{matricule}"},
            )
            inscription.update_financial_state()
            student, _ = Student.objects.get_or_create(
                user=user,
                defaults={"inscription": inscription, "matricule": matricule, "is_active": True},
            )
            student.inscription = inscription
            student.matricule = matricule
            student.is_active = True
            student.save(update_fields=["inscription", "matricule", "is_active"])
            enrollment, _ = AcademicEnrollment.objects.get_or_create(
                inscription=inscription,
                defaults={
                    "student": user,
                    "programme": programme,
                    "branch": branch,
                    "academic_year": academic_year,
                    "academic_class": academic_class,
                    "status": AcademicEnrollment.STATUS_ACTIVE,
                },
            )
            if enrollment.status != AcademicEnrollment.STATUS_ACTIVE:
                enrollment.status = AcademicEnrollment.STATUS_ACTIVE
                enrollment.academic_class = academic_class
                enrollment.academic_year = academic_year
                enrollment.save(update_fields=["status", "academic_class", "academic_year"])
            student.current_academic_enrollment = enrollment
            student.save(update_fields=["current_academic_enrollment"])
            cases[key] = {"student": student, "enrollment": enrollment, "label": label}
        return cases

    def _clear_case_grades(self, cases):
        enrollment_ids = [case["enrollment"].id for case in cases.values()]
        ECGrade.objects.filter(enrollment_id__in=enrollment_ids).delete()

    def _grades(self, semesters, cases):
        semester_ecs = {
            number: list(EC.objects.filter(ue__semester=semester).order_by("ue__code", "id"))
            for number, semester in semesters.items()
        }
        admitted_scores = [Decimal("14.00"), Decimal("13.00"), Decimal("15.00"), Decimal("12.00")]
        retake_normal = [Decimal("14.00"), Decimal("8.00"), Decimal("13.00"), Decimal("9.00")]
        failed_scores = [Decimal("20.00"), Decimal("20.00"), Decimal("8.00"), Decimal("8.00")]
        debt_scores = {
            1: [Decimal("10.00"), Decimal("10.00"), Decimal("10.00"), Decimal("10.00")],
            2: [Decimal("9.50"), Decimal("9.50"), Decimal("9.50"), Decimal("9.50")],
        }
        gap_scores = {
            1: [Decimal("10.00"), Decimal("10.00"), Decimal("10.00"), Decimal("10.00")],
            2: [Decimal("9.40"), Decimal("9.40"), Decimal("9.40"), Decimal("9.40")],
        }

        for semester_number, ecs in semester_ecs.items():
            for idx, ec in enumerate(ecs):
                self._grade(cases["admitted"]["enrollment"], ec, admitted_scores[idx % len(admitted_scores)])
                if not (semester_number == 2 and idx == len(ecs) - 1):
                    self._grade(cases["incomplete"]["enrollment"], ec, admitted_scores[idx % len(admitted_scores)])
                normal = retake_normal[idx % len(retake_normal)]
                retake = Decimal("12.00") if normal < Decimal("10.00") else None
                self._grade(cases["retake"]["enrollment"], ec, normal, retake)
                self._grade(cases["failed"]["enrollment"], ec, failed_scores[idx % len(failed_scores)])
                self._grade(cases["debt"]["enrollment"], ec, debt_scores[semester_number][idx % len(debt_scores[semester_number])])
                self._grade(cases["gap"]["enrollment"], ec, gap_scores[semester_number][idx % len(gap_scores[semester_number])])

    def _grade(self, enrollment, ec, normal_score, retake_score=None):
        ECGrade.objects.update_or_create(
            enrollment=enrollment,
            ec=ec,
            defaults={
                "normal_score": normal_score,
                "retake_score": retake_score,
            },
        )
