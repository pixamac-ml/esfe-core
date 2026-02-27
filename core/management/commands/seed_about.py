from django.core.management.base import BaseCommand
from core.models import AboutSection, AboutContentBlock


class Command(BaseCommand):
    help = "Seed initial data for About page"

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("Seeding About page..."))

        # Supprimer ancienne section si existe
        AboutSection.objects.filter(slug="a-propos").delete()

        # Créer section principale
        section = AboutSection.objects.create(
            title="À propos",
            slug="a-propos",
            description="Présentation institutionnelle de l’École Privée de Santé Félix Houphouët Boigny (EPSFé).",
            is_active=True,
            order=1,
        )

        blocks_data = [
            {
                "title": "Une institution engagée pour la santé au Mali et en Afrique",
                "content": """
<p>Fondée pour répondre aux besoins urgents en formation supérieure dans le domaine de la santé, l’École Privée de Santé Félix Houphouët Boigny (EPSFé) s’est donnée pour mission de contribuer à l’amélioration du système sanitaire au Mali et en Afrique.</p>

<p>Guidée par une vision fondée sur l’excellence, l’éthique et l’innovation, l’EPSFé forme des professionnels compétents, responsables et profondément humanistes.</p>
"""
            },
            {
                "title": "Reconnaissance et accréditation officielle",
                "content": """
<p>L’École Privée de Santé Félix Houphouët Boigny (EPSFé) a été créée par la Décision N°2018-0000613 MESRS-SG du 13 Avril 2018.</p>

<p>Son ouverture officielle a été autorisée par l’Arrêté N°6093/MESRS-SG du 31 décembre 2021.</p>
"""
            },
            {
                "title": "Offre de formation",
                "content": """
<p><strong>Licence :</strong></p>
<ul>
<li>Infirmier d’État</li>
<li>Sage-femme</li>
<li>Nutrition</li>
<li>Biologie médicale</li>
</ul>

<p><strong>Master :</strong></p>
<ul>
<li>Gynécologie Obstétrique</li>
<li>Épidémiologie</li>
<li>Nutrition</li>
<li>Biologie médicale</li>
<li>Management des Services de Santé</li>
<li>Pédagogie en Sciences de la Santé</li>
</ul>
"""
            },
            {
                "title": "Une pédagogie orientée vers l’excellence",
                "content": """
<ul>
<li>Accompagnement de l’étudiant jusqu’à l’insertion professionnelle</li>
<li>Conformité au système LMD</li>
<li>Formation continue des professionnels</li>
<li>Développement de la recherche scientifique</li>
</ul>
"""
            },
            {
                "title": "Gouvernance et assurance qualité",
                "content": """
<p>L’EPSFé est dotée d’organes de gouvernance solides :</p>
<ul>
<li>Conseil d’Administration</li>
<li>Conseil d’École</li>
<li>Conseil Scientifique et Pédagogique</li>
<li>Cellule Interne d’Assurance Qualité</li>
</ul>
"""
            },
            {
                "title": "Infrastructures et transformation numérique",
                "content": """
<ul>
<li>Modernisation des salles et laboratoires</li>
<li>Bibliothèque physique et numérique</li>
<li>Plateformes numériques académiques</li>
<li>Laboratoires virtuels</li>
</ul>
"""
            },
            {
                "title": "Vie universitaire",
                "content": """
<ul>
<li>Association étudiante</li>
<li>Activités culturelles et sportives</li>
<li>Service médico-social</li>
<li>Engagement communautaire</li>
</ul>
"""
            },
        ]

        for index, block in enumerate(blocks_data, start=1):
            AboutContentBlock.objects.create(
                section=section,
                title=block["title"],
                content=block["content"],
                order=index,
                is_active=True,
            )

        self.stdout.write(self.style.SUCCESS("About page seeded successfully."))