from __future__ import annotations

from datetime import date
from decimal import Decimal
import re

from django.core.management import BaseCommand
from django.db import transaction

from academics.models import (
    AcademicClass,
    AcademicEnrollment,
    AcademicYear,
    EC,
    Language,
    Profession,
    Semester,
    UE,
)
from academics.services.academic_context_resolver import (
    LEGACY_ENTRY_YEAR_TO_LEVEL,
    resolve_level_from_entry_year,
)
from academics.services.enrollment_service import assign_student_academic_enrollment
from inscriptions.models import Inscription


UE_BLUEPRINTS = {
    1: [
        {
            "code": "UE101",
            "title": "Fondements biologiques et anatomiques",
            "ecs": [
                ("Anatomie generale", Decimal("2.00"), Decimal("1.00")),
                ("Physiologie appliquee", Decimal("2.00"), Decimal("1.00")),
                ("Biologie cellulaire", Decimal("2.00"), Decimal("1.00")),
            ],
        },
        {
            "code": "UE102",
            "title": "Bases cliniques et soins",
            "ecs": [
                ("Soins fondamentaux", Decimal("2.00"), Decimal("1.00")),
                ("Hygiene hospitaliere", Decimal("2.00"), Decimal("1.00")),
                ("Securite du patient", Decimal("2.00"), Decimal("1.00")),
            ],
        },
        {
            "code": "UE103",
            "title": "Sante publique et prevention",
            "ecs": [
                ("Epidemiologie descriptive", Decimal("2.00"), Decimal("1.00")),
                ("Education a la sante", Decimal("2.00"), Decimal("1.00")),
                ("Promotion de la sante", Decimal("2.00"), Decimal("1.00")),
            ],
        },
        {
            "code": "UE104",
            "title": "Methodes quantitatives",
            "ecs": [
                ("Biostatistiques", Decimal("2.00"), Decimal("1.00")),
                ("Informatique appliquee", Decimal("2.00"), Decimal("1.00")),
                ("Analyse de donnees", Decimal("2.00"), Decimal("1.00")),
            ],
        },
        {
            "code": "UE105",
            "title": "Communication professionnelle",
            "ecs": [
                ("Francais professionnel", Decimal("2.00"), Decimal("1.00")),
                ("Anglais medical", Decimal("2.00"), Decimal("1.00")),
                ("Ethique et deontologie", Decimal("2.00"), Decimal("1.00")),
            ],
        },
    ],
    2: [
        {
            "code": "UE201",
            "title": "Pathologies et therapeutiques",
            "ecs": [
                ("Pathologies medicales", Decimal("2.00"), Decimal("1.00")),
                ("Pharmacologie pratique", Decimal("2.00"), Decimal("1.00")),
                ("Surveillance clinique", Decimal("2.00"), Decimal("1.00")),
            ],
        },
        {
            "code": "UE202",
            "title": "Pratiques de soins avances",
            "ecs": [
                ("Soins d'urgence", Decimal("2.00"), Decimal("1.00")),
                ("Soins materno-infantiles", Decimal("2.00"), Decimal("1.00")),
                ("Techniques de laboratoire", Decimal("2.00"), Decimal("1.00")),
            ],
        },
        {
            "code": "UE203",
            "title": "Gestion et qualite en sante",
            "ecs": [
                ("Organisation des services", Decimal("2.00"), Decimal("1.00")),
                ("Demarche qualite", Decimal("2.00"), Decimal("1.00")),
                ("Gestion des risques", Decimal("2.00"), Decimal("1.00")),
            ],
        },
        {
            "code": "UE204",
            "title": "Recherche appliquee",
            "ecs": [
                ("Methodologie de recherche", Decimal("2.00"), Decimal("1.00")),
                ("Lecture critique", Decimal("2.00"), Decimal("1.00")),
                ("Projet tutorat", Decimal("2.00"), Decimal("1.00")),
            ],
        },
        {
            "code": "UE205",
            "title": "Professionnalisation",
            "ecs": [
                ("Stage encadre", Decimal("2.00"), Decimal("1.00")),
                ("Communication clinique", Decimal("2.00"), Decimal("1.00")),
                ("Insertion professionnelle", Decimal("2.00"), Decimal("1.00")),
            ],
        },
    ],
}


