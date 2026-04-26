from __future__ import annotations

from base64 import b64decode
from datetime import datetime, time, timedelta
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from academics.models import (
    AcademicEnrollment,
    AcademicScheduleEvent,
    EC,
    ECChapter,
    ECContent,
    StudentContentProgress,
)
from academics.services.schedule_service import (
    cancel_schedule_event,
    complete_schedule_event,
    create_schedule_event,
    postpone_schedule_event,
    start_schedule_event,
)


User = get_user_model()

MINIMAL_PDF = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R >> endobj
4 0 obj << /Length 44 >> stream
BT /F1 18 Tf 40 90 Td (Support de cours demo ESFE) Tj ET
endstream endobj
xref
0 5
0000000000 65535 f
0000000010 00000 n
0000000063 00000 n
0000000120 00000 n
0000000207 00000 n
trailer << /Root 1 0 R /Size 5 >>
startxref
312
%%EOF
"""

MINIMAL_PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wn4K1QAAAAASUVORK5CYII="
)


class Command(BaseCommand):
    help = "Peuple le dashboard etudiant avec un jeu de demo pour les contenus et l'emploi du temps."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            help="Username d'un etudiant deja inscrit. Par defaut, prend la premiere inscription academique active.",
        )

    def handle(self, *args, **options):
        enrollment = self._get_enrollment(options.get("username"))
        academic_class = enrollment.academic_class
        branch = enrollment.branch
        academic_year = enrollment.academic_year
        student_user = enrollment.student

        ecs = list(
            EC.objects.filter(ue__semester__academic_class=academic_class)
            .select_related("ue", "ue__semester")
            .order_by("ue__semester__number", "ue__code", "id")
        )
        if not ecs:
            raise CommandError("Aucun EC n'est rattache a la classe academique ciblee.")

        teachers = self._ensure_seed_teachers()

        with transaction.atomic():
            seeded_contents = self._seed_course_contents(student_user, ecs)
            seeded_events = self._seed_schedule(
                academic_class=academic_class,
                branch=branch,
                academic_year=academic_year,
                ecs=ecs,
                teachers=teachers,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed termine pour {student_user.username} : {seeded_events} evenements et {seeded_contents} contenus demo prets."
            )
        )

    def _get_enrollment(self, username: str | None):
        queryset = AcademicEnrollment.objects.select_related(
            "student",
            "academic_class",
            "branch",
            "academic_year",
        ).filter(
            is_active=True,
            academic_class__is_active=True,
        )
        if username:
            queryset = queryset.filter(student__username=username)
        enrollment = queryset.first()
        if enrollment is None:
            if username:
                raise CommandError(f"Aucune inscription academique active trouvee pour {username}.")
            raise CommandError("Aucune inscription academique active disponible pour seed le dashboard.")
        return enrollment

    def _ensure_seed_teachers(self):
        teachers = []
        blueprints = [
            ("seed_teacher_1", "Awa", "Traore"),
            ("seed_teacher_2", "Moussa", "Diallo"),
            ("seed_teacher_3", "Fatou", "Keita"),
        ]
        for username, first_name, last_name in blueprints:
            teacher, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": f"{username}@example.com",
                },
            )
            if created:
                teacher.set_password("demo1234")
                teacher.save(update_fields=["password"])
            teachers.append(teacher)
        return teachers

    def _seed_course_contents(self, student_user, ecs):
        content_count = 0
        for index, ec in enumerate(ecs[:3], start=1):
            chapter_intro, _ = ECChapter.objects.get_or_create(
                ec=ec,
                order=1,
                defaults={"title": f"Introduction et plan - {ec.title}"},
            )
            chapter_resources, _ = ECChapter.objects.get_or_create(
                ec=ec,
                order=2,
                defaults={"title": f"Ressources et supports - {ec.title}"},
            )

            seeded = [
                self._ensure_text_content(
                    chapter_intro,
                    title="Vue d'ensemble du module",
                    order=1,
                    text=(
                        f"{ec.title} introduit les notions essentielles du module. "
                        "Ce contenu demo permet de tester l'affichage texte, la progression et la lecture directe dans le panneau du dashboard."
                    ),
                ),
                self._ensure_pdf_content(
                    chapter_intro,
                    title="Support de cours PDF",
                    order=2,
                ),
                self._ensure_video_content(
                    chapter_resources,
                    title="Capsule video de revision",
                    order=1,
                    video_url="https://www.youtube.com/embed/dQw4w9WgXcQ",
                ),
                self._ensure_image_content(
                    chapter_resources,
                    title="Schema de synthese",
                    order=2,
                ),
                self._ensure_document_content(
                    chapter_resources,
                    title="Fiche annexe bureautique",
                    order=3,
                    content_type=ECContent.CONTENT_TYPE_DOC if index == 1 else (
                        ECContent.CONTENT_TYPE_PPT if index == 2 else ECContent.CONTENT_TYPE_EXCEL
                    ),
                ),
            ]
            content_count += len(seeded)
            self._seed_progress(student_user, seeded)
        return content_count

    def _seed_progress(self, student_user, contents):
        progress_values = [100, 65, 40, 20, 0]
        for content, progress_percent in zip(contents, progress_values):
            StudentContentProgress.objects.update_or_create(
                student=student_user,
                content=content,
                defaults={
                    "progress_percent": progress_percent,
                    "last_position": progress_percent,
                    "is_completed": progress_percent >= 100,
                },
            )

    def _ensure_text_content(self, chapter, *, title, order, text):
        content, _ = ECContent.objects.update_or_create(
            chapter=chapter,
            title=title,
            defaults={
                "content_type": ECContent.CONTENT_TYPE_TEXT,
                "order": order,
                "text_content": text,
                "video_url": "",
                "duration": None,
                "is_active": True,
            },
        )
        return content

    def _ensure_video_content(self, chapter, *, title, order, video_url):
        content, _ = ECContent.objects.update_or_create(
            chapter=chapter,
            title=title,
            defaults={
                "content_type": ECContent.CONTENT_TYPE_VIDEO,
                "order": order,
                "video_url": video_url,
                "text_content": "",
                "duration": 12,
                "is_active": True,
            },
        )
        return content

    def _ensure_pdf_content(self, chapter, *, title, order):
        content = ECContent.objects.filter(chapter=chapter, title=title).first() or ECContent(
            chapter=chapter,
            title=title,
        )
        content.content_type = ECContent.CONTENT_TYPE_PDF
        content.order = order
        content.is_active = True
        content.text_content = ""
        content.video_url = ""
        self._ensure_file(content, f"{slugify(chapter.ec.title)}-support.pdf", MINIMAL_PDF)
        content.save()
        return content

    def _ensure_image_content(self, chapter, *, title, order):
        content = ECContent.objects.filter(chapter=chapter, title=title).first() or ECContent(
            chapter=chapter,
            title=title,
        )
        content.content_type = ECContent.CONTENT_TYPE_IMAGE
        content.order = order
        content.is_active = True
        content.text_content = ""
        content.video_url = ""
        self._ensure_file(content, f"{slugify(chapter.ec.title)}-schema.png", MINIMAL_PNG)
        content.save()
        return content

    def _ensure_document_content(self, chapter, *, title, order, content_type):
        extension = {
            ECContent.CONTENT_TYPE_DOC: "docx",
            ECContent.CONTENT_TYPE_PPT: "pptx",
            ECContent.CONTENT_TYPE_EXCEL: "xlsx",
        }[content_type]
        payload = (
            f"Document de demonstration ESFE pour {chapter.ec.title}. "
            "Ce fichier sert a tester l'affichage des formats bureautiques dans le dashboard."
        ).encode("utf-8")
        content = ECContent.objects.filter(chapter=chapter, title=title).first() or ECContent(
            chapter=chapter,
            title=title,
        )
        content.content_type = content_type
        content.order = order
        content.is_active = True
        content.text_content = ""
        content.video_url = ""
        self._ensure_file(content, f"{slugify(chapter.ec.title)}-annexe.{extension}", payload)
        content.save()
        return content

    def _ensure_file(self, content, filename, payload):
        if content.file and content.file.name:
            return
        content.file.save(filename, ContentFile(payload), save=False)

    def _seed_schedule(self, *, academic_class, branch, academic_year, ecs, teachers):
        week_start = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
        blueprints = [
            {
                "title": "[DEMO] Cours magistral",
                "ec": ecs[0],
                "teacher": teachers[0],
                "day_offset": 0,
                "start": time(8, 0),
                "end": time(10, 0),
                "location": "Bloc A - Salle 101",
                "status_action": "planned",
            },
            {
                "title": "[DEMO] Travaux diriges",
                "ec": ecs[min(1, len(ecs) - 1)],
                "teacher": teachers[min(1, len(teachers) - 1)],
                "day_offset": 1,
                "start": time(10, 0),
                "end": time(12, 0),
                "location": "Bloc A - Salle 204",
                "status_action": "ongoing",
            },
            {
                "title": "[DEMO] Revision accompagnee",
                "ec": ecs[min(2, len(ecs) - 1)],
                "teacher": teachers[min(2, len(teachers) - 1)],
                "day_offset": 2,
                "start": time(14, 0),
                "end": time(16, 0),
                "location": "En ligne",
                "is_online": True,
                "meeting_link": "https://meet.google.com/demo-esfe-class",
                "status_action": "completed",
            },
            {
                "title": "[DEMO] Cours reporte",
                "ec": ecs[0],
                "teacher": teachers[0],
                "day_offset": 3,
                "start": time(8, 0),
                "end": time(10, 0),
                "location": "Bloc B - Salle 301",
                "status_action": "postponed",
                "new_day_offset": 4,
                "new_start": time(10, 0),
                "new_end": time(12, 0),
            },
            {
                "title": "[DEMO] Seance annulee",
                "ec": ecs[min(1, len(ecs) - 1)],
                "teacher": teachers[min(1, len(teachers) - 1)],
                "day_offset": 4,
                "start": time(14, 0),
                "end": time(16, 0),
                "location": "Bloc C - Salle 105",
                "status_action": "cancelled",
            },
        ]

        created_or_reused = 0
        for blueprint in blueprints:
            start_datetime = timezone.make_aware(datetime.combine(week_start + timedelta(days=blueprint["day_offset"]), blueprint["start"]))
            end_datetime = timezone.make_aware(datetime.combine(week_start + timedelta(days=blueprint["day_offset"]), blueprint["end"]))
            event = AcademicScheduleEvent.objects.filter(
                title=blueprint["title"],
                academic_class=academic_class,
                ec=blueprint["ec"],
            ).first()
            if event is None:
                event = create_schedule_event(
                    user=teachers[0],
                    title=blueprint["title"],
                    description="Evenement de demonstration pour le dashboard etudiant.",
                    event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
                    academic_class=academic_class,
                    ec=blueprint["ec"],
                    teacher=blueprint["teacher"],
                    branch=branch,
                    academic_year=academic_year,
                    start_datetime=start_datetime,
                    end_datetime=end_datetime,
                    status=AcademicScheduleEvent.STATUS_PLANNED,
                    location="" if blueprint.get("is_online") else blueprint["location"],
                    is_online=blueprint.get("is_online", False),
                    meeting_link=blueprint.get("meeting_link", ""),
                    is_active=True,
                )
                self._apply_status_action(event, blueprint, teachers[0], week_start)
            created_or_reused += 1
        return created_or_reused

    def _apply_status_action(self, event, blueprint, actor, week_start):
        action = blueprint["status_action"]
        if action == "ongoing":
            start_schedule_event(event, actor, notes="Demarrage seed dashboard")
            return
        if action == "completed":
            complete_schedule_event(
                event,
                actor,
                notes="Cours termine pendant le seed dashboard",
                started_at=event.start_datetime,
                ended_at=event.end_datetime,
            )
            return
        if action == "postponed":
            new_start = timezone.make_aware(
                datetime.combine(week_start + timedelta(days=blueprint["new_day_offset"]), blueprint["new_start"])
            )
            new_end = timezone.make_aware(
                datetime.combine(week_start + timedelta(days=blueprint["new_day_offset"]), blueprint["new_end"])
            )
            postpone_schedule_event(
                event,
                new_start,
                new_end,
                "Report de demonstration pour tester le badge dashboard.",
                actor,
            )
            return
        if action == "cancelled":
            cancel_schedule_event(
                event,
                "Annulation de demonstration pour tester le badge dashboard.",
                actor,
            )
