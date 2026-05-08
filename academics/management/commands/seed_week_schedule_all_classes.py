from __future__ import annotations

from datetime import datetime, timedelta, time

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from academics.models import AcademicClass, AcademicScheduleEvent, EC
from academics.services.schedule_service import create_schedule_event, update_schedule_event
from accounts.models import Profile

User = get_user_model()


SLOT_WINDOWS = [
    (time(8, 0), time(10, 0)),
    (time(10, 0), time(12, 0)),
]


class Command(BaseCommand):
    help = "Seed emploi du temps d'une semaine pour chaque classe academique active"

    def add_arguments(self, parser):
        parser.add_argument(
            "--week-start",
            type=str,
            default="",
            help="Date de debut de semaine au format YYYY-MM-DD (lundi recommande).",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=5,
            help="Nombre de jours a seed (defaut: 5).",
        )

    def handle(self, *args, **options):
        week_start = self._resolve_week_start(options.get("week_start", ""))
        days = max(1, min(options.get("days", 5), 6))

        classes = list(
            AcademicClass.objects.filter(is_active=True)
            .select_related("branch", "academic_year", "programme")
            .order_by("branch__name", "programme__title", "level")
        )
        if not classes:
            raise CommandError("Aucune classe academique active trouvee.")

        counters = {
            "classes_processed": 0,
            "classes_without_ec": 0,
            "events_created": 0,
            "events_updated": 0,
            "events_skipped_conflict": 0,
            "teachers_seeded": 0,
        }

        self.stdout.write(
            self.style.NOTICE(
                f"\n[schedule] Seed semaine classes: debut={week_start.isoformat()} jours={days}"
            )
        )

        for academic_class in classes:
            counters["classes_processed"] += 1

            ecs = list(
                EC.objects.filter(ue__semester__academic_class=academic_class)
                .select_related("ue", "ue__semester")
                .order_by("ue__semester__number", "ue__code", "id")
            )
            if not ecs:
                counters["classes_without_ec"] += 1
                self.stdout.write(
                    self.style.WARNING(
                        f" - {academic_class.display_name}: ignoree (aucun EC)."
                    )
                )
                continue

            teachers, seeded_count = self._get_or_seed_teachers_for_class(academic_class)
            counters["teachers_seeded"] += seeded_count

            ec_cursor = 0
            teacher_cursor = 0

            for day_offset in range(days):
                current_day = week_start + timedelta(days=day_offset)

                for slot_index, (start_t, end_t) in enumerate(SLOT_WINDOWS, start=1):
                    start_dt = timezone.make_aware(datetime.combine(current_day, start_t))
                    end_dt = timezone.make_aware(datetime.combine(current_day, end_t))

                    existing_slot_event = AcademicScheduleEvent.objects.filter(
                        academic_class=academic_class,
                        is_active=True,
                        start_datetime=start_dt,
                        end_datetime=end_dt,
                        title__startswith="[SEED-WEEK]",
                    ).exclude(status=AcademicScheduleEvent.STATUS_CANCELLED).first()

                    if existing_slot_event is None and self._class_has_conflict(academic_class, start_dt, end_dt):
                        existing_same_slot = AcademicScheduleEvent.objects.filter(
                            academic_class=academic_class,
                            is_active=True,
                            start_datetime=start_dt,
                            end_datetime=end_dt,
                        ).exclude(status=AcademicScheduleEvent.STATUS_CANCELLED).exists()
                        if existing_same_slot:
                            counters["events_skipped_conflict"] += 1
                            continue

                    ec = ecs[ec_cursor % len(ecs)]
                    teacher = teachers[teacher_cursor % len(teachers)]
                    ec_cursor += 1
                    teacher_cursor += 1

                    title = f"[SEED-WEEK] {ec.title}"
                    description = (
                        "Seed automatique d'une semaine de cours pour activer les dashboards "
                        "et la planification initiale."
                    )

                    room_label = f"Salle-{academic_class.id}-{academic_class.level}-{slot_index}"

                    existing = existing_slot_event or AcademicScheduleEvent.objects.filter(
                        academic_class=academic_class,
                        ec=ec,
                        start_datetime=start_dt,
                        end_datetime=end_dt,
                        title=title,
                        is_active=True,
                    ).first()

                    try:
                        if existing:
                            update_schedule_event(
                                existing,
                                user=teacher,
                                description=description,
                                event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
                                teacher=teacher,
                                status=AcademicScheduleEvent.STATUS_PLANNED,
                                location=room_label,
                                is_online=False,
                                meeting_link="",
                            )
                            counters["events_updated"] += 1
                        else:
                            create_schedule_event(
                                user=teacher,
                                title=title,
                                description=description,
                                event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
                                academic_class=academic_class,
                                ec=ec,
                                teacher=teacher,
                                branch=academic_class.branch,
                                academic_year=academic_class.academic_year,
                                start_datetime=start_dt,
                                end_datetime=end_dt,
                                status=AcademicScheduleEvent.STATUS_PLANNED,
                                location=room_label,
                                is_online=False,
                                meeting_link="",
                                is_active=True,
                            )
                            counters["events_created"] += 1
                    except ValidationError:
                        counters["events_skipped_conflict"] += 1

        self.stdout.write(self.style.SUCCESS("\n[schedule] Seed semaine termine."))
        self.stdout.write(
            self.style.SUCCESS(
                " - Classes traitees: {classes_processed}\n"
                " - Classes sans EC: {classes_without_ec}\n"
                " - Evenements crees: {events_created}\n"
                " - Evenements mis a jour: {events_updated}\n"
                " - Evenements ignores (conflits): {events_skipped_conflict}\n"
                " - Enseignants seedes: {teachers_seeded}"
            ).format(**counters)
        )

    def _resolve_week_start(self, raw_date):
        if raw_date:
            try:
                parsed = datetime.strptime(raw_date, "%Y-%m-%d").date()
            except ValueError as exc:
                raise CommandError("--week-start doit etre au format YYYY-MM-DD") from exc
        else:
            parsed = timezone.localdate()

        return parsed - timedelta(days=parsed.weekday())

    def _class_has_conflict(self, academic_class, start_dt, end_dt):
        return AcademicScheduleEvent.objects.filter(
            academic_class=academic_class,
            is_active=True,
        ).exclude(
            status=AcademicScheduleEvent.STATUS_CANCELLED,
        ).filter(
            Q(start_datetime__lt=end_dt) & Q(end_datetime__gt=start_dt)
        ).exists()

    def _get_or_seed_teachers_for_class(self, academic_class):
        teachers = list(
            User.objects.filter(
                is_active=True,
                profile__position="teacher",
                profile__branch=academic_class.branch,
                username__startswith=f"seed.teacher.class.{academic_class.id}.",
            ).order_by("id")[:3]
        )

        seeded_count = 0
        target_count = 3
        while len(teachers) < target_count:
            index = len(teachers) + 1
            username = f"seed.teacher.class.{academic_class.id}.{index}"
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": "Teacher",
                    "last_name": f"C{academic_class.id}-{index}",
                    "email": f"{username}@esfe.local",
                    "is_staff": True,
                    "is_active": True,
                },
            )
            if created:
                user.set_password("demo1234")
                user.save(update_fields=["password"])

            profile, _ = Profile.objects.get_or_create(user=user)
            profile.role = "teacher"
            profile.user_type = "staff"
            profile.position = "teacher"
            profile.branch = academic_class.branch
            profile.employee_code = f"TEACH-C{academic_class.id}-{index:03d}"
            profile.employment_status = "active"
            profile.is_public = False
            profile.save(
                update_fields=[
                    "role",
                    "user_type",
                    "position",
                    "branch",
                    "employee_code",
                    "employment_status",
                    "is_public",
                    "updated_at",
                ]
            )

            teachers.append(user)
            seeded_count += 1

        return teachers, seeded_count

