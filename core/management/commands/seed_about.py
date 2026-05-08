from django.core.management.base import BaseCommand

from core.models import InstitutionPresentation, Value


class Command(BaseCommand):
    help = "Seed des contenus About basés sur les modèles core actuels"

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.NOTICE("\n📄 Mise à jour des contenus About..."))

        presentation = InstitutionPresentation.objects.first()
        defaults = {
            "about_title": "À propos de l'École de Santé Félix Houphouët-Boigny Mali",
            "about_text": (
                "<p>L'École de Santé Félix Houphouët-Boigny Mali (ESFé Mali) est un établissement "
                "d'enseignement supérieur spécialisé dans les sciences de la santé.</p>"
                "<p>Nos programmes sont structurés autour d'une pédagogie professionnalisante, "
                "centrée sur les compétences cliniques, l'éthique et l'employabilité.</p>"
            ),
            "vision_title": "Vision & Engagement Académique",
            "vision_text": (
                "Être une référence de formation en sciences de la santé au Mali et dans la sous-région, "
                "avec une approche orientée impact et qualité."
            ),
            "mission_title": "Mission",
            "mission_text": (
                "Former des professionnels de santé compétents, responsables et capables de répondre "
                "aux enjeux sanitaires contemporains."
            ),
            "hero_title": "ESFé Mali",
            "hero_subtitle": "Excellence académique et engagement pour la santé",
            "cta_title": "Rejoignez une institution d'excellence",
            "cta_subtitle": "Préparez votre avenir dans les métiers de la santé.",
            "cta_button_text": "Découvrir les formations",
            "cta_button_url": "/formations/",
        }

        if presentation:
            for key, value in defaults.items():
                setattr(presentation, key, value)
            presentation.save()
            self.stdout.write("   🔄 InstitutionPresentation mise à jour")
        else:
            InstitutionPresentation.objects.create(**defaults)
            self.stdout.write("   ✅ InstitutionPresentation créée")

        values_data = [
            ("Excellence", "Rigueur académique et qualité de la formation."),
            ("Innovation", "Amélioration continue des pratiques pédagogiques."),
            ("Engagement", "Accompagnement personnalisé vers la réussite."),
            ("Intégrité", "Éthique, transparence et responsabilité."),
        ]
        for order, (title, description) in enumerate(values_data, start=1):
            Value.objects.update_or_create(
                title=title,
                defaults={
                    "description": description,
                    "order": order,
                    "is_active": True,
                    "icon": "fa-solid fa-circle-check",
                },
            )

        self.stdout.write(self.style.SUCCESS("\n✅ Seed About terminé (modèles core actuels)."))
