"""Seed idempotent de la maquette pilote ISMI via le bootstrap institutionnel."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management import BaseCommand, CommandError, call_command
from django.db import transaction
from django.db.models import Sum

from academics.models import AcademicClass, EC, Semester, UE
from branches.models import Branch
from core.services.institution_bootstrap import load_bootstrap_manifest
from formations.models import Programme


PILOT_SEMESTERS = {
    "semester_ismi_s1": ("S1", "PILOTE ISMI - L1", 1),
    "semester_ismi_s2": ("S2", "PILOTE ISMI - L1", 2),
    "semester_ismi_s3": ("S3", "PILOTE ISMI - L2", 3),
}
EXPECTED_UE_CREDITS = Decimal("6.00")
EXPECTED_SEMESTER_CREDITS = Decimal("30.00")
PILOT_BRANCH_CODE = "MBG"
LEGACY_PILOT_BRANCH_CODE = "SK2"


class Command(BaseCommand):
    help = "Applique et contrôle la maquette pédagogique pilote ISMI (S1 à S3)."

    def handle(self, *args, **options):
        manifest_path = Path(settings.BASE_DIR) / "bootstrap" / "institution.json"
        payload = load_bootstrap_manifest(manifest_path)
        self._validate_source(payload)

        with transaction.atomic():
            moved_count = self._move_legacy_pilot_classes()
            call_command(
                "bootstrap_institution",
                data_file=manifest_path,
                stdout=self.stdout,
            )
            report = self._verify_database()
        if moved_count:
            self.stdout.write(f"Classes pilotes déplacées vers Moribabougou : {moved_count}.")
        self.stdout.write(self.style.SUCCESS("Maquette pilote ISMI disponible."))
        for label, ue_count, credits in report:
            self.stdout.write(f"{label} : {ue_count} UE / {credits} crédits")
        self.stdout.write("EC créés/réutilisés : 53")

    def _move_legacy_pilot_classes(self):
        """Conserve les identifiants déjà seedés avant le changement d'annexe."""
        target_branch = Branch.objects.filter(code=PILOT_BRANCH_CODE).first()
        legacy_branch = Branch.objects.filter(code=LEGACY_PILOT_BRANCH_CODE).first()
        if target_branch is None:
            raise CommandError("Annexe Moribabougou introuvable dans le bootstrap.")
        if legacy_branch is None:
            return 0

        moved_count = 0
        for _reference, (_label, class_name, _number) in PILOT_SEMESTERS.items():
            legacy_class = AcademicClass.objects.filter(
                branch=legacy_branch,
                academic_year__name="2099-2100",
                name=class_name,
                programme__slug="infirmiere-sante-maternelle-infantile",
            ).first()
            if legacy_class is None:
                continue
            if AcademicClass.objects.filter(
                branch=target_branch,
                academic_year=legacy_class.academic_year,
                name=class_name,
                programme=legacy_class.programme,
            ).exists():
                raise CommandError(
                    f"Une classe pilote ISMI existe déjà à Moribabougou : {class_name}."
                )
            legacy_class.branch = target_branch
            legacy_class.save(update_fields=["branch"])
            moved_count += 1
        return moved_count

    def _validate_source(self, payload):
        objects_by_id = {
            item.get("id"): item
            for item in payload["objects"]
            if isinstance(item, dict) and item.get("id")
        }
        for semester_ref, (label, _class_name, _number) in PILOT_SEMESTERS.items():
            semester_spec = objects_by_id.get(semester_ref)
            if not semester_spec:
                raise CommandError(f"{label} absent du manifeste institutionnel.")
            configured_total = Decimal(str(semester_spec["fields"].get("total_required_credits", "0")))
            if configured_total != EXPECTED_SEMESTER_CREDITS:
                raise CommandError(f"{label} doit totaliser {EXPECTED_SEMESTER_CREDITS} crédits.")

            semester_ues = [
                item
                for item in objects_by_id.values()
                if item.get("model") == "academics.UE"
                and item.get("lookup", {}).get("semester", {}).get("$ref") == semester_ref
            ]
            if len(semester_ues) != 5:
                raise CommandError(f"{label} doit contenir exactement 5 UE.")

            semester_credits = Decimal("0.00")
            for ue_spec in semester_ues:
                ue_ref = ue_spec["id"]
                ue_credits = sum(
                    (
                        Decimal(str(ec_spec["fields"].get("credit_required", "0")))
                        for ec_spec in objects_by_id.values()
                        if ec_spec.get("model") == "academics.EC"
                        and ec_spec.get("lookup", {}).get("ue", {}).get("$ref") == ue_ref
                    ),
                    Decimal("0.00"),
                )
                if ue_credits != EXPECTED_UE_CREDITS:
                    raise CommandError(
                        f"{label} / {ue_spec['lookup']['code']} : "
                        f"{ue_credits} crédits EC au lieu de {EXPECTED_UE_CREDITS}."
                    )
                semester_credits += ue_credits
            if semester_credits != EXPECTED_SEMESTER_CREDITS:
                raise CommandError(f"{label} : total EC incohérent ({semester_credits}).")

    def _verify_database(self):
        programme = Programme.objects.filter(slug="infirmiere-sante-maternelle-infantile").first()
        if programme is None:
            raise CommandError("Programme pilote ISMI absent après bootstrap.")

        report = []
        total_ecs = 0
        for _reference, (label, class_name, number) in PILOT_SEMESTERS.items():
            academic_class = AcademicClass.objects.filter(
                programme=programme,
                branch__code=PILOT_BRANCH_CODE,
                academic_year__name="2099-2100",
                name=class_name,
            ).first()
            semester = (
                Semester.objects.filter(academic_class=academic_class, number=number).first()
                if academic_class
                else None
            )
            if semester is None:
                raise CommandError(f"{label} absent après bootstrap.")
            ues = UE.objects.filter(semester=semester).exclude(structure_status=UE.STRUCTURE_ARCHIVED)
            credits = ues.aggregate(total=Sum("ecs__credit_required"))["total"] or Decimal("0.00")
            if ues.count() != 5 or credits != EXPECTED_SEMESTER_CREDITS:
                raise CommandError(f"{label} non conforme après bootstrap.")
            for ue in ues:
                ue_credits = ue.ecs.exclude(structure_status=EC.STRUCTURE_ARCHIVED).aggregate(
                    total=Sum("credit_required")
                )["total"] or Decimal("0.00")
                if ue_credits != EXPECTED_UE_CREDITS:
                    raise CommandError(f"{label} / {ue.code} non conforme après bootstrap.")
            total_ecs += EC.objects.filter(ue__semester=semester).exclude(
                structure_status=EC.STRUCTURE_ARCHIVED
            ).count()
            report.append((label, ues.count(), credits))

        if total_ecs != 53:
            raise CommandError(f"Nombre d'EC ISMI inattendu : {total_ecs} au lieu de 53.")
        return report
