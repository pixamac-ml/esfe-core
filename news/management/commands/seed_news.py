import base64
from datetime import timedelta
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify

from news.models import Category, News, NewsImage, Program

User = get_user_model()

# Placeholder local en secours si une URL distante echoue.
PNG_1X1_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/w8AAusB9Y9L3nQAAAAASUVORK5CYII="
)


class Command(BaseCommand):
    help = "Seed enrichi des actualites avec images distantes de test"

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=24,
            help="Nombre d'actualites a creer (defaut: 24)",
        )
        parser.add_argument(
            "--refresh-images",
            action="store_true",
            help="Re-telecharge les images meme si elles existent deja.",
        )

    def _download_image(self, url):
        request = Request(url, headers={"User-Agent": "ESFE-Seed/1.0"})
        try:
            with urlopen(request, timeout=15) as response:
                content_type = (response.info().get("Content-Type") or "").lower()
                payload = response.read()
                if payload and "image" in content_type:
                    return payload
        except (URLError, HTTPError, TimeoutError):
            return None
        return None

    def _placeholder(self):
        return base64.b64decode(PNG_1X1_BASE64)

    def _image_bytes(self, seed, width=1600, height=900):
        url = f"https://picsum.photos/seed/{seed}/{width}/{height}"
        return self._download_image(url) or self._placeholder()

    def handle(self, *args, **options):
        total_count = max(1, options["count"])
        refresh_images = options.get("refresh_images", False)

        self.stdout.write(self.style.NOTICE("\n📰 Enrichissement massif des actualites..."))

        admin_user = User.objects.first()

        categories_data = [
            ("Vie academique", 1),
            ("Annonces officielles", 2),
            ("Evenements", 3),
            ("Resultats", 4),
            ("Partenariats", 5),
            ("Recherche & Innovation", 6),
        ]

        categories = {}
        for name, order in categories_data:
            cat, _ = Category.objects.update_or_create(
                nom=name,
                defaults={
                    "slug": slugify(name),
                    "ordre": order,
                    "is_active": True,
                },
            )
            categories[name] = cat

        programs_data = [
            "Licence Infirmier d'Etat",
            "Licence Sage-femme",
            "Master Sante Publique",
            "Master Gestion des Services de Sante",
        ]

        programs = {}
        for name in programs_data:
            prog, _ = Program.objects.update_or_create(
                nom=name,
                defaults={
                    "slug": slugify(name),
                    "description": f"Actualites liees au programme {name}.",
                    "is_active": True,
                },
            )
            programs[name] = prog

        templates = [
            {
                "title": "Ouverture des inscriptions {year}-{next_year}",
                "resume": "La campagne d'admission est ouverte sur toutes les filieres.",
                "contenu": "La direction informe les candidats que les depots sont ouverts selon le calendrier officiel.",
                "categorie": "Annonces officielles",
                "program": None,
                "important": True,
                "urgent": False,
            },
            {
                "title": "Session d'orientation des nouveaux etudiants #{idx}",
                "resume": "Une session d'orientation est organisee pour faciliter l'integration.",
                "contenu": "L'equipe pedagogique presente l'organisation academique, les regles et les outils numeriques.",
                "categorie": "Vie academique",
                "program": None,
                "important": False,
                "urgent": False,
            },
            {
                "title": "Atelier de simulation clinique #{idx}",
                "resume": "Un atelier pratique renforce les competences cliniques des apprenants.",
                "contenu": "Les enseignants animent des mises en situation professionnelles sur plateaux techniques.",
                "categorie": "Evenements",
                "program": "Licence Infirmier d'Etat",
                "important": False,
                "urgent": False,
            },
            {
                "title": "Publication des resultats semestriels - Serie #{idx}",
                "resume": "Les resultats sont consultables depuis l'espace academique.",
                "contenu": "Les etudiants sont invites a verifier leurs notes et suivre la procedure en cas de reclamation.",
                "categorie": "Resultats",
                "program": "Licence Sage-femme",
                "important": False,
                "urgent": True,
            },
            {
                "title": "Partenariat hospitalier signe avec un centre de reference #{idx}",
                "resume": "Un nouveau partenariat facilite les stages et l'insertion.",
                "contenu": "La convention permet d'elargir les terrains de stage et d'ameliorer l'encadrement pratique.",
                "categorie": "Partenariats",
                "program": None,
                "important": True,
                "urgent": False,
            },
            {
                "title": "Innovation pedagogique: classe numerique active #{idx}",
                "resume": "De nouveaux supports numeriques sont deployes pour les cours.",
                "contenu": "Les contenus pedagogiques sont enrichis et accessibles en continu pour renforcer l'autonomie.",
                "categorie": "Recherche & Innovation",
                "program": "Master Sante Publique",
                "important": False,
                "urgent": False,
            },
        ]

        year = timezone.now().year
        created_news = 0
        updated_news = 0
        created_gallery = 0
        refreshed_images = 0

        for i in range(total_count):
            tpl = templates[i % len(templates)]
            idx = i + 1
            title = tpl["title"].format(idx=idx, year=year, next_year=year + 1)
            slug = slugify(title) or f"actualite-{idx}"

            status = News.STATUS_PUBLISHED
            published_at = timezone.now() - timedelta(days=i)

            news, created = News.objects.update_or_create(
                slug=slug,
                defaults={
                    "titre": title,
                    "resume": tpl["resume"],
                    "contenu": tpl["contenu"],
                    "categorie": categories[tpl["categorie"]],
                    "program": programs.get(tpl["program"]) if tpl["program"] else None,
                    "is_important": tpl["important"],
                    "is_urgent": tpl["urgent"],
                    "status": status,
                    "auteur": admin_user,
                    "published_at": published_at,
                },
            )

            if created:
                created_news += 1
            else:
                updated_news += 1

            if refresh_images or not news.image:
                main_bytes = self._image_bytes(seed=f"esfe-news-main-{slug}")
                news.image.save(f"{slug}-main.jpg", ContentFile(main_bytes), save=False)
                news.save(update_fields=["image", "updated_at"])
                refreshed_images += 1

            # Galerie de 2 images par actualite pour enrichir visuellement la page.
            for order in (1, 2):
                gallery_item = NewsImage.objects.filter(news=news, ordre=order).first()
                if gallery_item is None:
                    gallery_item = NewsImage(news=news, ordre=order)
                    created_gallery += 1

                if refresh_images or not gallery_item.image:
                    gallery_bytes = self._image_bytes(seed=f"esfe-news-gallery-{slug}-{order}")
                    gallery_item.alt_text = f"Illustration {order} - {news.titre}"
                    gallery_item.image.save(
                        f"{slug}-gallery-{order}.jpg",
                        ContentFile(gallery_bytes),
                        save=False,
                    )
                    gallery_item.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✅ Seed News enrichi termine. News: {created_news} creees, {updated_news} mises a jour. "
                f"Galerie creee: {created_gallery}. Images traitees: {refreshed_images}."
            )
        )
