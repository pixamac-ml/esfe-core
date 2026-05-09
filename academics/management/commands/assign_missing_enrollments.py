# academics/management/commands/assign_missing_enrollments.py
#
# Commande de rattrapage pour les étudiants existants sans classe.
# Usage :
#   python manage.py assign_missing_enrollments --dry-run   (aperçu)
#   python manage.py assign_missing_enrollments             (exécution)

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Affecte automatiquement les étudiants existants sans classe académique"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Affiche ce qui serait fait sans rien écrire en base",
        )

    def handle(self, *args, **options):
        from students.models import Student
        from academics.services.enrollment_service import assign_student_academic_enrollment

        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  Mode dry-run — aucune écriture en base\n"))

        # Tous les étudiants dont l'inscription n'a pas d'AcademicEnrollment
        students_qs = (
            Student.objects
            .filter(inscription__isnull=False)
            .exclude(inscription__academic_enrollment__isnull=False)
            .select_related(
                "inscription__candidature__programme",
                "inscription__candidature__branch",
            )
            .order_by("id")
        )

        total = students_qs.count()
        self.stdout.write(f"📋 {total} étudiant(s) sans affectation académique\n")

        if total == 0:
            self.stdout.write(self.style.SUCCESS("✅ Rien à faire.\n"))
            return

        counts = {"assigned": 0, "manual": 0, "error": 0}

        for student in students_qs:
            inscription = student.inscription
            cand = inscription.candidature
            self.stdout.write(
                f"  • {student.matricule} | {cand.programme} | "
                f"annexe={cand.branch} | "
                f"année candidature='{cand.academic_year}' | "
                f"entry_year={cand.entry_year}"
            )

            if dry_run:
                continue

            result = assign_student_academic_enrollment(inscription)
            status = result["status"]

            if status == "assigned":
                counts["assigned"] += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"     Affecté → {result['enrollment'].academic_class}"
                    )
                )
            elif status == "already_assigned":
                self.stdout.write("    ℹ️  Déjà affecté")
            elif status.startswith("manual_required"):
                counts["manual"] += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"    ⚠️  Manuelle requise : {result['reason']}"
                    )
                )
            else:
                counts["error"] += 1
                self.stdout.write(
                    self.style.ERROR(f"    ❌ Erreur : {result['reason']}")
                )

        if not dry_run:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS(f"✅ Affectés automatiquement : {counts['assigned']}"))
            self.stdout.write(self.style.WARNING(f"⚠️  Manuels requis          : {counts['manual']}"))
            self.stdout.write(self.style.ERROR(  f"❌ Erreurs                  : {counts['error']}"))
