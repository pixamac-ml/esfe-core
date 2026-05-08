"""
Seed production — Groupes métiers + Superutilisateur ESFé Mali
Usage: python manage.py seed_groups_superuser
"""
import os
import secrets
import string

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

User = get_user_model()


GROUPS = [
    "Superadmin",
    "Direction",
    "Admissions",
    "Secretaire Academique",
    "Finance",
    "Gestionnaire",
    "Enseignant",
    "Etudiant",
    "Surveillant Academique",
    "Informaticien",
    "Agent Paiement",
    "Responsable Qualite",
    "Support",
]


def generate_password(length=16):
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


class Command(BaseCommand):
    help = "Seed des groupes métiers et du superutilisateur ESFé Mali (production)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default=os.environ.get("ESFE_ADMIN_USERNAME", "superadmin"),
            help="Nom d'utilisateur du superadmin (défaut: superadmin)",
        )
        parser.add_argument(
            "--email",
            default=os.environ.get("ESFE_ADMIN_EMAIL", "admin@esfe-mali.org"),
            help="Email du superadmin",
        )
        parser.add_argument(
            "--password",
            default=None,
            help="Mot de passe du superadmin (auto-généré si absent)",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("\n👥 Création des groupes métiers ESFé Mali..."))

        # ─── Groupes ───────────────────────────────────────────────────────────
        for name in GROUPS:
            group, created = Group.objects.get_or_create(name=name)
            status = "✅ Créé" if created else "🔄 Existant"
            self.stdout.write(f"   {status} : {name}")

        self.stdout.write(self.style.SUCCESS(f"   → {len(GROUPS)} groupes configurés.\n"))

        # ─── Superutilisateur ──────────────────────────────────────────────────
        username = options["username"]
        email = options["email"]
        password = options["password"] or generate_password()

        if User.objects.filter(username=username).exists():
            user = User.objects.get(username=username)
            self.stdout.write(
                self.style.WARNING(f"⚠️  Superadmin '{username}' déjà existant — mot de passe NON modifié.")
            )
        else:
            user = User.objects.create_superuser(
                username=username,
                email=email,
                password=password,
            )
            self.stdout.write(self.style.SUCCESS(f"✅ Superadmin créé : {username} / {email}"))

            # Sauvegarder les identifiants dans un fichier local (NON versionné)
            creds_path = "credentials_prod.txt"
            with open(creds_path, "w") as f:
                f.write("=== ESFé Mali — Identifiants Superadmin ===\n")
                f.write(f"Username  : {username}\n")
                f.write(f"Email     : {email}\n")
                f.write(f"Password  : {password}\n")
                f.write("⚠️  Fichier à supprimer après première connexion.\n")

            self.stdout.write(
                self.style.WARNING(
                    f"🔐 Identifiants sauvegardés dans '{creds_path}' — À supprimer après connexion !"
                )
            )

        # Ajouter au groupe Superadmin
        superadmin_group = Group.objects.get(name="Superadmin")
        user.groups.add(superadmin_group)

        self.stdout.write(self.style.SUCCESS("\n✅ Groupes et superadmin prêts pour la production."))

