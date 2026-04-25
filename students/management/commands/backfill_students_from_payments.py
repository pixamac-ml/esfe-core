from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef, Q

from inscriptions.models import Inscription
from payments.models import Payment
from students.models import Student
from students.services.create_student import create_student_after_first_payment


class Command(BaseCommand):
    help = "Create missing Student accounts for eligible paid inscriptions."

    def handle(self, *args, **options):
        validated_payment_exists = Payment.objects.filter(
            inscription_id=OuterRef("pk"),
            status=Payment.STATUS_VALIDATED,
        )

        student_exists = Student.objects.filter(inscription_id=OuterRef("pk"))

        qs = (
            Inscription.objects.select_related("candidature")
            .annotate(
                has_validated_payment=Exists(validated_payment_exists),
                has_student=Exists(student_exists),
            )
            .filter(
                has_validated_payment=True,
                has_student=False,
            )
            .filter(
                Q(candidature__status="accepted")
                | Q(candidature__status="accepted_with_reserve")
            )
            .order_by("id")
        )

        created_count = 0
        skipped_count = 0
        error_count = 0

        for inscription in qs:
            try:
                result = create_student_after_first_payment(inscription)
                if result and result.get("student"):
                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"[CREATED] inscription={inscription.id} student={result['student'].id}"
                        )
                    )
                else:
                    skipped_count += 1
                    self.stdout.write(
                        f"[SKIPPED] inscription={inscription.id}"
                    )
            except Exception as exc:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"[ERROR] inscription={inscription.id} error={exc}"
                    )
                )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Backfill completed."))
        self.stdout.write(f"Created: {created_count}")
        self.stdout.write(f"Skipped: {skipped_count}")
        self.stdout.write(f"Errors: {error_count}")

