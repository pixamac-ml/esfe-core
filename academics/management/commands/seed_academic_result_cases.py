from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from academics.models import (
    AcademicCalendar,
    AcademicCalendarEntry,
    AcademicClass,
    AcademicEnrollment,
    AcademicScheduleEvent,
    AcademicYear,
    EC,
    ECGrade,
    Semester,
    UE,
)
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
        parser.add_argument(
            "--pilot-moribabougou",
            action="store_true",
            help="Complete de facon idempotente le scenario annuel reel PILOTE ISMI - L1 (2099-2100).",
        )

    def handle(self, *args, **options):
        if options["pilot_moribabougou"]:
            self._seed_pilot_moribabougou()
            return
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

    def _seed_pilot_moribabougou(self):
        """Raccorde le cas pilote existant sans toucher a son historique S1.

        Cette variante vit dans la commande institutionnelle deja destinee aux
        cas de resultats : elle ne cree ni identite etudiante ni maquette.
        Les ecritures de notes utilisent ECGrade (source de saisie) puis les
        transitions IT/DE existantes afin que les snapshots et releves restent
        produits par le workflow normal.
        """
        from accounts.models import Profile
        from academic_cycle.services.activation_service import activate_academic_year_for_branch
        from academics.services.calendar_service import (
            create_calendar,
            create_calendar_entry,
            publish_calendar,
            submit_calendar,
            validate_calendar,
        )
        from academics.services.schedule_service import create_schedule_event, create_weekly_schedule_slot
        from academics.services.teacher_assignment_service import create_teacher_assignment
        from portal.services.notes_workflow import (
            ACTION_ACTIVATE_RETAKE,
            ACTION_PUBLISH_NORMAL,
            ACTION_START,
            ACTION_SUBMIT_TO_DIRECTOR,
            apply_notes_workflow_action,
            get_retake_candidates,
        )
        from portal.views.views import director_results_action
        from django.test.client import RequestFactory
        from django.contrib.sessions.middleware import SessionMiddleware

        branch = Branch.objects.get(code="MBG")
        academic_year = AcademicYear.objects.get(name="2099-2100")
        academic_class = AcademicClass.objects.get(
            branch=branch,
            academic_year=academic_year,
            name="PILOTE ISMI - L1",
        )
        director = Profile.objects.select_related("user").get(
            branch=branch,
            position="director_of_studies",
            user__is_active=True,
        ).user
        technician = Profile.objects.select_related("user").get(
            branch=branch,
            position="it_support",
            user__is_active=True,
        ).user
        teacher = Profile.objects.select_related("user").get(
            branch=branch,
            position="teacher",
            user__is_active=True,
        ).user
        semesters = {semester.number: semester for semester in Semester.objects.filter(academic_class=academic_class)}
        semester_1, semester_2 = semesters[1], semesters[2]
        enrollments = list(
            AcademicEnrollment.objects.filter(
                academic_class=academic_class,
                academic_year=academic_year,
                is_active=True,
            ).order_by("id")
        )
        if len(enrollments) != 20:
            raise CommandError("Le scenario pilote exige exactement les 20 inscriptions academiques existantes.")

        # Le contexte global est explicitement ouvert pour cette annexe. Aucune
        # autre annee n'est actuellement active dans la base.
        if not academic_year.is_active:
            AcademicYear.objects.filter(is_active=True).exclude(pk=academic_year.pk).update(is_active=False)
            academic_year.is_active = True
            academic_year.save(update_fields=["is_active"])
        cycle = activate_academic_year_for_branch(branch, academic_year, director)
        calendar, calendar_created = self._pilot_calendar(
            branch=branch,
            academic_year=academic_year,
            academic_class=academic_class,
            semester_1=semester_1,
            semester_2=semester_2,
            actor=director,
            create_calendar=create_calendar,
            create_calendar_entry=create_calendar_entry,
            submit_calendar=submit_calendar,
            validate_calendar=validate_calendar,
            publish_calendar=publish_calendar,
        )
        assignments, course_events, weekly_slots = self._pilot_teaching(
            academic_class=academic_class,
            teacher=teacher,
            actor=director,
            create_teacher_assignment=create_teacher_assignment,
            create_schedule_event=create_schedule_event,
            create_weekly_schedule_slot=create_weekly_schedule_slot,
        )

        if semester_2.status != Semester.STATUS_PUBLISHED:
            if semester_2.status == Semester.STATUS_DRAFT:
                apply_notes_workflow_action(
                    actor=technician, academic_class=academic_class, semester=semester_2, action=ACTION_START
                )
            semester_2.refresh_from_db()
            if semester_2.status == Semester.STATUS_NORMAL_ENTRY:
                self._pilot_s2_normal_scores(enrollments=enrollments, semester=semester_2)
                apply_notes_workflow_action(
                    actor=technician, academic_class=academic_class, semester=semester_2, action=ACTION_PUBLISH_NORMAL
                )
            semester_2.refresh_from_db()
            candidates = get_retake_candidates(academic_class=academic_class, semester=semester_2)
            if candidates and semester_2.status == Semester.STATUS_NORMAL_LOCKED:
                apply_notes_workflow_action(
                    actor=technician, academic_class=academic_class, semester=semester_2, action=ACTION_ACTIVATE_RETAKE
                )
            semester_2.refresh_from_db()
            if semester_2.status == Semester.STATUS_RETAKE_ENTRY:
                self._pilot_s2_retake_scores(enrollments=enrollments, semester=semester_2)
                apply_notes_workflow_action(
                    actor=technician, academic_class=academic_class, semester=semester_2, action=ACTION_SUBMIT_TO_DIRECTOR
                )
            elif semester_2.status == Semester.STATUS_NORMAL_LOCKED:
                apply_notes_workflow_action(
                    actor=technician, academic_class=academic_class, semester=semester_2, action=ACTION_SUBMIT_TO_DIRECTOR
                )
            semester_2.refresh_from_db()
            if semester_2.status == Semester.STATUS_READY_FOR_DIRECTOR:
                self._pilot_director_semester_action(director_results_action, director, semester_2.id, "validate", RequestFactory, SessionMiddleware)
                self._pilot_director_semester_action(director_results_action, director, semester_2.id, "publish", RequestFactory, SessionMiddleware)
        semester_2.refresh_from_db()
        if semester_2.status != Semester.STATUS_PUBLISHED:
            raise CommandError("S2 n'a pas pu etre publie par le workflow officiel.")

        # Les propositions sont volontaires, revues manuellement et ne sont
        # jamais finalisees ici. Le DE conserve l'ouverture de la deliberation
        # et l'envoi de la demande OTP comme actions explicites du dashboard.
        from academics.services.annual_deliberation import prepare_class_annual_synthesis
        prepared = prepare_class_annual_synthesis(academic_class=academic_class, actor=director)

        retake_count = sum(len(item.failed_subjects) for item in get_retake_candidates(academic_class=academic_class, semester=semester_2))
        self.stdout.write(self.style.SUCCESS("Scenario annuel pilote pret."))
        self.stdout.write(
            f"cycle={cycle.status}; calendrier={calendar.id} ({'cree' if calendar_created else 'existant'}); "
            f"affectations={assignments}; seances={course_events}; creneaux={weekly_slots}; "
            f"S2={semester_2.status}; propositions={len(prepared['prepared'])}; rattrapages_restants={retake_count}"
        )

    def _pilot_calendar(self, *, branch, academic_year, academic_class, semester_1, semester_2, actor,
                        create_calendar, create_calendar_entry, submit_calendar, validate_calendar, publish_calendar):
        calendar = AcademicCalendar.objects.filter(
            branch=branch, academic_year=academic_year, status=AcademicCalendar.STATUS_PUBLISHED
        ).first()
        created = False
        if calendar is None:
            calendar = create_calendar(actor=actor, branch=branch, academic_year=academic_year)
            calendar.official_title = "Calendrier académique pilote ISMI 2099-2100"
            calendar.administrative_reference = "ESFE-MBG-2099-2100-PILOTE"
            calendar.general_observations = "Scénario institutionnel de préparation à la délibération annuelle."
            calendar.updated_by = actor
            calendar.save()
            created = True
        if calendar.status in {AcademicCalendar.STATUS_DRAFT, AcademicCalendar.STATUS_REJECTED}:
            def at(value):
                return timezone.make_aware(datetime.combine(value, time(8, 0)))
            def end(value):
                return timezone.make_aware(datetime.combine(value, time(17, 0)))
            timeline = [
                ("Rentrée académique 2099-2100", "academic_start", date(2099, 10, 1), date(2099, 10, 1), "branch", None, False),
                ("Enseignements S1", "semester_start", date(2099, 10, 5), date(2099, 10, 5), "semester", semester_1, False),
                ("Évaluations normales S1", "exam_session", date(2100, 1, 11), date(2100, 1, 20), "semester", semester_1, True),
                ("Rattrapages S1", "retake_session", date(2100, 2, 1), date(2100, 2, 5), "semester", semester_1, True),
                ("Publication résultats S1", "result_publication", date(2100, 2, 10), date(2100, 2, 10), "semester", semester_1, True),
                ("Enseignements S2", "semester_start", date(2100, 2, 15), date(2100, 2, 15), "semester", semester_2, False),
                ("Évaluations normales S2", "exam_session", date(2100, 6, 10), date(2100, 6, 20), "semester", semester_2, True),
                ("Saisie et contrôle des notes S2", "other", date(2100, 6, 21), date(2100, 6, 24), "semester", semester_2, False),
                ("Rattrapages S2", "retake_session", date(2100, 6, 25), date(2100, 6, 29), "semester", semester_2, True),
                ("Jury et préparation annuelle", "jury", date(2100, 7, 2), date(2100, 7, 3), "class", None, True),
                ("Publication résultats S2", "result_publication", date(2100, 7, 5), date(2100, 7, 5), "semester", semester_2, True),
                ("Clôture académique 2099-2100", "academic_end", date(2100, 7, 31), date(2100, 7, 31), "branch", None, False),
            ]
            for title, event_type, start_day, end_day, scope, semester, blocking in timeline:
                if calendar.entries.filter(title=title).exists():
                    continue
                data = {
                    "title": title, "event_type": event_type, "start_datetime": at(start_day),
                    "end_datetime": end(end_day), "all_day": True, "target_scope": scope,
                    "is_blocking": blocking, "status": AcademicCalendarEntry.STATUS_DRAFT,
                }
                if scope == "semester":
                    data["semester"] = semester
                elif scope == "class":
                    data["academic_class"] = academic_class
                create_calendar_entry(actor=actor, calendar=calendar, **data)
            if calendar.status in {AcademicCalendar.STATUS_DRAFT, AcademicCalendar.STATUS_REJECTED}:
                submit_calendar(calendar, actor=actor)
            calendar.refresh_from_db()
            if calendar.status == AcademicCalendar.STATUS_SUBMITTED:
                validate_calendar(calendar, actor=actor)
            calendar.refresh_from_db()
            if calendar.status == AcademicCalendar.STATUS_VALIDATED:
                publish_calendar(calendar, actor=actor)
        return calendar, created

    def _pilot_teaching(self, *, academic_class, teacher, actor, create_teacher_assignment,
                        create_schedule_event, create_weekly_schedule_slot):
        ecs = list(EC.objects.filter(ue__semester__academic_class=academic_class).select_related("ue", "ue__semester").order_by("ue__semester__number", "ue__code", "id"))
        assignments = events = slots = 0
        for index, ec in enumerate(ecs):
            if not __import__("portal.models", fromlist=["DirectorTeacherAssignment"]).DirectorTeacherAssignment.objects.filter(
                academic_class=academic_class, ec=ec, teacher=teacher, is_active=True
            ).exists():
                create_teacher_assignment(
                    actor=actor, teacher=teacher, branch=academic_class.branch, academic_class=academic_class,
                    ec=ec, room_label="Salle pilote ISMI", planned_hours="4", status="active",
                )
                assignments += 1
            weekday = index % 6
            start_hour = 8 + (index // 6) * 2
            if not __import__("academics.models", fromlist=["WeeklyScheduleSlot"]).WeeklyScheduleSlot.objects.filter(
                academic_class=academic_class, ec=ec, teacher=teacher
            ).exists():
                create_weekly_schedule_slot(
                    user=actor, academic_class=academic_class, ec=ec, teacher=teacher,
                    branch=academic_class.branch, academic_year=academic_class.academic_year,
                    weekday=weekday, start_time=time(start_hour, 0), end_time=time(start_hour + 1, 30),
                    room="Salle pilote ISMI", is_active=True,
                )
                slots += 1
            semester_start = date(2099, 10, 12) if ec.ue.semester.number == 1 else date(2100, 2, 22)
            event_day = semester_start + timedelta(days=index % 14)
            start = timezone.make_aware(datetime.combine(event_day, time(8 + (index % 4) * 2, 0)))
            end = start + timedelta(hours=2)
            if not AcademicScheduleEvent.objects.filter(
                academic_class=academic_class, ec=ec, start_datetime=start, end_datetime=end
            ).exists():
                create_schedule_event(
                    user=actor, title=f"Cours représentatif — {ec.title}", description="Séance institutionnelle du scénario pilote.",
                    event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE, academic_class=academic_class, ec=ec,
                    teacher=teacher, branch=academic_class.branch, academic_year=academic_class.academic_year,
                    start_datetime=start, end_datetime=end, status=AcademicScheduleEvent.STATUS_COMPLETED,
                    location="Salle pilote ISMI", is_online=False, is_active=True,
                )
                events += 1
        return assignments, events, slots

    def _pilot_s2_score(self, student_index, ec_index):
        normal, retake = Decimal("13.00"), None
        if student_index < 4:
            normal = Decimal("16.00")
        elif 8 <= student_index < 12 and ec_index in {0, 3}:
            normal, retake = Decimal("7.00"), Decimal("14.00")
        elif 12 <= student_index < 16 and ec_index in {1, 4}:
            normal = Decimal("7.00")
            retake = Decimal("13.00") if ec_index == 1 else Decimal("7.00")
        elif student_index >= 16:
            normal, retake = Decimal("6.00"), Decimal("7.00")
        return normal, retake

    def _pilot_s2_normal_scores(self, *, enrollments, semester):
        ecs = list(EC.objects.filter(ue__semester=semester).order_by("ue__code", "id"))
        for student_index, enrollment in enumerate(enrollments):
            for ec_index, ec in enumerate(ecs):
                normal, _ = self._pilot_s2_score(student_index, ec_index)
                ECGrade.objects.update_or_create(
                    enrollment=enrollment,
                    ec=ec,
                    defaults={"normal_score": normal, "retake_score": None},
                )

    def _pilot_s2_retake_scores(self, *, enrollments, semester):
        ecs = list(EC.objects.filter(ue__semester=semester).order_by("ue__code", "id"))
        for student_index, enrollment in enumerate(enrollments):
            for ec_index, ec in enumerate(ecs):
                _, retake = self._pilot_s2_score(student_index, ec_index)
                if retake is None:
                    continue
                grade = ECGrade.objects.get(enrollment=enrollment, ec=ec)
                if grade.retake_score == retake:
                    continue
                grade.retake_score = retake
                grade.save(update_fields=["retake_score"])

    def _pilot_director_semester_action(self, view, director, semester_id, action, RequestFactory, SessionMiddleware):
        request = RequestFactory().post("/portal/director/results/action/", {"semester_id": semester_id, "action": action})
        SessionMiddleware(lambda current_request: None).process_request(request)
        request.session.save()
        request.user = director
        response = view(request)
        if response.status_code >= 400:
            raise CommandError(f"Le workflow DE S2 a echoue lors de '{action}' (HTTP {response.status_code}).")
