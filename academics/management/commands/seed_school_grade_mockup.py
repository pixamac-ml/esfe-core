from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from academics.models import AcademicClass, AcademicEnrollment, EC, ECGrade, Semester, UE


class Command(BaseCommand):
    help = "Generate a coherent school grade mockup for existing academic classes."

    semester_blueprints = {
        1: [
            {
                "code": "UE103",
                "title": "Culture economique et professionnelle",
                "ecs": [
                    ("Economie generale", Decimal("3.00"), Decimal("2.00")),
                    ("Anglais professionnel I", Decimal("3.00"), Decimal("2.00")),
                ],
            },
            {
                "code": "UE104",
                "title": "Methodes quantitatives",
                "ecs": [
                    ("Statistiques descriptives", Decimal("2.00"), Decimal("1.00")),
                    ("Mathematiques financieres", Decimal("2.00"), Decimal("1.00")),
                    ("Analyse de donnees", Decimal("2.00"), Decimal("1.00")),
                ],
            },
            {
                "code": "UE105",
                "title": "Pratiques professionnelles",
                "ecs": [
                    ("Bureautique appliquee", Decimal("2.00"), Decimal("1.00")),
                    ("Projet tutoriel I", Decimal("2.00"), Decimal("1.00")),
                    ("Initiation a l entrepreneuriat", Decimal("2.00"), Decimal("1.00")),
                ],
            },
        ],
        2: [
            {
                "code": "UE203",
                "title": "Pilotage et communication",
                "ecs": [
                    ("Gestion des ressources humaines", Decimal("3.00"), Decimal("2.00")),
                    ("Communication professionnelle", Decimal("3.00"), Decimal("2.00")),
                ],
            },
            {
                "code": "UE204",
                "title": "Gestion financiere et controle",
                "ecs": [
                    ("Comptabilite analytique", Decimal("2.00"), Decimal("1.00")),
                    ("Budget et tresorerie", Decimal("2.00"), Decimal("1.00")),
                    ("Controle interne", Decimal("2.00"), Decimal("1.00")),
                ],
            },
            {
                "code": "UE205",
                "title": "Developpement professionnel",
                "ecs": [
                    ("Anglais professionnel II", Decimal("2.00"), Decimal("1.00")),
                    ("Projet tutoriel II", Decimal("2.00"), Decimal("1.00")),
                    ("Ethique et vie professionnelle", Decimal("2.00"), Decimal("1.00")),
                ],
            },
        ],
    }
    scores = [
        Decimal("14.00"),
        Decimal("12.50"),
        Decimal("15.00"),
        Decimal("13.00"),
        Decimal("16.00"),
        Decimal("11.50"),
    ]

    def handle(self, *args, **options):
        created_ues = 0
        created_ecs = 0
        created_grades = 0
        updated_semesters = 0

        with transaction.atomic():
            for academic_class in AcademicClass.objects.filter(is_active=True).order_by("id"):
                for number in (1, 2):
                    semester, _ = Semester.objects.get_or_create(
                        academic_class=academic_class,
                        number=number,
                        defaults={"status": Semester.STATUS_DRAFT},
                    )

                    for ue_data in self.semester_blueprints[number]:
                        ue, ue_created = UE.objects.get_or_create(
                            semester=semester,
                            code=ue_data["code"],
                            defaults={"title": ue_data["title"]},
                        )
                        if ue_created:
                            created_ues += 1
                        elif ue.title != ue_data["title"]:
                            ue.title = ue_data["title"]
                            ue.save(update_fields=["title"])

                        for ec_title, credit, coefficient in ue_data["ecs"]:
                            ec, ec_created = EC.objects.get_or_create(
                                ue=ue,
                                title=ec_title,
                                defaults={
                                    "credit_required": credit,
                                    "coefficient": coefficient,
                                },
                            )
                            if ec_created:
                                created_ecs += 1

                            if ec.credit_required != credit or ec.coefficient != coefficient:
                                ec.credit_required = credit
                                ec.coefficient = coefficient
                                ec.save()

                            created_grades += self._complete_existing_grade_rows(
                                academic_class=academic_class,
                                semester=semester,
                                ec=ec,
                            )

                    total_credits = sum(
                        ue.credit_required
                        for ue in semester.ues.prefetch_related("ecs")
                    )
                    if semester.total_required_credits != total_credits:
                        semester.total_required_credits = total_credits
                        semester.save(update_fields=["total_required_credits"])
                        updated_semesters += 1

        self.stdout.write(self.style.SUCCESS(
            "Mockup generated: "
            f"{created_ues} UE, {created_ecs} EC, "
            f"{created_grades} notes, {updated_semesters} semesters updated."
        ))
        self._print_summary()

    def _complete_existing_grade_rows(self, *, academic_class, semester, ec):
        created = 0
        enrollments = AcademicEnrollment.objects.filter(
            academic_class=academic_class,
            academic_year=academic_class.academic_year,
            is_active=True,
        ).order_by("id")

        for index, enrollment in enumerate(enrollments):
            semester_has_grades = ECGrade.objects.filter(
                enrollment=enrollment,
                ec__ue__semester=semester,
            ).exists()
            if not semester_has_grades:
                continue

            score = self.scores[(index + ec.id) % len(self.scores)]
            grade, grade_created = ECGrade.objects.get_or_create(
                enrollment=enrollment,
                ec=ec,
                defaults={"normal_score": score},
            )
            if grade_created:
                created += 1
            elif grade.normal_score is None:
                grade.normal_score = score
                grade.save(update_fields=["normal_score"])

        return created

    def _print_summary(self):
        semesters = (
            Semester.objects
            .select_related("academic_class")
            .prefetch_related("ues__ecs")
            .order_by("academic_class_id", "number")
        )
        for semester in semesters:
            ues = list(semester.ues.all())
            credits = sum(ue.credit_required for ue in ues)
            coefficients = sum(ue.coefficient for ue in ues)
            ec_count = sum(ue.ecs.count() for ue in ues)
            self.stdout.write(
                f"{semester.academic_class.display_name} S{semester.number}: "
                f"{len(ues)} UE, {ec_count} matieres, "
                f"credits={credits}, coefficients={coefficients}"
            )
