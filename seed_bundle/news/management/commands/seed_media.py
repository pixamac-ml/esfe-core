from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.utils import timezone
from news.models import EventType, Event, MediaItem
from PIL import Image
from io import BytesIO


class Command(BaseCommand):
    help = "Seed Médiathèque (Events + MediaItems)"

    def handle(self, *args, **kwargs):

        self.stdout.write("📸 Initialisation médiathèque...")

        # ==================================================
        # TYPES D'ÉVÉNEMENTS
        # ==================================================
        types_data = [
            "Cérémonie",
            "Conférence",
            "Formation pratique",
            "Remise de diplômes",
        ]

        event_types = {}

        for name in types_data:
            obj, _ = EventType.objects.get_or_create(
                name=name,
                defaults={
                    "slug": name.lower().replace(" ", "-"),
                    "is_active": True,
                }
            )
            event_types[name] = obj

        # ==================================================
        # ÉVÉNEMENTS
        # ==================================================
        events_data = [
            {
                "title": "Cérémonie de rentrée académique 2025",
                "type": "Cérémonie",
                "description": "Cérémonie officielle marquant le début de l’année académique 2025-2026.",
                "date": "2025-10-15",
            },
            {
                "title": "Conférence sur la santé publique",
                "type": "Conférence",
                "description": "Conférence institutionnelle sur les enjeux sanitaires nationaux.",
                "date": "2025-11-10",
            },
            {
                "title": "Session de travaux pratiques en laboratoire",
                "type": "Formation pratique",
                "description": "Séance de pratique en biologie médicale.",
                "date": "2025-12-05",
            },
        ]

        for data in events_data:

            event, _ = Event.objects.update_or_create(
                title=data["title"],
                defaults={
                    "event_type": event_types[data["type"]],
                    "description": data["description"],
                    "event_date": data["date"],
                    "is_published": True,
                }
            )

            # ==================================================
            # IMAGE DE COUVERTURE FAKE PROPRE
            # ==================================================
            if not event.cover_image:

                img = Image.new("RGB", (1600, 900), color=(30, 80, 120))
                buffer = BytesIO()
                img.save(buffer, format="JPEG")

                event.cover_image.save(
                    f"{event.slug}_cover.jpg",
                    ContentFile(buffer.getvalue()),
                    save=True
                )

            # ==================================================
            # MÉDIAS IMAGES
            # ==================================================
            for i in range(1, 4):

                media_exists = MediaItem.objects.filter(
                    event=event,
                    caption=f"Photo {i}"
                ).exists()

                if not media_exists:

                    img = Image.new("RGB", (1200, 800), color=(60, 120, 160))
                    buffer = BytesIO()
                    img.save(buffer, format="JPEG")

                    media = MediaItem.objects.create(
                        event=event,
                        media_type=MediaItem.IMAGE,
                        caption=f"Photo {i}",
                    )

                    media.image.save(
                        f"{event.slug}_photo_{i}.jpg",
                        ContentFile(buffer.getvalue()),
                        save=True
                    )

        self.stdout.write(self.style.SUCCESS("✅ Seed médiathèque terminé proprement."))