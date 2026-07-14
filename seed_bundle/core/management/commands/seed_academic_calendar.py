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
            AcademicClass,
            AcademicYear,
            Semester,
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
            branch = Branch.objects.filter(is_active=True).first()
            if not branch:
                branch = Branch.objects.first()
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
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS("  ✓ Calendrier 2026-2027 v1 créé (Brouillon)"))
        else:
            self.stdout.write(f"  → Calendrier existant : {cal} (statut : {cal.status})")

        # ── Classe de référence ───────────────────────────────────────────────
        ref_class = (
            AcademicClass.objects.filter(branch=branch, academic_year=year, is_active=True)
            .first()
        )
        if not ref_class:
            ref_class = AcademicClass.objects.filter(branch=branch, is_active=True).first()

        if ref_class:
            self.stdout.write(f"  Classe de référence : {ref_class.display_name}")
            # S'assurer que S1 et S2 existent
            s1, c1 = Semester.objects.get_or_create(academic_class=ref_class, number=1)
            s2, c2 = Semester.objects.get_or_create(academic_class=ref_class, number=2)
            if c1:
                self.stdout.write(self.style.SUCCESS(f"    ✓ Semestre 1 créé pour {ref_class.display_name}"))
            if c2:
                self.stdout.write(self.style.SUCCESS(f"    ✓ Semestre 2 créé pour {ref_class.display_name}"))
        else:
            s1 = s2 = None
            self.stdout.write(self.style.WARNING(
                "  ⚠ Aucune classe active trouvée — les entrées liées à une classe/semestre seront ignorées."
            ))

        # ── Entrées du calendrier ─────────────────────────────────────────────
        # Chaque entrée : (event_type, title, start, end, scope, class, semester)
        E = AcademicCalendarEntry

        entries_spec = [
            # 1. Rentrée académique (toute l'annexe)
            dict(
                event_type=E.EVENT_ACADEMIC_START,
                title="Rentrée académique 2026-2027",
                start=aw(date(2026, 10, 6)),
                end=aw(date(2026, 10, 6), 23, 59),
                scope=E.SCOPE_BRANCH,
                academic_class=None,
                semester=None,
                is_blocking=True,
            ),
            # 2. Début semestre 1
            dict(
                event_type=E.EVENT_SEMESTER_START,
                title="Début Semestre 1",
                start=aw(date(2026, 10, 7)),
                end=aw(date(2026, 10, 7), 23, 59),
                scope=E.SCOPE_CLASS if ref_class else E.SCOPE_BRANCH,
                academic_class=ref_class,
                semester=s1,
                is_blocking=False,
            ),
            # 3. Session d'examens S1
            dict(
                event_type=E.EVENT_EXAM_SESSION,
                title="Session d'examens — Semestre 1",
                start=aw(date(2027, 1, 20)),
                end=aw(date(2027, 2, 3), 23, 59),
                scope=E.SCOPE_CLASS if ref_class else E.SCOPE_BRANCH,
                academic_class=ref_class,
                semester=s1,
                is_blocking=True,
            ),
            # 4. Session de rattrapage S1
            dict(
                event_type=E.EVENT_RETAKE_SESSION,
                title="Session de rattrapage — Semestre 1",
                start=aw(date(2027, 2, 10)),
                end=aw(date(2027, 2, 17), 23, 59),
                scope=E.SCOPE_CLASS if ref_class else E.SCOPE_BRANCH,
                academic_class=ref_class,
                semester=s1,
                is_blocking=True,
            ),
            # 5. Début semestre 2
            dict(
                event_type=E.EVENT_SEMESTER_START,
                title="Début Semestre 2",
                start=aw(date(2027, 3, 1)),
                end=aw(date(2027, 3, 1), 23, 59),
                scope=E.SCOPE_CLASS if ref_class else E.SCOPE_BRANCH,
                academic_class=ref_class,
                semester=s2,
                is_blocking=False,
            ),
            # 6. Session d'examens S2
            dict(
                event_type=E.EVENT_EXAM_SESSION,
                title="Session d'examens — Semestre 2",
                start=aw(date(2027, 5, 28)),
                end=aw(date(2027, 6, 10), 23, 59),
                scope=E.SCOPE_CLASS if ref_class else E.SCOPE_BRANCH,
                academic_class=ref_class,
                semester=s2,
                is_blocking=True,
            ),
            # 7. Clôture académique
            dict(
                event_type=E.EVENT_ACADEMIC_END,
                title="Clôture académique 2026-2027",
                start=aw(date(2027, 7, 15)),
                end=aw(date(2027, 7, 31), 23, 59),
                scope=E.SCOPE_BRANCH,
                academic_class=None,
                semester=None,
                is_blocking=False,
            ),
        ]

        created_count = 0
        skipped_count = 0
        for spec in entries_spec:
            # Ignorer les entrées nécessitant classe/semestre si absents
            if spec["semester"] is None and spec["event_type"] in {
                E.EVENT_EXAM_SESSION,
                E.EVENT_RETAKE_SESSION,
                E.EVENT_SEMESTER_START,
                E.EVENT_SEMESTER_END,
            }:
                self.stdout.write(
                    self.style.WARNING(f"    ⚠ Ignoré (pas de semestre) : {spec['title']}")
                )
                skipped_count += 1
                continue

            # Vérifier si une entrée du même type existe déjà sur ce calendrier
            qs = E.objects.filter(
                calendar=cal,
                event_type=spec["event_type"],
                semester=spec["semester"],
            )
            if qs.exists():
                self.stdout.write(f"    → Déjà existant : {spec['title']}")
                skipped_count += 1
                continue

            E.objects.create(
                calendar=cal,
                event_type=spec["event_type"],
                title=spec["title"],
                start_datetime=spec["start"],
                end_datetime=spec["end"],
                target_scope=spec["scope"],
                academic_class=spec["academic_class"],
                semester=spec["semester"],
                is_blocking=spec["is_blocking"],
                status=E.STATUS_DRAFT,
                created_by=actor,
            )
            self.stdout.write(self.style.SUCCESS(f"    ✓ Créé : {spec['title']}"))
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
