import base64
from datetime import timedelta
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify

from blog.models import Category, Article, ArticleImage

User = get_user_model()

# Placeholder local en secours si une URL distante echoue.
PNG_1X1_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/w8AAusB9Y9L3nQAAAAASUVORK5CYII="
)


class Command(BaseCommand):
    help = "Seed enrichi du blog avec articles et images distantes de test"

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=30,
            help="Nombre d'articles a creer (defaut: 30)",
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

        self.stdout.write(self.style.NOTICE("\n📝 Enrichissement massif du blog..."))

        admin = User.objects.filter(is_superuser=True).first()
        if not admin:
            self.stdout.write(self.style.ERROR("Crée un superuser d'abord."))
            return

        categories_data = [
            ("Actualites institutionnelles", "Communiques officiels et annonces strategiques."),
            ("Vie academique", "Activites pedagogiques, soutenances et stages."),
            ("Partenariats", "Collaborations nationales et internationales."),
            ("Recherche & Innovation", "Projets scientifiques et developpement pedagogique."),
            ("Temoignages", "Histoires de succes d'etudiants et diplomes."),
            ("Sante Communautaire", "Sujets de sante publique et preventiion."),
        ]

        categories = {}
        for name, description in categories_data:
            cat, _ = Category.objects.update_or_create(
                name=name,
                defaults={
                    "slug": slugify(name),
                    "description": description,
                    "is_active": True,
                },
            )
            categories[name] = cat

        article_templates = [
            {
                "title": "Ouverture des inscriptions {year}-{next_year}",
                "excerpt": "L'ESFE annonce l'ouverture des candidatures pour la rentree academique.",
                "content": "<h2>Nouvelle annee academique</h2><p>L'inscription est entierement digitalisee via notre plateforme officielle.</p>",
                "category": "Actualites institutionnelles",
                "seo_title": "Inscriptions {year} - ESFE Mali",
                "seo_desc": "Candidatez pour les formations ESFE Mali {year}.",
            },
            {
                "title": "Session d'orientation des etudiants #{idx}",
                "excerpt": "Une presentation complete de l'organisation academique et des outils numeriques.",
                "content": "<h2>Bienvenue a ESFE</h2><p>Notre equipe pedagogique vous presente les fondamentaux de votre parcours.</p>",
                "category": "Vie academique",
                "seo_title": "Orientation etudiants ESFE",
                "seo_desc": "Session d'integraton et presentation du programme academique.",
            },
            {
                "title": "Ceremonie de remise des diplomes - Promotion {year}",
                "excerpt": "Une promotion marquee par l'excellence et l'engagement professionnel.",
                "content": "<h2>Succes academique</h2><p>Nos diplomes integrent rapidement les structures de sante.</p>",
                "category": "Actualites institutionnelles",
                "seo_title": "Diplomes ESFE {year}",
                "seo_desc": "Remise officielle des diplomes aux finissants ESFE.",
            },
            {
                "title": "Partenariat hospitalier #{idx} signe",
                "excerpt": "Renforcement de la formation pratique par une collaboration strategique.",
                "content": "<h2>Stages cliniques</h2><p>Ce partenariat elargit les terrains de stage et ameliore l'encadrement clinique.</p>",
                "category": "Partenariats",
                "seo_title": "Partenaire clinique ESFE",
                "seo_desc": "Convention de stage et formation pratique avec nos partenaires.",
            },
            {
                "title": "Innovation pedagogique: classe numerique #{idx}",
                "excerpt": "Digitalisation des cours et interactivite amelioree entre enseignants et etudiants.",
                "content": "<h2>Pedagogie moderne</h2><p>Les outils numeriques transforment notre approche educative.</p>",
                "category": "Recherche & Innovation",
                "seo_title": "Digitalisation pedagogique ESFE",
                "seo_desc": "Outils numeriques et innovation dans l'enseignement.",
            },
            {
                "title": "Conference scientifique #{idx}: Sante communautaire",
                "excerpt": "Echanges sur les enjeux sanitaires et publics au Mali.",
                "content": "<h2>Recherche appliquee</h2><p>ESFE organise des conferences regroupant experts et professionnels de sante.</p>",
                "category": "Recherche & Innovation",
                "seo_title": "Conference sante ESFE",
                "seo_desc": "Discussions scientifiques sur la sante communautaire.",
            },
            {
                "title": "Temoignage: Reussite de #{idx}",
                "excerpt": "L'histoire inspirante d'une diplomee d'ESFE.",
                "content": "<h2>Du reve a la realite</h2><p>Voici le parcours exemplaire d'une ancienne etudiante d'ESFE.</p>",
                "category": "Temoignages",
                "seo_title": "Parcours professionnel ESFE",
                "seo_desc": "Temoignage de reussite d'une diplomee ESFE Mali.",
            },
            {
                "title": "Prevention et sante publique: Guide #{idx}",
                "excerpt": "Conseils pratiques pour une meilleure sante communautaire.",
                "content": "<h2>Education sanitaire</h2><p>Sensibilisation aux pratiques de prevention et promotion de la sante.</p>",
                "category": "Sante Communautaire",
                "seo_title": "Sante publique Mali",
                "seo_desc": "Ressources et conseils en prevention et sante communautaire.",
            },
            {
                "title": "Programme de bourses d'excellence {year}",
                "excerpt": "ESFE soutient les etudiants meritants a travers des bourses academiques.",
                "content": "<h2>Soutien financier</h2><p>Les meilleurs etudiants beneficient d'un accompagnement financier et academique.</p>",
                "category": "Actualites institutionnelles",
                "seo_title": "Bourses ESFE Mali {year}",
                "seo_desc": "Programme de bourses d'excellence pour les etudiants meritants.",
            },
        ]

        year = timezone.now().year
        created_articles = 0
        updated_articles = 0
        created_gallery = 0
        refreshed_images = 0

        for i in range(total_count):
            tpl = article_templates[i % len(article_templates)]
            idx = i + 1

            title = tpl["title"].format(idx=idx, year=year, next_year=year + 1)
            slug = slugify(title) or f"article-{idx}"

            published_at = timezone.now() - timedelta(days=i)

            article, created = Article.objects.update_or_create(
                slug=slug,
                defaults={
                    "title": title,
                    "excerpt": tpl["excerpt"],
                    "content": tpl["content"],
                    "category": categories[tpl["category"]],
                    "author": admin,
                    "status": "published",
                    "published_at": published_at,
                    "allow_comments": True,
                    "meta_title": tpl["seo_title"].format(idx=idx, year=year, next_year=year + 1),
                    "meta_description": tpl["seo_desc"],
                },
            )

            if created:
                created_articles += 1
            else:
                updated_articles += 1

            # Image principale featured
            if refresh_images or not article.featured_image:
                featured_bytes = self._image_bytes(seed=f"esfe-blog-featured-{slug}")
                article.featured_image.save(
                    f"{slug}-featured.jpg",
                    ContentFile(featured_bytes),
                    save=False,
                )
                article.save(update_fields=["featured_image", "updated_at"])
                refreshed_images += 1

            # Galerie de 3 images par article
            for order in (1, 2, 3):
                gallery_item = ArticleImage.objects.filter(article=article, id=order).first()
                if gallery_item is None:
                    gallery_item = ArticleImage(article=article)
                    created_gallery += 1

                if refresh_images or not gallery_item.image:
                    gallery_bytes = self._image_bytes(seed=f"esfe-blog-gallery-{slug}-{order}")
                    gallery_item.caption = f"Illustration {order} - {article.title}"
                    gallery_item.image.save(
                        f"{slug}-gallery-{order}.jpg",
                        ContentFile(gallery_bytes),
                        save=False,
                    )
                    gallery_item.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✅ Seed Blog enrichi termine. Articles: {created_articles} crees, {updated_articles} mises a jour. "
                f"Galerie creee: {created_gallery}. Images traitees: {refreshed_images}."
            )
        )
