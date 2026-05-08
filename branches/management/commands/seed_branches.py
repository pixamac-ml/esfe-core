"""
Seed production — Annexes ESFé Mali
Usage: python manage.py seed_branches
"""
from django.core.management.base import BaseCommand
from branches.models import Branch


BRANCHES = [
    {
        "name": "ESFé Badalabougou",
        "code": "BDL",
        "slug": "badalabougou",
        "address": "Badalabougou Est, Rue 110, Bamako",
        "city": "Bamako",
        "phone": "+223 20 22 10 00",
        "email": "badalabougou@esfe-mali.org",
        "is_active": True,
        "accepts_online_registration": True,
    },
    {
        "name": "ESFé Kalaban-Coura",
        "code": "KLB",
        "slug": "kalaban-coura",
        "address": "Kalaban-Coura ACI, Bamako",
        "city": "Bamako",
        "phone": "+223 20 28 50 00",
        "email": "kalaban@esfe-mali.org",
        "is_active": True,
        "accepts_online_registration": True,
    },
    {
        "name": "ESFé Missabougou",
        "code": "MSB",
        "slug": "missabougou",
        "address": "Missabougou, Route de Koulikoro, Bamako",
        "city": "Bamako",
        "phone": "+223 20 29 60 00",
        "email": "missabougou@esfe-mali.org",
        "is_active": True,
        "accepts_online_registration": True,
    },
]


class Command(BaseCommand):
    help = "Seed des annexes ESFé Mali (production)"

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.NOTICE("\n📍 Création des annexes ESFé Mali..."))

        created_count = 0
        updated_count = 0

        for data in BRANCHES:
            branch, created = Branch.objects.update_or_create(
                code=data["code"],
                defaults=data,
            )
            if created:
                created_count += 1
                self.stdout.write(f"   ✅ Créée : {branch.name} ({branch.code})")
            else:
                updated_count += 1
                self.stdout.write(f"   🔄 Mise à jour : {branch.name} ({branch.code})")

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✅ Annexes : {created_count} créées, {updated_count} mises à jour."
            )
        )

