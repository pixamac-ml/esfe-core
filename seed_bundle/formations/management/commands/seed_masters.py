from django.core.management.base import BaseCommand
from formations.models import (
    Cycle,
    Diploma,
    Filiere,
    Programme,
    ProgrammeYear,
    Fee,
    RequiredDocument,
    ProgrammeRequiredDocument,
)

ACADEMIC_YEAR = "2025-2026"


class Command(BaseCommand):
    help = "Seed Master ESFE - Version stratégique enrichie 2025-2026"

    def handle(self, *args, **kwargs):

        self.stdout.write("🚀 Initialisation des formations MASTER...")

        # =====================================================
        # BASE STRUCTURE
        # =====================================================

        master, _ = Cycle.objects.get_or_create(
            name="Master",
            defaults={
                "min_duration_years": 2,
                "max_duration_years": 2,
                "theme": "secondary",
                "description": "Cycle Master ESFE",
                "is_active": True,
            }
        )

        diploma_sup, _ = Diploma.objects.get_or_create(
            name="Diplôme Supérieur en Sciences de la Santé",
            defaults={"level": "superieur"}
        )

        filiere_sante, _ = Filiere.objects.get_or_create(
            name="Sciences de la Santé",
            defaults={"is_active": True}
        )

        # =====================================================
        # DOCUMENTS REQUIS MASTER
        # =====================================================

        documents_data = [
            "Demande timbrée",
            "Copie extrait de naissance",
            "Copie légalisée Licence ou équivalent",
            "Curriculum Vitae (CV)",
            "Lettre de motivation",
            "Quatre (04) photos d'identité",
        ]

        required_documents = []

        for name in documents_data:
            doc, _ = RequiredDocument.objects.get_or_create(
                name=name,
                defaults={
                    "description": f"Document requis pour admission Master – {ACADEMIC_YEAR}",
                    "is_mandatory": True,
                }
            )
            required_documents.append(doc)

        # =====================================================
        # PROGRAMMES MASTER
        # =====================================================

        MASTER_PROGRAMMES = [

            {
                "title": "Master en Biologie Médicale",
                "description": """
        Le Master en Biologie Médicale forme des experts capables de superviser des laboratoires biomédicaux et de piloter des projets de recherche appliquée.

        La formation approfondit microbiologie avancée, biologie moléculaire, immunologie clinique et gestion qualité en laboratoire.

        Année académique : 2025-2026.
        """,
                "learning_outcomes": """
        • Supervision de laboratoires biomédicaux  
        • Analyse biologique avancée  
        • Gestion qualité et accréditation  
        • Recherche scientifique appliquée
        """,
                "career_opportunities": """
        Laboratoires de référence, instituts de recherche, centres hospitaliers universitaires.
        """,
            },

            {
                "title": "Master en Gynécologie Obstétrique",
                "description": """
        Programme avancé destiné aux professionnels souhaitant se spécialiser en santé reproductive et obstétrique clinique.

        Il renforce les compétences en prise en charge des grossesses complexes et en gestion des urgences obstétricales.

        Année académique : 2025-2026.
        """,
                "learning_outcomes": """
        • Gestion des grossesses à risque  
        • Intervention en urgences obstétricales  
        • Planification stratégique des services maternels
        """,
                "career_opportunities": """
        Centres hospitaliers spécialisés, cliniques obstétricales, programmes nationaux de santé maternelle.
        """,
            },

            {
                "title": "Master en Manager en Santé",
                "description": """
        Le Master en Manager en Santé prépare des cadres supérieurs capables de piloter des établissements sanitaires.

        Il intègre management stratégique, gestion financière hospitalière et leadership institutionnel.

        Année académique : 2025-2026.
        """,
                "learning_outcomes": """
        • Gestion stratégique d’établissement  
        • Pilotage budgétaire  
        • Leadership organisationnel  
        • Audit et performance hospitalière
        """,
                "career_opportunities": """
        Directions hospitalières, ONG internationales, institutions sanitaires.
        """,
            },

            {
                "title": "Master en Biochimie",
                "description": """
        Programme scientifique avancé orienté vers la recherche biomoléculaire et les applications cliniques.

        La formation couvre biologie moléculaire, enzymologie et recherche translationnelle.

        Année académique : 2025-2026.
        """,
                "learning_outcomes": """
        • Recherche biomoléculaire  
        • Analyse biochimique avancée  
        • Développement de protocoles expérimentaux
        """,
                "career_opportunities": """
        Instituts de recherche, laboratoires pharmaceutiques, universités.
        """,
            },

            {
                "title": "Master en Pédagogie en Santé",
                "description": """
        Ce programme forme des formateurs et encadreurs spécialisés dans l’enseignement des sciences de la santé.

        Il développe les compétences en ingénierie pédagogique et innovation éducative.

        Année académique : 2025-2026.
        """,
                "learning_outcomes": """
        • Conception de curricula  
        • Méthodologies pédagogiques innovantes  
        • Évaluation des apprentissages
        """,
                "career_opportunities": """
        Instituts de formation sanitaire, universités, centres pédagogiques.
        """,
            },

            {
                "title": "Master en Suivi et Évaluation",
                "description": """
        Formation spécialisée dans le monitoring et l’évaluation des programmes sanitaires et humanitaires.

        Le programme développe des compétences en analyse d’impact et gestion axée sur les résultats.

        Année académique : 2025-2026.
        """,
                "learning_outcomes": """
        • Conception de systèmes de suivi  
        • Analyse d’impact  
        • Gestion basée sur les résultats
        """,
                "career_opportunities": """
        ONG internationales, agences de développement, ministères.
        """,
            },

            {
                "title": "Master en Nutrition",
                "description": """
        Programme avancé en nutrition clinique et sécurité alimentaire.

        Il prépare des spécialistes capables de piloter des programmes nutritionnels nationaux.

        Année académique : 2025-2026.
        """,
                "learning_outcomes": """
        • Nutrition clinique avancée  
        • Gestion de programmes nutritionnels  
        • Analyse des politiques alimentaires
        """,
                "career_opportunities": """
        Programmes nationaux de nutrition, ONG, organisations internationales.
        """,
            },

            {
                "title": "Master en Santé Environnementale",
                "description": """
        Formation stratégique en gestion des risques environnementaux et sanitaires.

        Le programme couvre hygiène publique, sécurité environnementale et prévention des risques.

        Année académique : 2025-2026.
        """,
                "learning_outcomes": """
        • Analyse des risques environnementaux  
        • Gestion de crises sanitaires  
        • Politiques de prévention
        """,
                "career_opportunities": """
        Collectivités territoriales, ONG, institutions publiques.
        """,
            },

            {
                "title": "Master en Attaché de Recherche Clinique",
                "description": """
        Formation spécialisée dans la coordination et la gestion des essais cliniques.

        Les étudiants apprennent la réglementation internationale et la méthodologie de recherche clinique.

        Année académique : 2025-2026.
        """,
                "learning_outcomes": """
        • Coordination d’essais cliniques  
        • Réglementation internationale  
        • Analyse de données cliniques
        """,
                "career_opportunities": """
        Centres hospitaliers, industries pharmaceutiques, instituts de recherche.
        """,
            },

            {
                "title": "Master en Data Manager",
                "description": """
        Programme orienté vers la gestion et l’analyse des données sanitaires à grande échelle.

        Il combine statistiques avancées, bases de données et santé numérique.

        Année académique : 2025-2026.
        """,
                "learning_outcomes": """
        • Gestion de bases de données sanitaires  
        • Analyse statistique avancée  
        • Exploitation de données massives
        """,
                "career_opportunities": """
        Institutions de santé publique, ONG, organismes internationaux.
        """,
            },

        ]
        for data in MASTER_PROGRAMMES:

            programme, _ = Programme.objects.update_or_create(
                title=data["title"],
                defaults={
                    "cycle": master,
                    "filiere": filiere_sante,
                    "diploma_awarded": diploma_sup,
                    "duration_years": 2,
                    "short_description": f"{data['title']} – Expertise avancée ({ACADEMIC_YEAR})",
                    "description": data["description"],
                    "learning_outcomes": data["learning_outcomes"],
                    "career_opportunities": data["career_opportunities"],
                    "program_structure": """
• Cours magistraux avancés  
• Séminaires spécialisés  
• Travaux de recherche  
• Stage professionnel  
• Mémoire de fin d’études
""",
                    "is_active": True,
                }
            )

            # Lier les documents
            for doc in required_documents:
                ProgrammeRequiredDocument.objects.get_or_create(
                    programme=programme,
                    document=doc
                )

            programme.years.all().delete()

            # ======================
            # ANNÉE 1 : 810 000
            # ======================
            year1 = ProgrammeYear.objects.create(
                programme=programme,
                year_number=1
            )

            Fee.objects.create(programme_year=year1, label="Inscription", amount=410000, due_month="Octobre")
            Fee.objects.create(programme_year=year1, label="Janvier", amount=200000, due_month="Janvier")
            Fee.objects.create(programme_year=year1, label="Mars", amount=200000, due_month="Mars")

            # ======================
            # ANNÉE 2 : 1 200 000
            # ======================
            year2 = ProgrammeYear.objects.create(
                programme=programme,
                year_number=2
            )

            Fee.objects.create(programme_year=year2, label="Inscription", amount=600000, due_month="Octobre")
            Fee.objects.create(programme_year=year2, label="Janvier", amount=300000, due_month="Janvier")
            Fee.objects.create(programme_year=year2, label="Mars", amount=300000, due_month="Mars")

        self.stdout.write(self.style.SUCCESS("✅ Seed MASTER enrichi terminé proprement."))