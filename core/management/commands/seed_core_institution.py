from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from core.models import (
    Institution,
    InstitutionPresentation,
    InstitutionStat,
    LegalPage,
    LegalSection,
    LegalSidebarBlock,
    SiteConfiguration,
    Value,
)


class Command(BaseCommand):
    help = "Seed institutionnel ESFé Mali (idempotent, core uniquement)"

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.NOTICE("\n🏛️  Seed core institutionnel ESFé Mali..."))

        # Groupes utilises par les affectations automatiques des messages de contact.
        groups = [
            "Direction",
            "Secretaire Academique",
            "Gestionnaire",
            "Responsable Qualite",
            "Support",
        ]
        for name in groups:
            Group.objects.get_or_create(name=name)

        # Singleton Institution
        institution = Institution.objects.first()
        institution_defaults = {
            "name": "École de Santé Félix Houphouët-Boigny Mali",
            "short_name": "ESFé Mali",
            "address": "Badalabougou, Bamako",
            "city": "Bamako",
            "country": "Mali",
            "phone": "+223 20 00 00 00",
            "email": "contact@esfe-mali.org",
            "is_active": True,
            "legal_status": "Établissement privé d'enseignement supérieur paramédical.",
            "approval_number": "AGR-ESFE-MALI-2026",
            "director_title": "Direction Générale",
            "hosting_provider": "Infrastructure cloud sécurisée",
            "hosting_location": "Afrique de l'Ouest",
        }
        if institution:
            for key, value in institution_defaults.items():
                setattr(institution, key, value)
            institution.save()
            self.stdout.write("   🔄 Institution mise à jour")
        else:
            Institution.objects.create(**institution_defaults)
            self.stdout.write("   ✅ Institution créée")

        # Singleton Presentation
        presentation = InstitutionPresentation.objects.first()
        presentation_defaults = {
            "about_title": "À propos de notre institution",
            "about_text": (
                "<p>L'École de Santé Félix Houphouët-Boigny Mali forme des professionnels de "
                "santé compétents, responsables et ancrés dans les réalités du terrain.</p>"
            ),
            "vision_title": "Notre Vision",
            "vision_text": (
                "Devenir une référence sous-régionale de la formation en sciences de la santé "
                "grâce à l'excellence académique et l'innovation pédagogique."
            ),
            "mission_title": "Notre Mission",
            "mission_text": (
                "Former des talents capables de répondre efficacement aux enjeux sanitaires du Mali "
                "et de la sous-région."
            ),
            "hero_title": "École de Santé Félix Houphouët-Boigny Mali",
            "hero_subtitle": "Former les professionnels de santé de demain",
            "cta_title": "Rejoignez ESFé Mali",
            "cta_subtitle": "Lancez votre parcours académique dans un cadre d'excellence.",
            "cta_button_text": "Candidater maintenant",
            "cta_button_url": "/admissions/candidature/",
        }
        if presentation:
            for key, value in presentation_defaults.items():
                setattr(presentation, key, value)
            presentation.save()
            self.stdout.write("   🔄 Présentation institutionnelle mise à jour")
        else:
            InstitutionPresentation.objects.create(**presentation_defaults)
            self.stdout.write("   ✅ Présentation institutionnelle créée")

        # Singleton SiteConfiguration
        site_configuration = SiteConfiguration.objects.first()
        site_defaults = {
            "home_hero_title": "École de Santé Félix Houphouët-Boigny Mali",
            "home_hero_subtitle": "Former les cadres de la santé au Mali",
            "about_vision_title": "Notre Vision",
            "about_vision_text": (
                "Construire un enseignement de santé moderne, inclusif et professionnalisant."
            ),
            "about_values_title": "Nos Valeurs",
            "about_values_subtitle": "Excellence, intégrité, engagement, innovation.",
            "smart_rocket_enabled": True,
            "smart_rocket_title": "Assistant ESFé",
            "smart_rocket_message": "Accédez rapidement aux informations clés d'ESFé Mali.",
        }
        if site_configuration:
            for key, value in site_defaults.items():
                setattr(site_configuration, key, value)
            site_configuration.save()
            self.stdout.write("   🔄 Configuration du site mise à jour")
        else:
            SiteConfiguration.objects.create(**site_defaults)
            self.stdout.write("   ✅ Configuration du site créée")

        # Valeurs (max 4 actives)
        values_data = [
            ("Excellence", "Nous visons la rigueur académique et professionnelle."),
            ("Intégrité", "Nous agissons avec éthique, transparence et responsabilité."),
            ("Engagement", "Nous accompagnons chaque étudiant vers la réussite."),
            ("Innovation", "Nous intégrons des pratiques pédagogiques modernes."),
        ]
        for idx, (title, description) in enumerate(values_data, start=1):
            Value.objects.update_or_create(
                title=title,
                defaults={
                    "description": description,
                    "order": idx,
                    "is_active": True,
                    "icon": "fa-solid fa-circle-check",
                },
            )

        # Statistiques
        stats_data = [
            ("Étudiants formés", 500, "+", "", 1),
            ("Années d'expérience", 20, "+", "", 2),
            ("Taux de réussite", 95, "%", "", 3),
            ("Annexes", 3, "", "", 4),
        ]
        for label, value, suffix, prefix, order in stats_data:
            InstitutionStat.objects.update_or_create(
                label=label,
                defaults={
                    "value": value,
                    "suffix": suffix,
                    "prefix": prefix,
                    "order": order,
                    "is_active": True,
                },
            )

        legal_pages = {
            "legal": {
                "title": "Mentions légales",
                "introduction": (
                    "<p>Le site est édité par l'École de Santé Félix Houphouët-Boigny Mali (ESFé Mali).</p>"
                ),
                "sections": [
                    (
                        "Identification de l'établissement",
                        "<p>Nom officiel : École de Santé Félix Houphouët-Boigny Mali.</p>",
                    ),
                    (
                        "Propriété intellectuelle",
                        "<p>Les contenus du site sont protégés selon la réglementation en vigueur.</p>",
                    ),
                ],
                "sidebar": [
                    (
                        "Contact officiel",
                        "Adresse : Badalabougou, Bamako<br>Email : contact@esfe-mali.org",
                    )
                ],
            },
            "privacy": {
                "title": "Politique de confidentialité",
                "introduction": "<p>ESFé Mali protège les données personnelles des usagers.</p>",
                "sections": [
                    (
                        "Données collectées",
                        "<p>Les données sont collectées pour la gestion académique et administrative.</p>",
                    ),
                    (
                        "Sécurité",
                        "<p>Les accès sont limités aux personnels autorisés et tracés.</p>",
                    ),
                ],
                "sidebar": [],
            },
            "terms": {
                "title": "Conditions d'utilisation",
                "introduction": "<p>L'utilisation du site implique l'acceptation des présentes conditions.</p>",
                "sections": [
                    (
                        "Accès au service",
                        "<p>Le service est disponible hors interruptions de maintenance planifiée.</p>",
                    ),
                ],
                "sidebar": [],
            },
        }

        for page_type, payload in legal_pages.items():
            page, _ = LegalPage.objects.update_or_create(
                page_type=page_type,
                defaults={
                    "title": payload["title"],
                    "introduction": payload["introduction"],
                    "version": "1.0",
                    "status": "published",
                },
            )

            for order, (title, content) in enumerate(payload["sections"], start=1):
                LegalSection.objects.update_or_create(
                    page=page,
                    title=title,
                    defaults={
                        "content": content,
                        "order": order,
                        "is_active": True,
                    },
                )

            for order, (title, content) in enumerate(payload["sidebar"], start=1):
                LegalSidebarBlock.objects.update_or_create(
                    page=page,
                    title=title,
                    defaults={
                        "content": content,
                        "order": order,
                        "is_active": True,
                    },
                )

        self.stdout.write(self.style.SUCCESS("\n✅ Seed core institutionnel terminé (core uniquement)."))