class Command(BaseCommand):
    help = (
        "Seed structure academics (annee, classes, semestres, UE, EC) "
        "et rattache les inscriptions existantes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict-clean-ecs",
            action="store_true",
            help="Supprime les EC hors blueprint pour chaque UE seedee.",
        )

    def handle(self, *args, **options):
        strict_clean_ecs = options.get("strict_clean_ecs", False)
        self.stdout.write(self.style.NOTICE("\n[academics] Initialisation structure academique..."))

        counters = {
            "years_created": 0,
            "years_updated": 0,
            "classes_created": 0,
            "classes_updated": 0,
            "semesters_created": 0,
            "semesters_updated": 0,
            "ues_created": 0,
            "ues_updated": 0,
            "ecs_created": 0,
            "ecs_updated": 0,
            "ecs_deleted": 0,
            "enroll_assigned": 0,
            "enroll_existing": 0,
            "enroll_manual": 0,
            "enroll_skipped": 0,
            "fallback_levels": 0,
        }

        with transaction.atomic():
            self._seed_languages_and_professions()
            year_map = self._ensure_academic_years(counters)
            self._ensure_classes_from_inscriptions(year_map, counters)
            self._ensure_semesters_ues_ecs(counters, strict_clean_ecs=strict_clean_ecs)
            self._link_inscriptions_to_academics(year_map, counters)

        self.stdout.write(self.style.SUCCESS("\n[academics] Seed termine."))
        self.stdout.write(
            self.style.SUCCESS(
                " - Annees: {years_created} creees, {years_updated} mises a jour\n"
                " - Classes: {classes_created} creees, {classes_updated} mises a jour\n"
                " - Semestres: {semesters_created} crees, {semesters_updated} mis a jour\n"
                " - UE: {ues_created} creees, {ues_updated} mises a jour\n"
                " - EC: {ecs_created} crees, {ecs_updated} mis a jour, {ecs_deleted} supprimes\n"
                " - Enrollment: {enroll_assigned} affectes, {enroll_existing} deja existants, "
                "{enroll_manual} relies en fallback, {enroll_skipped} ignores"
            ).format(**counters)
        )

    def _seed_languages_and_professions(self):
        for name, code in (("Francais", "fr"), ("Anglais", "en"), ("Bambara", "bm")):
            Language.objects.update_or_create(
                name=name,
                defaults={"code": code, "is_active": True},
            )

        professions = [
            "Infirmier",
            "Sage-femme",
            "Technicien de laboratoire",
            "Data manager sante",
            "Agent de sante communautaire",
        ]
        for name in professions:
            Profession.objects.update_or_create(
                name=name,
                defaults={"description": "Referentiel metier seed.", "is_active": True},
            )

    def _ensure_academic_years(self, counters):
        year_names = set(
            Inscription.objects.select_related("candidature")
            .values_list("candidature__academic_year", flat=True)
        )
        year_names = {self._canonical_year_name(y) for y in year_names if self._canonical_year_name(y)}

        if not year_names:
            today = date.today()
            start_year = today.year if today.month >= 9 else today.year - 1
            year_names.add(f"{start_year}-{start_year + 1}")

        year_map = {}
        ordered = sorted(year_names)
        target_active = ordered[-1]

        for name in ordered:
            start_year, end_year = self._split_year(name)
            defaults = {
                "start_date": date(start_year, 10, 1),
                "end_date": date(end_year, 7, 31),
                "is_active": name == target_active,
            }
            obj, created = AcademicYear.objects.update_or_create(name=name, defaults=defaults)
            if created:
                counters["years_created"] += 1
            else:
                counters["years_updated"] += 1
            year_map[name] = obj

        # Garantit une seule annee active.
        AcademicYear.objects.exclude(name=target_active).update(is_active=False)
        return year_map

    def _ensure_classes_from_inscriptions(self, year_map, counters):
        inscriptions = Inscription.objects.select_related(
            "candidature__programme__cycle",
            "candidature__branch",
        )

        for inscription in inscriptions:
            candidature = inscription.candidature
            programme = candidature.programme
            branch = candidature.branch
            year_name = self._canonical_year_name(candidature.academic_year)
            academic_year = year_map.get(year_name)
            if not academic_year:
                continue

            level = self._resolve_level(programme, candidature.entry_year, counters)
            if not level:
                continue

            study_level = "MASTER" if level.startswith("M") else "LICENCE"
            class_name = f"{programme.title} - {branch.code} - {level} ({academic_year.name})"

            academic_class, created = AcademicClass.objects.update_or_create(
                programme=programme,
                branch=branch,
                academic_year=academic_year,
                level=level,
                defaults={
                    "name": class_name[:100],
                    "study_level": study_level,
                    "validation_threshold": Decimal("10.00"),
                    "is_active": True,
                },
            )

            if created:
                counters["classes_created"] += 1
            else:
                counters["classes_updated"] += 1

    def _ensure_semesters_ues_ecs(self, counters, *, strict_clean_ecs=False):
        classes = AcademicClass.objects.filter(is_active=True).select_related("academic_year")

        for academic_class in classes:
            for number in (1, 2):
                semester, sem_created = Semester.objects.get_or_create(
                    academic_class=academic_class,
                    number=number,
                    defaults={
                        "status": Semester.STATUS_DRAFT,
                        "total_required_credits": Decimal("30.00"),
                    },
                )
                if sem_created:
                    counters["semesters_created"] += 1

                expected_total = Decimal("0.00")
                for ue_data in UE_BLUEPRINTS[number]:
                    ue, ue_created = UE.objects.get_or_create(
                        semester=semester,
                        code=ue_data["code"],
                        defaults={"title": ue_data["title"]},
                    )
                    if ue_created:
                        counters["ues_created"] += 1
                    elif ue.title != ue_data["title"]:
                        ue.title = ue_data["title"]
                        ue.save(update_fields=["title"])
                        counters["ues_updated"] += 1

                    ue_total_credit = Decimal("0.00")
                    expected_titles = {title for title, _, _ in ue_data["ecs"]}

                    for ec_title, credit_required, coefficient in ue_data["ecs"]:
                        ec, ec_created = EC.objects.get_or_create(
                            ue=ue,
                            title=ec_title,
                            defaults={
                                "credit_required": credit_required,
                                "coefficient": coefficient,
                            },
                        )
                        if ec_created:
                            counters["ecs_created"] += 1
                        else:
                            changed = False
                            if ec.credit_required != credit_required:
                                ec.credit_required = credit_required
                                changed = True
                            if ec.coefficient != coefficient:
                                ec.coefficient = coefficient
                                changed = True
                            if changed:
                                ec.save(update_fields=["credit_required", "coefficient"])
                                counters["ecs_updated"] += 1
                        ue_total_credit += credit_required

                    if strict_clean_ecs:
                        extras_qs = ue.ecs.exclude(title__in=expected_titles)
                        deleted_count, _ = extras_qs.delete()
                        counters["ecs_deleted"] += deleted_count

                    expected_total += ue_total_credit

                if (
                    semester.total_required_credits != expected_total
                    or semester.status != Semester.STATUS_DRAFT
                ):
                    semester.total_required_credits = expected_total
                    semester.status = Semester.STATUS_DRAFT
                    semester.save(update_fields=["total_required_credits", "status"])
                    counters["semesters_updated"] += 1

    def _link_inscriptions_to_academics(self, year_map, counters):
        inscriptions = Inscription.objects.select_related(
            "candidature__programme__cycle",
            "candidature__branch",
        )

        for inscription in inscriptions:
            result = assign_student_academic_enrollment(inscription)
            status = result.get("status")
            if status == "assigned":
                counters["enroll_assigned"] += 1
                continue
            if status == "already_assigned":
                counters["enroll_existing"] += 1
                continue

            manual_enrollment = self._manual_enrollment_fallback(inscription, year_map, counters)
            if manual_enrollment:
                counters["enroll_manual"] += 1
            else:
                counters["enroll_skipped"] += 1

    def _manual_enrollment_fallback(self, inscription, year_map, counters):
        candidature = getattr(inscription, "candidature", None)
        student = getattr(inscription, "student", None)
        if candidature is None or student is None:
            return None

        year_name = self._canonical_year_name(candidature.academic_year)
        academic_year = year_map.get(year_name)
        if not academic_year:
            return None

        level = self._resolve_level(candidature.programme, candidature.entry_year, counters)
        if not level:
            return None

        academic_class = AcademicClass.objects.filter(
            programme=candidature.programme,
            branch=candidature.branch,
            academic_year=academic_year,
            level=level,
            is_active=True,
        ).first()
        if not academic_class:
            return None

        enrollment, _ = AcademicEnrollment.objects.get_or_create(
            inscription=inscription,
            defaults={
                "student": student.user,
                "programme": candidature.programme,
                "branch": candidature.branch,
                "academic_year": academic_year,
                "academic_class": academic_class,
                "is_active": True,
            },
        )
        return enrollment

    def _resolve_level(self, programme, entry_year, counters):
        result = resolve_level_from_entry_year(programme, entry_year)
        if result.get("status") == "resolved":
            return result.get("resolved_level")

        try:
            legacy_level = LEGACY_ENTRY_YEAR_TO_LEVEL.get(int(entry_year))
        except (TypeError, ValueError):
            legacy_level = None

        if legacy_level:
            counters["fallback_levels"] += 1
        return legacy_level

    def _canonical_year_name(self, value):
        raw = str(value or "").strip().replace(" ", "")
        if not raw:
            return ""
        if re.fullmatch(r"\d{4}[-/]\d{4}", raw):
            return raw.replace("/", "-")
        return ""

    def _split_year(self, year_name):
        left, right = year_name.split("-")
        return int(left), int(right)

