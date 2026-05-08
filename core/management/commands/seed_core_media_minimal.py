import base64

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from core.models import Infrastructure, Partner, Staff, Testimonial
from formations.models import Programme

# Small 1x1 PNG placeholder used to satisfy required ImageField values.
PNG_1X1_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/w8AAusB9Y9L3nQAAAAASUVORK5CYII="
)


class Command(BaseCommand):
    help = "Seed core media minimal (staff, infrastructures, partners, testimonials)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-placeholders",
            action="store_true",
            help="Regenerer les images placeholders meme si une image existe deja.",
        )

    def _placeholder(self, filename):
        return ContentFile(base64.b64decode(PNG_1X1_BASE64), name=filename)

    def _ensure_image(self, instance, field_name, folder, reset=False):
        field = getattr(instance, field_name)
        if field and not reset:
            return False

        filename = f"{folder}/{instance.pk}.png"
        field.save(filename, self._placeholder(filename), save=False)
        return True

    def handle(self, *args, **options):
        reset = options.get("reset_placeholders", False)
        self.stdout.write(self.style.NOTICE("\n🖼️  Seed core media minimal..."))

        infrastructures_data = [
            {
                "name": "Laboratoire de biologie",
                "category": "laboratory",
                "description": "Plateau technique pour les travaux pratiques de biologie.",
                "features": ["Microscopes", "Lames", "Analyse de base"],
                "order": 1,
            },
            {
                "name": "Salle de simulation clinique",
                "category": "classroom",
                "description": "Salle dediee aux mises en situation cliniques.",
                "features": ["Mannequins", "Materiel de soins", "Projection"],
                "order": 2,
            },
            {
                "name": "Bibliotheque academique",
                "category": "library",
                "description": "Espace d'etude avec ressources pedagogiques de sante.",
                "features": ["Ouvrages", "Postes de lecture", "Acces numerique"],
                "order": 3,
            },
        ]

        staff_data = [
            {
                "full_name": "Dr Aissata Traore",
                "position": "Directrice des etudes",
                "category": "direction",
                "bio": "Coordination academique et qualite pedagogique.",
                "email": "direction.etudes@esfe-mali.org",
                "order": 1,
                "is_featured": True,
            },
            {
                "full_name": "Pr Mamadou Keita",
                "position": "Responsable pedagogique - Sciences infirmieres",
                "category": "teacher",
                "bio": "Encadrement des modules cliniques et des stages.",
                "email": "pedagogie@esfe-mali.org",
                "order": 2,
                "is_featured": True,
            },
            {
                "full_name": "Mme Fatoumata Diallo",
                "position": "Responsable administrative",
                "category": "admin",
                "bio": "Suivi administratif et accompagnement des etudiants.",
                "email": "administration@esfe-mali.org",
                "order": 3,
                "is_featured": False,
            },
        ]

        partners_data = [
            {
                "name": "Ministere de la Sante du Mali",
                "partner_type": "ministere",
                "description": "Partenariat institutionnel pour la formation en sante.",
                "website": "https://www.sante.gouv.ml",
                "order": 1,
            },
            {
                "name": "Hopital du Mali",
                "partner_type": "hospital",
                "description": "Accueil des stagiaires et collaboration clinique.",
                "website": "",
                "order": 2,
            },
            {
                "name": "Centre Hospitalier Gabriel Toure",
                "partner_type": "hospital",
                "description": "Partenaire de stage et de pratique professionnelle.",
                "website": "",
                "order": 3,
            },
        ]

        programmes = list(Programme.objects.filter(is_active=True).order_by("title")[:3])
        testimonials_data = [
            {
                "author_name": "Mariam Coulibaly",
                "author_role": "Infirmiere diplomee d'Etat",
                "promotion": "Promo 2023",
                "quote": "Ma formation a ESFe Mali m'a donne des bases solides pour exercer.",
                "programme": programmes[0] if len(programmes) > 0 else None,
                "order": 1,
                "is_featured": True,
            },
            {
                "author_name": "Abdoulaye Konate",
                "author_role": "Technicien de laboratoire",
                "promotion": "Promo 2022",
                "quote": "Les travaux pratiques etaient alignes sur les realites du terrain.",
                "programme": programmes[1] if len(programmes) > 1 else None,
                "order": 2,
                "is_featured": True,
            },
            {
                "author_name": "Aminata Sidibe",
                "author_role": "Sage-femme",
                "promotion": "Promo 2021",
                "quote": "L'encadrement pedagogique m'a permis de progresser rapidement.",
                "programme": programmes[2] if len(programmes) > 2 else None,
                "order": 3,
                "is_featured": False,
            },
        ]

        created_images = 0

        for data in infrastructures_data:
            obj, _ = Infrastructure.objects.update_or_create(
                name=data["name"],
                defaults={
                    "category": data["category"],
                    "description": data["description"],
                    "features": data["features"],
                    "order": data["order"],
                    "is_active": True,
                },
            )
            if self._ensure_image(obj, "image", "infrastructure/placeholders", reset=reset):
                created_images += 1
                obj.save()

        for data in staff_data:
            obj, _ = Staff.objects.update_or_create(
                full_name=data["full_name"],
                defaults={
                    "position": data["position"],
                    "category": data["category"],
                    "bio": data["bio"],
                    "email": data["email"],
                    "order": data["order"],
                    "is_active": True,
                    "is_featured": data["is_featured"],
                },
            )
            if self._ensure_image(obj, "photo", "staff/placeholders", reset=reset):
                created_images += 1
                obj.save()

        for data in partners_data:
            obj, _ = Partner.objects.update_or_create(
                name=data["name"],
                defaults={
                    "partner_type": data["partner_type"],
                    "description": data["description"],
                    "website": data["website"],
                    "order": data["order"],
                    "is_active": True,
                },
            )
            if self._ensure_image(obj, "logo", "partners/placeholders", reset=reset):
                created_images += 1
                obj.save()

        for data in testimonials_data:
            Testimonial.objects.update_or_create(
                author_name=data["author_name"],
                defaults={
                    "author_role": data["author_role"],
                    "promotion": data["promotion"],
                    "quote": data["quote"],
                    "programme": data["programme"],
                    "order": data["order"],
                    "is_featured": data["is_featured"],
                    "is_active": True,
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✅ Core media seed termine. Placeholders generes: {created_images}."
            )
        )

