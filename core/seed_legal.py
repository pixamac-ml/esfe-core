# core/seed_legal.py

from django.db import transaction
from core.models import (
    Institution,
    LegalPage,
    LegalSection,
    LegalSidebarBlock
)


@transaction.atomic
def run():

    print("=== Initialisation du module juridique ===")

    # ==========================================================
    # INSTITUTION
    # ==========================================================

    institution, created = Institution.objects.update_or_create(
        name="École Supérieure de Formation et d’Excellence",
        defaults={
            "short_name": "ESFE",
            "address": "Bamako",
            "city": "Bamako",
            "country": "Mali",
            "phone": "+223 XX XX XX XX",
            "email": "contact@esfe.edu.ml",
            "legal_status": "Établissement privé d’enseignement supérieur",
            "approval_number": "AGR-2026-001",
            "hosting_provider": "Infrastructure sécurisée",
            "hosting_location": "Hébergement professionnel protégé",
        }
    )

    print("Institution synchronisée.")

    # ==========================================================
    # FONCTION GÉNÉRIQUE POUR PAGE
    # ==========================================================

    def create_or_update_page(page_type, title, introduction, sections, sidebar):

        page, created = LegalPage.objects.update_or_create(
            page_type=page_type,
            defaults={
                "title": title,
                "introduction": introduction,
                "version": "1.0",
                "status": "published",
            }
        )

        print(f"Page '{title}' synchronisée.")

        # Supprime anciennes sections pour éviter doublons
        page.sections.all().delete()
        page.sidebar_blocks.all().delete()

        # Recrée sections
        for index, section in enumerate(sections, start=1):
            LegalSection.objects.create(
                page=page,
                title=section["title"],
                content=section["content"],
                order=index,
            )

        # Recrée sidebar
        for index, block in enumerate(sidebar, start=1):
            LegalSidebarBlock.objects.create(
                page=page,
                title=block["title"],
                content=block["content"],
                order=index,
            )

    # ==========================================================
    # MENTIONS LÉGALES
    # ==========================================================

    create_or_update_page(
        page_type="legal",
        title="Mentions légales",
        introduction="""
        Les présentes mentions légales définissent les informations relatives
        à l’identité juridique et à l’organisation institutionnelle.
        """,
        sections=[
            {
                "title": "Identification de l’établissement",
                "content": """
                L’établissement est un organisme d’enseignement supérieur
                basé au Mali et régi par les dispositions légales en vigueur.
                """
            },
            {
                "title": "Gouvernance",
                "content": """
                L’institution dispose d’organes stratégiques comprenant
                un Conseil d’Administration et un Conseil Académique.
                """
            },
            {
                "title": "Responsabilité",
                "content": """
                Les informations publiées sur le site sont mises à jour régulièrement.
                L’établissement décline toute responsabilité en cas d’interruption temporaire.
                """
            },
        ],
        sidebar=[
            {
                "title": "Contact institutionnel",
                "content": "contact@esfe.edu.ml<br>+223 XX XX XX XX"
            },
            {
                "title": "Référence administrative",
                "content": "Numéro d’agrément : AGR-2026-001"
            },
        ]
    )

    # ==========================================================
    # POLITIQUE DE CONFIDENTIALITÉ
    # ==========================================================

    create_or_update_page(
        page_type="privacy",
        title="Politique de confidentialité",
        introduction="""
        Cette politique décrit les modalités de collecte,
        d’utilisation et de protection des données personnelles.
        """,
        sections=[
            {
                "title": "Données collectées",
                "content": """
                Les données collectées incluent les informations académiques,
                administratives et financières nécessaires au traitement des candidatures.
                """
            },
            {
                "title": "Finalité du traitement",
                "content": """
                Les données sont utilisées exclusivement pour la gestion administrative,
                académique et réglementaire.
                """
            },
            {
                "title": "Sécurité",
                "content": """
                Des mesures techniques et organisationnelles sont mises en œuvre
                afin d’assurer la protection des données personnelles.
                """
            },
        ],
        sidebar=[
            {
                "title": "Contact données",
                "content": "contact@esfe.edu.ml"
            }
        ]
    )

    print("=== Seed juridique terminé avec succès ===")
