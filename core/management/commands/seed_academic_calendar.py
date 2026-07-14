"""
seed_academic_calendar
======================
Crée un exemple complet de calendrier académique pour l'annexe active :

  - Année académique 2026-2027 (si absente)
  - Calendrier brouillon pour cette année
  - Entrées : Rentrée, Clôture, Débuts S1/S2, Sessions examens S1/S2, Rattrapage S1
  - Semestres S1 + S2 sur la première classe active trouvée (si manquants)

Idempotent : get_or_create partout, safe à relancer.

Usage :
    python manage.py seed_academic_calendar
    python manage.py seed_academic_calendar --branch-id 2
"""
from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

User = get_user_model()


class Command(BaseCommand):
    help = "Seed exemple complet de calendrier académique (rentrée, semestres, examens…)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--branch-id",
            type=int,
            default=None,
            help="ID de la branche/annexe cible (défaut : première branche active).",
        )

    def handle(self, *args, **options):
        from academics.models import (
            AcademicCalendar,
            AcademicCalendarEntry,
            AcademicYear,
        )
        from branches.models import Branch

        def aw(d, hour=0, minute=0):
            """Date → datetime aware."""
            return timezone.make_aware(
                datetime(d.year, d.month, d.day, hour, minute)
            )

        # ── Branche ──────────────────────────────────────────────────────────
        branch_id = options.get("branch_id")
        if branch_id:
            branch = Branch.objects.filter(pk=branch_id).first()
            if not branch:
                self.stderr.write(self.style.ERROR(f"Branche {branch_id} introuvable."))
                return
        else:
            # Priorité : Moribabougou (annexe principale), sinon première active
            branch = (
                Branch.objects.filter(name__icontains="Moribabougou").first()
                or Branch.objects.filter(is_active=True).first()
                or Branch.objects.first()
            )
        if not branch:
            self.stderr.write(self.style.ERROR("Aucune branche trouvée. Créez d'abord une branche."))
            return
        self.stdout.write(f"  Branche : {branch.name}")

        # ── Utilisateur admin (pour created_by) ──────────────────────────────
        actor = User.objects.filter(is_superuser=True).first() or User.objects.first()

        # ── Année académique 2026-2027 ────────────────────────────────────────
        year, created = AcademicYear.objects.get_or_create(
            name="2026-2027",
            defaults={
                "start_date": date(2026, 10, 1),
                "end_date": date(2027, 7, 31),
                "is_active": True,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS("  ✓ Année académique 2026-2027 créée"))
        else:
            self.stdout.write(f"  → Année académique existante : {year.name}")

        # ── Calendrier brouillon ──────────────────────────────────────────────
        cal, created = AcademicCalendar.objects.get_or_create(
            branch=branch,
            academic_year=year,
            version=1,
            defaults={
                "status": AcademicCalendar.STATUS_DRAFT,
                "created_by": actor,
                "updated_by": actor,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS("  ✓ Calendrier 2026-2027 v1 créé (Brouillon)"))
        else:
            self.stdout.write(f"  → Calendrier existant : {cal} (statut : {cal.status})")

        E = AcademicCalendarEntry

        # ── Nettoyer les anciennes entrées par classe/semestre (migration) ────
        old_entries = E.objects.filter(
            calendar=cal,
            academic_class__isnull=False,
        )
        old_count = old_entries.count()
        if old_count:
            old_entries.delete()
            self.stdout.write(self.style.WARNING(
                f"  ⚠ {old_count} ancienne(s) entrée(s) par classe supprimée(s)"
            ))

        # ── 7 entrées globales SCOPE_BRANCH pour toute l'annexe ──────────────
        # Un seul calendrier, toutes classes confondues.
        BRANCH_ENTRIES = [
            (E.EVENT_ACADEMIC_START,  "Rentrée académique 2026-2027",
             date(2026, 10, 6),  date(2026, 10, 6),   True),
            (E.EVENT_SEMESTER_START,  "Début Semestre 1",
             date(2026, 10, 7),  date(2026, 10, 7),   False),
            (E.EVENT_EXAM_SESSION,    "Session d'examens — Semestre 1",
             date(2027, 1, 20),  date(2027, 2, 3),    True),
            (E.EVENT_RETAKE_SESSION,  "Session de rattrapage — Semestre 1",
             date(2027, 2, 10),  date(2027, 2, 17),   True),
            (E.EVENT_SEMESTER_START,  "Début Semestre 2",
             date(2027, 3, 1),   date(2027, 3, 1),    False),
            (E.EVENT_EXAM_SESSION,    "Session d'examens — Semestre 2",
             date(2027, 5, 28),  date(2027, 6, 10),   True),
            (E.EVENT_ACADEMIC_END,    "Clôture académique 2026-2027",
             date(2027, 7, 15),  date(2027, 7, 31),   False),
        ]

        created_count = 0
        skipped_count = 0
        for ev_type, title, d_start, d_end, blocking in BRANCH_ENTRIES:
            if E.objects.filter(calendar=cal, event_type=ev_type, title=title).exists():
                self.stdout.write(f"  → Déjà existant : {title}")
                skipped_count += 1
                continue
            E.objects.create(
                calendar=cal,
                event_type=ev_type,
                title=title,
                start_datetime=aw(d_start),
                end_datetime=aw(d_end, 23, 59),
                target_scope=E.SCOPE_BRANCH,
                academic_class=None,
                semester=None,
                is_blocking=blocking,
                status=E.STATUS_DRAFT,
                created_by=actor,
                updated_by=actor,
            )
            self.stdout.write(self.style.SUCCESS(f"  ✓ {title}"))
            created_count += 1

        # ── Résumé ────────────────────────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Seed terminé : {created_count} entrée(s) créée(s), {skipped_count} ignorée(s)."
        ))
        self.stdout.write("")
        self.stdout.write("  Prochaine étape dans l'interface :")
        self.stdout.write("  1. Menu Calendrier → sélectionner 2026-2027")
        self.stdout.write("  2. Vérifier les entrées créées")
        self.stdout.write("  3. Bouton 'Valider' → puis 'Publier'")
