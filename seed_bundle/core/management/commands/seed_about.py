from django.core.management.base import BaseCommand
from core.models import AboutSection


class Command(BaseCommand):
    help = "Seed initial data for About page (new structure)"

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("Seeding About page (new structure)..."))

        # Nettoyage complet
        AboutSection.objects.all().delete()

        sections_data = [
            {
                "section_key": "identity",
                "title": "L’École de Santé Félix Houphouët-Boigny",
                "subtitle": "École supérieure privée spécialisée dans les sciences de la santé",
                "content": """
<p>L’École de Santé Félix Houphouët-Boigny est une école supérieure privée spécialisée dans la formation paramédicale et scientifique au Mali.</p>

<p>À travers des formations structurées selon le système Licence-Master-Doctorat (LMD), l’école développe des compétences techniques, éthiques et professionnelles adaptées aux réalités hospitalières et communautaires.</p>

<p>Créée par Décision N°2018-0000613 MESRS-SG du 13 avril 2018 et officiellement ouverte par Arrêté N°6093/MESRS-SG du 31 décembre 2021.</p>
""",
                "highlights": [
                    "École supérieure privée reconnue par l’État",
                    "Formations paramédicales conformes au système LMD",
                    "Ancrage professionnel et terrain",
                ],
                "icon": "fa-solid fa-school",
                "background": "white",
                "order": 1,
            },
            {
                "section_key": "vision",
                "title": "Vision & Engagement Académique",
                "subtitle": "",
                "content": """
<p>L’École place l’excellence académique et l’éthique professionnelle au cœur de son projet pédagogique.</p>

<p>Elle œuvre pour le développement d’un capital humain qualifié, capable de répondre efficacement aux défis sanitaires contemporains.</p>
""",
                "highlights": [
                    "Excellence académique",
                    "Recherche appliquée",
                    "Innovation pédagogique",
                    "Transformation numérique",
                ],
                "icon": "fa-solid fa-heart-pulse",
                "background": "light",
                "order": 2,
            },
            {
                "section_key": "governance",
                "title": "Gouvernance & Assurance Qualité",
                "subtitle": "",
                "content": """
<p>L’École évolue sous la gouvernance structurée de l’Université Privée Félix Houphouët-Boigny-Mali.</p>

<p>Son organisation repose sur un Rectorat, une Direction Générale et des instances académiques garantissant rigueur et transparence.</p>
""",
                "icon": "fa-solid fa-sitemap",
                "background": "white",
                "order": 3,
            },
            {
                "section_key": "infrastructure",
                "title": "Infrastructures & Transformation Numérique",
                "subtitle": "",
                "content": """
<ul>
<li>Modernisation des salles et laboratoires</li>
<li>Bibliothèque physique et numérique</li>
<li>Plateformes numériques académiques</li>
<li>Laboratoires virtuels</li>
</ul>
""",
                "icon": "fa-solid fa-building-columns",
                "background": "light",
                "order": 4,
            },
            {
                "section_key": "student_life",
                "title": "Vie Estudiantine",
                "subtitle": "",
                "content": """
<ul>
<li>Association étudiante</li>
<li>Activités culturelles et sportives</li>
<li>Service médico-social</li>
<li>Engagement communautaire</li>
</ul>
""",
                "icon": "fa-solid fa-users",
                "background": "white",
                "order": 5,
            },
            {
                "section_key": "network",
                "title": "Annexes & Partenariats",
                "subtitle": "",
                "content": """
<p>L’École s’appuie sur un réseau d’annexes stratégiques et de partenaires académiques nationaux et internationaux.</p>
""",
                "icon": "fa-solid fa-globe",
                "background": "light",
                "order": 6,
            },
        ]

        for data in sections_data:
            AboutSection.objects.create(
                section_key=data["section_key"],
                title=data["title"],
                subtitle=data.get("subtitle"),
                content=data.get("content"),
                highlights=data.get("highlights"),
                icon=data.get("icon"),
                background=data.get("background"),
                order=data.get("order"),
                is_active=True,
            )

        self.stdout.write(self.style.SUCCESS("About page seeded successfully (new structure)."))