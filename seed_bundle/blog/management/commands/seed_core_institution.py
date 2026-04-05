from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group
from core.models import (
    Institution,
    LegalPage,
    LegalSection,
    LegalSidebarBlock,
    InstitutionStat,
    AboutSection
)


class Command(BaseCommand):
    help = "Seed institutionnel complet ESFé"

    def handle(self, *args, **kwargs):

        # ======================================================
        # GROUPES MÉTIERS OFFICIELS
        # ======================================================

        groups = [
            "Direction Generale",
            "Secretaire Academique",
            "Gestionnaire Administrative",
            "Responsable Qualite",
            "Support Technique",
        ]

        for name in groups:
            Group.objects.get_or_create(name=name)

        # ======================================================
        # INSTITUTION
        # ======================================================

        Institution.objects.get_or_create(
            name="École de Santé Félix Houphouët-Boigny",
            defaults={
                "short_name": "ESFé",
                "address": "Moribabougou",
                "city": "Bamako",
                "country": "Mali",
                "phone": "+223 XX XX XX XX",
                "email": "contact@esfe.mali",
                "legal_status": (
                    "Établissement privé d’enseignement supérieur paramédical "
                    "agréé par les autorités compétentes de la République du Mali."
                ),
                "approval_number": "N° AGR-ESFE-2026-001",
                "director_title": "Direction Générale",
                "hosting_provider": "Infrastructure Cloud Sécurisée",
                "hosting_location": "Union Européenne"
            }
        )

        # ======================================================
        # STATISTIQUES INSTITUTIONNELLES
        # ======================================================

        stats = [
            ("Étudiants formés depuis la création", 1850, "+"),
            ("Taux d’insertion professionnelle", 94, "%"),
            ("Laboratoires spécialisés", 4, ""),
            ("Partenariats hospitaliers", 12, "+"),
            ("Années d’excellence académique", 15, "+"),
        ]

        for index, (label, value, suffix) in enumerate(stats):
            InstitutionStat.objects.get_or_create(
                label=label,
                defaults={
                    "value": value,
                    "suffix": suffix,
                    "order": index
                }
            )

        # ======================================================
        # MENTIONS LÉGALES (RÉDIGÉES SÉRIEUSEMENT)
        # ======================================================

        legal_page, _ = LegalPage.objects.get_or_create(
            page_type="legal",
            defaults={
                "title": "Mentions légales",
                "introduction": (
                    "Le présent site est la propriété officielle de l’École de Santé "
                    "Félix Houphouët-Boigny (ESFé), établissement d’enseignement "
                    "supérieur paramédical situé à Moribabougou, Bamako, République du Mali."
                ),
                "version": "1.0",
                "status": "published"
            }
        )

        LegalSection.objects.get_or_create(
            page=legal_page,
            title="Identification de l’établissement",
            defaults={
                "content": (
                    "Dénomination : École de Santé Félix Houphouët-Boigny (ESFé). "
                    "Statut : Établissement privé d’enseignement supérieur paramédical. "
                    "Siège : Moribabougou, Bamako, Mali."
                ),
                "order": 1
            }
        )

        LegalSection.objects.get_or_create(
            page=legal_page,
            title="Propriété intellectuelle",
            defaults={
                "content": (
                    "L’ensemble des contenus publiés sur le site (textes, images, "
                    "documents pédagogiques, éléments graphiques) est protégé par "
                    "la législation en vigueur relative à la propriété intellectuelle."
                ),
                "order": 2
            }
        )

        LegalSection.objects.get_or_create(
            page=legal_page,
            title="Responsabilité",
            defaults={
                "content": (
                    "L’établissement s’efforce de fournir des informations fiables "
                    "et régulièrement mises à jour. Toutefois, il ne saurait être tenu "
                    "responsable d’éventuelles erreurs ou omissions."
                ),
                "order": 3
            }
        )

        LegalSidebarBlock.objects.get_or_create(
            page=legal_page,
            title="Coordonnées officielles",
            defaults={
                "content": (
                    "Adresse : Moribabougou, Bamako, Mali<br>"
                    "Email : contact@esfe.mali<br>"
                    "Téléphone : +223 XX XX XX XX"
                ),
                "order": 1
            }
        )

        # ======================================================
        # POLITIQUE DE CONFIDENTIALITÉ
        # ======================================================

        privacy_page, _ = LegalPage.objects.get_or_create(
            page_type="privacy",
            defaults={
                "title": "Politique de confidentialité",
                "introduction": (
                    "L’École de Santé Félix Houphouët-Boigny attache une importance "
                    "majeure à la protection des données personnelles des candidats, "
                    "étudiants et partenaires."
                ),
                "version": "1.0",
                "status": "published"
            }
        )

        LegalSection.objects.get_or_create(
            page=privacy_page,
            title="Données collectées",
            defaults={
                "content": (
                    "Les données collectées via le site concernent principalement "
                    "les candidatures académiques, les inscriptions administratives "
                    "et les demandes d’information."
                ),
                "order": 1
            }
        )

        LegalSection.objects.get_or_create(
            page=privacy_page,
            title="Sécurité des données",
            defaults={
                "content": (
                    "Les données sont hébergées sur une infrastructure sécurisée "
                    "et ne sont accessibles qu’aux personnels autorisés."
                ),
                "order": 2
            }
        )

        # ======================================================
        # CONDITIONS D’UTILISATION
        # ======================================================

        terms_page, _ = LegalPage.objects.get_or_create(
            page_type="terms",
            defaults={
                "title": "Conditions d’utilisation",
                "introduction": (
                    "L’utilisation du site implique l’acceptation pleine et entière "
                    "des présentes conditions."
                ),
                "version": "1.0",
                "status": "published"
            }
        )

        LegalSection.objects.get_or_create(
            page=terms_page,
            title="Accès au service",
            defaults={
                "content": (
                    "Le site est accessible 24h/24, sauf interruption pour maintenance "
                    "technique ou cas de force majeure."
                ),
                "order": 1
            }
        )

        # ======================================================
        # À PROPOS (DENSE ET CRÉDIBLE)
        # ======================================================

        about_sections = [
            (
                "Notre mission",
                "Former des professionnels de santé compétents, éthiques et engagés, "
                "capables de répondre aux défis sanitaires nationaux et internationaux."
            ),
            (
                "Notre vision",
                "Positionner l’ESFé comme une référence régionale en formation "
                "paramédicale, reconnue pour son excellence académique et son innovation pédagogique."
            ),
            (
                "Nos valeurs",
                "Excellence académique, intégrité professionnelle, rigueur scientifique, "
                "responsabilité sociale et innovation continue."
            ),
        ]

        for index, (title, content) in enumerate(about_sections):
            AboutSection.objects.get_or_create(
                title=title,
                defaults={
                    "content": content,
                    "order": index,
                    "is_active": True
                }
            )

        self.stdout.write(self.style.SUCCESS("ESFé institutionnel seeded with enriched data."))