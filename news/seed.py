import random
from django.utils import timezone
from news.models import News, Category, Program
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.first()

categories = list(Category.objects.all())
programs = list(Program.objects.all())

titles = [
    "Mission humanitaire annuelle",
    "Signature partenariat international",
    "Forum entreprises 2026",
    "Distribution kits scolaires",
    "Publication résultats semestre",
    "Séminaire scientifique",
    "Coopération internationale",
    "Campagne sensibilisation",
]

for i in range(25):
    title = f"{random.choice(titles)} #{i+1}"

    News.objects.create(
        titre=title,
        slug=title.lower().replace(" ", "-"),
        resume="Résumé généré automatiquement pour test.",
        contenu="<p>Contenu généré automatiquement pour simulation complète.</p>",
        categorie=random.choice(categories),
        program=random.choice(programs) if programs else None,
        auteur=user,
        status=random.choice(["draft", "published", "archived"]),
        published_at=timezone.now(),
        is_important=random.choice([True, False]),
        is_urgent=random.choice([True, False, False]),
        views_count=random.randint(0, 500)
    )

print("✅ Données générées.")
