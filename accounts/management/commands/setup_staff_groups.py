"""
Management command to set up staff groups and permissions.

Usage:
    python manage.py setup_staff_groups
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType


class Command(BaseCommand):
    help = "Set up staff groups and permissions for dashboards"

    def handle(self, *args, **options):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("🚀 Configuration des groupes et permissions")
        self.stdout.write("=" * 60 + "\n")

        # =====================================================
        # 1. CRÉER LES GROUPES
        # =====================================================
        self.stdout.write(self.style.NOTICE("📦 Création des groupes..."))

        groups = {
            "admissions_managers": "Responsable des dossiers - Validation des candidatures",
            "finance_agents": "Agent de paiement - Gestion des encaissements",
            "executive_director": "Directeur Général - Vue globale",
        }

        created_groups = {}
        for group_name, description in groups.items():
            group, created = Group.objects.get_or_create(name=group_name)
            if created:
                self.stdout.write(f"   ✅ Groupe créé: {group_name}")
            else:
                self.stdout.write(f"   🔄 Groupe existant: {group_name}")
            created_groups[group_name] = group

        # =====================================================
        # 2. DÉFINIR LES PERMISSIONS PAR GROUPE
        # =====================================================

        # --- RESPONSABLE DES DOSSIERS ---
        admissions_group = created_groups["admissions_managers"]
        admissions_perms = self._get_admissions_permissions()
        admissions_group.permissions.set(admissions_perms)
        self.stdout.write(f"   ✅ Permissions assignées à {admissions_group.name}")

        # --- AGENTS DE PAIEMENT ---
        finance_group = created_groups["finance_agents"]
        finance_perms = self._get_finance_permissions()
        finance_group.permissions.set(finance_perms)
        self.stdout.write(f"   ✅ Permissions assignées à {finance_group.name}")

        # --- DIRECTEUR GÉNÉRAL ---
        executive_group = created_groups["executive_director"]
        executive_perms = self._get_executive_permissions()
        executive_group.permissions.set(executive_perms)
        self.stdout.write(f"   ✅ Permissions assignées à {executive_group.name}")

        # =====================================================
        # 3. RÉCAPITULATIF
        # =====================================================
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("✅ Configuration terminée !"))
        self.stdout.write("=" * 60)
        self.stdout.write("""
📋 Résumé des groupes créés:

1. admissions_managers (Responsable des dossiers)
   - Peut voir, modifier les candidatures
   - Peut valider les documents
   - Peut accepter/refuser les candidats

2. finance_agents (Agent de paiement)
   - Peut voir les inscriptions
   - Peut créer et valider les paiements
   - Peut gérer les sessions de caisse

3. executive_director (Directeur Général)
   - Accès lecture seule à tout
   - Peut voir les statistiques globales

⚠️  Pour assigner un utilisateur à un groupe:
    from django.contrib.auth.models import User, Group
    user = User.objects.get(username='john')
    group = Group.objects.get(name='admissions_managers')
    user.groups.add(group)
""")

    def _get_admissions_permissions(self):
        """Retourne les permissions pour le groupe Responsable des dossiers"""
        from admissions.models import Candidature, CandidatureDocument
        from inscriptions.models import Inscription

        perms = []

        # Candidatures - Full access
        ct_candidature = ContentType.objects.get_for_model(Candidature)
        perms += list(Permission.objects.filter(
            content_type=ct_candidature,
            codename__in=[
                "view_candidature",
                "change_candidature",
            ]
        ))

        # Documents - Full access
        ct_document = ContentType.objects.get_for_model(CandidatureDocument)
        perms += list(Permission.objects.filter(
            content_type=ct_document,
            codename__in=[
                "view_candidaturedocument",
                "change_candidaturedocument",
            ]
        ))

        # Inscriptions - View only
        ct_inscription = ContentType.objects.get_for_model(Inscription)
        perms += list(Permission.objects.filter(
            content_type=ct_inscription,
            codename__in=[
                "view_inscription",
            ]
        ))

        return perms

    def _get_finance_permissions(self):
        """Retourne les permissions pour le groupe Agent de paiement"""
        from payments.models import Payment, PaymentAgent, CashPaymentSession
        from inscriptions.models import Inscription
        from students.models import Student

        perms = []

        # Payments - Full access
        ct_payment = ContentType.objects.get_for_model(Payment)
        perms += list(Permission.objects.filter(
            content_type=ct_payment,
            codename__in=[
                "view_payment",
                "add_payment",
                "change_payment",
            ]
        ))

        # Payment Agents - Full access
        ct_agent = ContentType.objects.get_for_model(PaymentAgent)
        perms += list(Permission.objects.filter(
            content_type=ct_agent,
            codename__in=[
                "view_paymentagent",
                "add_paymentagent",
                "change_paymentagent",
            ]
        ))

        # Cash Sessions - Full access
        ct_session = ContentType.objects.get_for_model(CashPaymentSession)
        perms += list(Permission.objects.filter(
            content_type=ct_session,
            codename__in=[
                "view_cashpaymentsession",
                "add_cashpaymentsession",
                "change_cashpaymentsession",
            ]
        ))

        # Inscriptions - View only
        ct_inscription = ContentType.objects.get_for_model(Inscription)
        perms += list(Permission.objects.filter(
            content_type=ct_inscription,
            codename__in=[
                "view_inscription",
            ]
        ))

        # Students - View only
        ct_student = ContentType.objects.get_for_model(Student)
        perms += list(Permission.objects.filter(
            content_type=ct_student,
            codename__in=[
                "view_student",
            ]
        ))

        return perms

    def _get_executive_permissions(self):
        """Retourne les permissions pour le groupe Directeur Général (lecture seule)"""
        from admissions.models import Candidature, CandidatureDocument
        from inscriptions.models import Inscription
        from payments.models import Payment, PaymentAgent, CashPaymentSession
        from students.models import Student
        from formations.models import Programme, Cycle, Filiere

        perms = []

        # All view-only permissions
        models = [
            Candidature,
            CandidatureDocument,
            Inscription,
            Payment,
            PaymentAgent,
            CashPaymentSession,
            Student,
            Programme,
            Cycle,
            Filiere,
        ]

        for model in models:
            ct = ContentType.objects.get_for_model(model)
            view_perm = Permission.objects.filter(
                content_type=ct,
                codename__startswith="view_"
            )
            perms += list(view_perm)

        return perms