
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from django.utils import timezone
from blog.models import Category, Article

User = get_user_model()


class Command(BaseCommand):
    help = "Seed blog live-ready content for ESFE"

    def handle(self, *args, **kwargs):

        admin = User.objects.filter(is_superuser=True).first()

        if not admin:
            self.stdout.write(self.style.ERROR("Crée un superuser d'abord."))
            return

        # ============================
        # CATÉGORIES
        # ============================

        categories_data = [
            ("Actualités institutionnelles",
             "Communiqués officiels et annonces stratégiques de l’ESFE."),
            ("Vie académique",
             "Activités pédagogiques, soutenances et stages."),
            ("Partenariats",
             "Collaborations nationales et internationales."),
            ("Recherche & Innovation",
             "Projets scientifiques et développement pédagogique."),
        ]

        categories = {}

        for name, description in categories_data:
            cat, _ = Category.objects.get_or_create(
                name=name,
                defaults={
                    "slug": slugify(name),
                    "description": description,
                    "is_active": True
                }
            )
            categories[name] = cat

        # ============================
        # ARTICLES
        # ============================

        articles_data = [
            {
                "title": "Ouverture officielle des inscriptions 2026-2027",
                "excerpt": "L’ESFE annonce l’ouverture des candidatures pour la rentrée académique 2026-2027.",
                "content": """
<h2>Une nouvelle année académique ambitieuse</h2>
<p>L’École de Santé Félix Houphouët-Boigny ouvre officiellement ses candidatures pour l’année 2026-2027.</p>

<h2>Formations disponibles</h2>
<ul>
<li>Licence en Sciences Infirmières</li>
<li>Licence en Obstétrique</li>
<li>Technicien de Santé</li>
<li>Master en Santé Publique</li>
</ul>

<p>Les candidatures sont entièrement digitalisées via notre plateforme officielle.</p>
"""
            },
            {
                "title": "Cérémonie de remise des diplômes – Promotion 2025",
                "excerpt": "Une promotion marquée par l’excellence et l’engagement professionnel.",
                "content": """
<h2>Une promotion exemplaire</h2>
<p>La promotion 2025 a démontré un niveau académique remarquable avec un taux de réussite supérieur à 90%.</p>

<h2>Engagement professionnel</h2>
<p>Nos diplômés intègrent rapidement les structures hospitalières partenaires.</p>
"""
            },
            {
                "title": "Signature d’un partenariat hospitalier stratégique",
                "excerpt": "Renforcement de la formation pratique des étudiants de l’ESFE.",
                "content": """
<h2>Renforcement des stages cliniques</h2>
<p>Un nouveau partenariat avec un centre hospitalier de référence à Bamako permettra d’améliorer l’encadrement clinique.</p>

<p>Ce partenariat s’inscrit dans notre politique d’excellence pratique.</p>
"""
            },
            {
                "title": "Innovation pédagogique : digitalisation des cours",
                "excerpt": "L’ESFE intègre des outils numériques avancés dans son système pédagogique.",
                "content": """
<h2>Une pédagogie modernisée</h2>
<p>La digitalisation permet un meilleur suivi académique et une interaction améliorée entre enseignants et étudiants.</p>
"""
            },
            {
                "title": "Conférence scientifique sur la santé communautaire",
                "excerpt": "Une conférence réunissant experts et professionnels de santé.",
                "content": """
<h2>Échanges scientifiques</h2>
<p>L’ESFE a organisé une conférence dédiée aux enjeux de la santé communautaire au Mali.</p>
"""
            },
            {
                "title": "Programme de bourses d’excellence 2026",
                "excerpt": "L’ESFE soutient les étudiants méritants à travers des bourses académiques.",
                "content": """
<h2>Soutien à l’excellence</h2>
<p>Les meilleurs étudiants pourront bénéficier d’un accompagnement financier et académique.</p>
"""
            },
        ]

        for data in articles_data:
            Article.objects.get_or_create(
                title=data["title"],
                defaults={
                    "slug": slugify(data["title"]),
                    "excerpt": data["excerpt"],
                    "content": data["content"],
                    "category": categories["Actualités institutionnelles"],
                    "author": admin,
                    "status": "published",
                    "published_at": timezone.now(),
                    "allow_comments": True
                }
            )

        self.stdout.write(self.style.SUCCESS("Blog live content seeded successfully."))