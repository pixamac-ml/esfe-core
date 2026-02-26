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
    help = "Seed Licence ESFE - Version stratégique enrichie 2025-2026"

    def handle(self, *args, **kwargs):

        self.stdout.write("🚀 Initialisation des formations Licence...")

        # =====================================================
        # BASE STRUCTURE
        # =====================================================

        licence, _ = Cycle.objects.get_or_create(
            name="Licence",
            defaults={
                "min_duration_years": 1,
                "max_duration_years": 3,
                "theme": "accent",
                "description": "Cycle Licence ESFE",
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
        # DOCUMENTS REQUIS (CRÉÉS UNE SEULE FOIS)
        # =====================================================

        documents_data = [
            "Demande timbrée",
            "Copie extrait de naissance ou jugement supplétif",
            "Copie légalisée du diplôme (BAC ou équivalent)",
            "Certificat de fréquentation",
            "Quatre (04) photos d'identité",
        ]

        required_documents = []

        for name in documents_data:
            doc, _ = RequiredDocument.objects.get_or_create(
                name=name,
                defaults={
                    "description": f"Document obligatoire – Année académique {ACADEMIC_YEAR}",
                    "is_mandatory": True,
                }
            )
            required_documents.append(doc)

        # =====================================================
        # PROGRAMMES LICENCE ENRICHIS
        # =====================================================

        LICENCE_PROGRAMMES = [
            {
                "title": "Infirmier d’État",
                "description": """
La Licence Infirmier d’État forme des professionnels capables d’assurer la prise en charge complète du patient dans un environnement hospitalier, communautaire ou humanitaire.

La formation combine sciences biomédicales, soins cliniques avancés, gestion des urgences, éthique médicale et immersion pratique progressive.

Les étudiants bénéficient de stages encadrés en milieu hospitalier dès la première année, avec montée en compétence progressive jusqu’à l’autonomie professionnelle.

Année académique : 2025-2026.
""",
                "learning_outcomes": """
• Maîtrise des soins infirmiers généraux et spécialisés  
• Capacité d’analyse clinique autonome  
• Gestion des urgences médicales  
• Communication thérapeutique  
• Travail en équipe pluridisciplinaire
""",
                "career_opportunities": """
Hôpitaux publics et privés, centres de santé, ONG médicales, structures humanitaires, spécialisation ultérieure.
""",
            },
            {
                "title": "Sage-Femme",
                "description": """
Formation spécialisée en santé maternelle et néonatale.

Le programme prépare à la gestion complète du suivi prénatal, de l’accouchement et du suivi postnatal, avec forte immersion clinique.

Les étudiantes sont formées à intervenir dans des contextes urbains et ruraux, avec rigueur et responsabilité.

Année académique : 2025-2026.
""",
                "learning_outcomes": """
• Suivi prénatal et postnatal  
• Gestion sécurisée de l’accouchement  
• Détection des complications  
• Soins néonatals immédiats
""",
                "career_opportunities": """
Maternités publiques et privées, ONG santé reproductive, structures hospitalières.
""",
            },
            {
                "title": "Biologie Médicale",
                "description": """
Formation scientifique orientée vers le diagnostic biomédical et les analyses cliniques.

Le programme couvre microbiologie, hématologie, biochimie et contrôle qualité en laboratoire.

Les étudiants maîtrisent les normes internationales de sécurité biologique.

Année académique : 2025-2026.
""",
                "learning_outcomes": """
• Réalisation d’analyses biologiques  
• Interprétation des résultats  
• Gestion des équipements  
• Normes de biosécurité
""",
                "career_opportunities": """
Laboratoires hospitaliers, centres de diagnostic, instituts de recherche.
""",
            },
            {
                "title": "Technicien Supérieur en Pharmacie",
                "description": """
Formation orientée vers la gestion pharmaceutique et la dispensation sécurisée des médicaments.

Le programme inclut pharmacologie appliquée, gestion des stocks et réglementation sanitaire.

Année académique : 2025-2026.
""",
                "learning_outcomes": """
• Connaissance des classes thérapeutiques  
• Gestion des stocks  
• Application de la réglementation
""",
                "career_opportunities": """
Officines, pharmacies hospitalières, entreprises pharmaceutiques.
""",
            },
            {
                "title": "Santé Communautaire",
                "description": """
Formation stratégique en prévention et gestion des programmes sanitaires communautaires.

Les étudiants apprennent à concevoir, suivre et évaluer des projets de santé publique adaptés aux réalités locales.

Année académique : 2025-2026.
""",
                "learning_outcomes": """
• Conception de projets sanitaires  
• Analyse des indicateurs  
• Intervention communautaire
""",
                "career_opportunities": """
ONG, collectivités, ministère de la santé.
""",
            },
        ]

        for data in LICENCE_PROGRAMMES:

            programme, _ = Programme.objects.update_or_create(
                title=data["title"],
                defaults={
                    "cycle": licence,
                    "filiere": filiere_sante,
                    "diploma_awarded": diploma_sup,
                    "duration_years": 3,
                    "short_description": f"{data['title']} – Licence professionnelle ({ACADEMIC_YEAR})",
                    "description": data["description"],
                    "learning_outcomes": data["learning_outcomes"],
                    "career_opportunities": data["career_opportunities"],
                    "program_structure": """
• Enseignements théoriques  
• Travaux dirigés  
• Stages cliniques  
• Évaluations continues
""",
                    "is_active": True,
                }
            )

            # Lier les documents au programme
            for doc in required_documents:
                ProgrammeRequiredDocument.objects.get_or_create(
                    programme=programme,
                    document=doc
                )

            programme.years.all().delete()

            for year_number in range(1, 4):
                year_obj = ProgrammeYear.objects.create(
                    programme=programme,
                    year_number=year_number
                )

                Fee.objects.create(programme_year=year_obj, label="Inscription", amount=130000, due_month="Octobre")
                Fee.objects.create(programme_year=year_obj, label="Janvier", amount=140000, due_month="Janvier")
                Fee.objects.create(programme_year=year_obj, label="Mars", amount=140000, due_month="Mars")

        self.stdout.write(self.style.SUCCESS("✅ Seed Licence propre et structuré terminé."))