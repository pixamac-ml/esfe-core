from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from admissions.models import Candidature
from accounts.models import BranchCashMovement, BranchExpense, PayrollEntry, Profile
from branches.models import Branch
from formations.models import Cycle, Diploma, Fee, Filiere, Programme, ProgrammeYear
from inscriptions.models import Inscription
from payments.models import Payment, PaymentAgent
from shop.models import ShopOrder, ShopOrderItem, ShopPayment, ShopProduct, ShopStockMovement
from shop.services.shop_service import validate_shop_payment
from students.models import Student


User = get_user_model()


class Command(BaseCommand):
    help = "Prepare un jeu de donnees compact pour presenter le dashboard gestionnaire."

    def add_arguments(self, parser):
        parser.add_argument("--branch-code", default="DEMO", help="Code de l'annexe de demonstration.")
        parser.add_argument("--manager-username", default="gestionnaire_demo")

    def handle(self, *args, **options):
        branch_code = options["branch_code"].upper()
        manager_username = options["manager_username"]

        with transaction.atomic():
            branch = self._get_or_create_branch(branch_code)
            manager = self._get_or_create_manager(manager_username, branch)
            programme = self._get_or_create_programme()
            agent, _ = PaymentAgent.objects.get_or_create(
                user=manager,
                defaults={"branch": branch, "is_active": True},
            )
            if agent.branch_id != branch.id or not agent.is_active:
                agent.branch = branch
                agent.is_active = True
                agent.save(update_fields=["branch", "is_active"])

            staff = self._create_staff(branch)
            candidatures = self._create_candidatures(branch, programme, manager)
            inscriptions = self._create_inscriptions(candidatures)
            self._create_students_and_payments(inscriptions, branch, agent)
            self._create_expenses(branch, manager)
            self._create_payroll(branch, staff, manager)
            self._create_shop(branch, manager, inscriptions)

        self.stdout.write(self.style.SUCCESS(
            f"Demo gestionnaire prete: annexe={branch.name}, utilisateur={manager.username}, agent={agent.agent_code}"
        ))

    def _get_or_create_branch(self, branch_code):
        branch, _ = Branch.objects.get_or_create(
            code=branch_code,
            defaults={
                "name": "Annexe Demo Gestionnaire",
                "slug": "annexe-demo-gestionnaire",
                "city": "Bamako",
                "phone": "+223 70 00 00 00",
                "email": "demo.gestionnaire@esfe.local",
            },
        )
        return branch

    def _get_or_create_manager(self, username, branch):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "first_name": "Awa",
                "last_name": "Gestionnaire",
                "email": "gestionnaire.demo@esfe.local",
                "is_staff": True,
            },
        )
        if created:
            user.set_password("Demo@12345")
            user.save(update_fields=["password"])
        group, _ = Group.objects.get_or_create(name="gestionnaire")
        user.groups.add(group)
        Profile.objects.update_or_create(
            user=user,
            defaults={
                "role": "finance",
                "user_type": "staff",
                "position": "branch_manager",
                "branch": branch,
                "employee_code": "GEST-DEMO",
                "salary_base": 350000,
                "employment_status": "active",
            },
        )
        if branch.manager_id != user.id:
            branch.manager = user
            branch.save(update_fields=["manager"])
        return user

    def _get_or_create_programme(self):
        cycle, _ = Cycle.objects.get_or_create(
            name="Licence Demo",
            defaults={"min_duration_years": 3, "max_duration_years": 3, "is_active": True},
        )
        diploma, _ = Diploma.objects.get_or_create(name="Licence professionnelle demo", defaults={"level": "superieur"})
        filiere, _ = Filiere.objects.get_or_create(name="Sciences infirmieres demo", defaults={"is_active": True})
        programme, _ = Programme.objects.get_or_create(
            title="Licence en Sciences Infirmieres Demo",
            defaults={
                "filiere": filiere,
                "cycle": cycle,
                "diploma_awarded": diploma,
                "duration_years": 3,
                "short_description": "Parcours de demonstration pour le dashboard gestionnaire.",
                "description": "Programme utilise pour presenter la chaine candidature, inscription et paiement.",
                "is_active": True,
                "is_featured": True,
            },
        )
        year, _ = ProgrammeYear.objects.get_or_create(programme=programme, year_number=1)
        Fee.objects.get_or_create(
            programme_year=year,
            label="Frais annuels demo",
            defaults={"amount": 500000, "due_month": "Octobre"},
        )
        return programme

    def _create_staff(self, branch):
        rows = [
            ("enseignant_demo", "Moussa", "Traore", "teacher", 280000),
            ("secretaire_demo", "Fatoumata", "Diarra", "secretary", 180000),
            ("surveillant_demo", "Ibrahim", "Keita", "academic_supervisor", 220000),
        ]
        staff = []
        for username, first_name, last_name, position, salary in rows:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": f"{username}@esfe.local",
                    "is_staff": True,
                },
            )
            if created:
                user.set_password("Demo@12345")
                user.save(update_fields=["password"])
            Profile.objects.update_or_create(
                user=user,
                defaults={
                    "role": "teacher" if position == "teacher" else "finance",
                    "user_type": "staff",
                    "position": position,
                    "branch": branch,
                    "employee_code": username.upper()[:12],
                    "salary_base": salary,
                    "employment_status": "active",
                },
            )
            staff.append(user)
        return staff

    def _create_candidatures(self, branch, programme, reviewer):
        academic_year = "2025-2026"
        rows = [
            ("Mariam", "Coulibaly", "submitted"),
            ("Oumar", "Sangare", "under_review"),
            ("Aminata", "Diallo", "accepted"),
            ("Boubacar", "Konate", "accepted"),
            ("Nene", "Toure", "to_complete"),
        ]
        candidatures = []
        for index, (first_name, last_name, status) in enumerate(rows, start=1):
            candidature, _ = Candidature.objects.update_or_create(
                email=f"demo.candidat{index}@esfe.local",
                programme=programme,
                academic_year=academic_year,
                defaults={
                    "branch": branch,
                    "entry_year": 1,
                    "first_name": first_name,
                    "last_name": last_name,
                    "birth_date": date(2001, min(index, 12), 10),
                    "birth_place": "Bamako",
                    "gender": "female" if index in {1, 3, 5} else "male",
                    "phone": f"+223 76 00 00 0{index}",
                    "address": "Bamako",
                    "city": "Bamako",
                    "country": "Mali",
                    "status": status,
                    "reviewed_by": reviewer if status != "submitted" else None,
                    "reviewed_at": timezone.now() if status != "submitted" else None,
                    "is_deleted": False,
                },
            )
            candidatures.append(candidature)
        return candidatures

    def _create_inscriptions(self, candidatures):
        inscriptions = []
        for candidature in candidatures:
            if candidature.status not in {"accepted", "accepted_with_reserve"}:
                continue
            amount = candidature.programme.get_inscription_amount_for_year(candidature.entry_year) or 500000
            inscription, _ = Inscription.objects.get_or_create(
                candidature=candidature,
                defaults={"amount_due": amount, "status": Inscription.STATUS_AWAITING_PAYMENT},
            )
            inscriptions.append(inscription)
        return inscriptions

    def _create_students_and_payments(self, inscriptions, branch, agent):
        amounts = [300000, 500000]
        for index, inscription in enumerate(inscriptions):
            amount = amounts[index % len(amounts)]
            payment, _ = Payment.objects.get_or_create(
                reference=f"PAY-DEMO-{inscription.pk}",
                defaults={
                    "inscription": inscription,
                    "agent": agent,
                    "amount": amount,
                    "method": Payment.METHOD_CASH if index == 0 else Payment.METHOD_ORANGE,
                    "status": Payment.STATUS_PENDING,
                    "paid_at": timezone.now(),
                },
            )
            if payment.status != Payment.STATUS_VALIDATED:
                payment.status = Payment.STATUS_VALIDATED
                payment.save(update_fields=["status"])
            inscription.refresh_from_db()
            student_user, created = User.objects.get_or_create(
                username=f"student_demo_{inscription.pk}",
                defaults={
                    "first_name": inscription.candidature.first_name,
                    "last_name": inscription.candidature.last_name,
                    "email": inscription.candidature.email,
                },
            )
            if created:
                student_user.set_password("Demo@12345")
                student_user.save(update_fields=["password"])
            if not Student.objects.filter(inscription=inscription).exists():
                Student.objects.create(
                    user=student_user,
                    inscription=inscription,
                    matricule=f"ESFE-DEMO-{inscription.pk:04d}",
                    is_active=True,
                )
        if inscriptions:
            Payment.objects.get_or_create(
                reference="PAY-DEMO-ATTENTE",
                defaults={
                    "inscription": inscriptions[0],
                    "agent": agent,
                    "amount": 50000,
                    "method": Payment.METHOD_BANK,
                    "status": Payment.STATUS_PENDING,
                    "paid_at": timezone.now(),
                },
            )

    def _create_expenses(self, branch, manager):
        rows = [
            ("Achat consommables laboratoire", BranchExpense.CATEGORY_SUPPLIES, 85000, BranchExpense.STATUS_SUBMITTED),
            ("Maintenance groupe electrogene", BranchExpense.CATEGORY_MAINTENANCE, 125000, BranchExpense.STATUS_APPROVED),
            ("Facture internet", BranchExpense.CATEGORY_COMMUNICATION, 45000, BranchExpense.STATUS_PAID),
        ]
        for title, category, amount, status in rows:
            expense, _ = BranchExpense.objects.get_or_create(
                branch=branch,
                title=title,
                defaults={
                    "category": category,
                    "amount": amount,
                    "expense_date": timezone.localdate(),
                    "supplier": "Fournisseur demo",
                    "status": status,
                    "created_by": manager,
                },
            )
            if expense.status == BranchExpense.STATUS_PAID:
                BranchCashMovement.objects.get_or_create(
                    branch=branch,
                    source=BranchCashMovement.SOURCE_EXPENSE,
                    source_reference=f"EXP-DEMO-{expense.pk}",
                    defaults={
                        "movement_type": BranchCashMovement.TYPE_OUT,
                        "amount": expense.amount,
                        "label": expense.title,
                        "movement_date": expense.expense_date,
                        "expense": expense,
                        "created_by": manager,
                    },
                )

    def _create_payroll(self, branch, staff, manager):
        period_month = timezone.localdate().replace(day=1)
        for index, user in enumerate(staff):
            profile = user.profile
            entry, _ = PayrollEntry.objects.get_or_create(
                branch=branch,
                employee=user,
                period_month=period_month,
                defaults={
                    "base_salary": profile.salary_base,
                    "allowances": 0,
                    "deductions": 0,
                    "advances": 0,
                    "paid_amount": profile.salary_base if index == 0 else 0,
                    "status": PayrollEntry.STATUS_READY,
                    "created_by": manager,
                    "updated_by": manager,
                },
            )
            if entry.paid_amount:
                BranchCashMovement.objects.get_or_create(
                    branch=branch,
                    source=BranchCashMovement.SOURCE_PAYROLL,
                    source_reference=f"PAYROLL-DEMO-{entry.pk}",
                    defaults={
                        "movement_type": BranchCashMovement.TYPE_OUT,
                        "amount": entry.paid_amount,
                        "label": f"Salaire - {user.get_full_name() or user.username}",
                        "movement_date": timezone.localdate(),
                        "created_by": manager,
                    },
                )

    def _create_shop(self, branch, manager, inscriptions):
        products = [
            ("Blouse ESFE", ShopProduct.CATEGORY_BLOUSE, 15000, True, 3, 20),
            ("Badge etudiant", ShopProduct.CATEGORY_BADGE, 3000, True, 5, 30),
            ("Kit travaux pratiques", ShopProduct.CATEGORY_KIT, 25000, False, 4, 8),
        ]
        created_products = []
        for name, category, price, required, threshold, quantity in products:
            product, _ = ShopProduct.objects.get_or_create(
                branch=branch,
                name=name,
                defaults={
                    "category": category,
                    "unit_price": price,
                    "description": "Article demo pour presentation gestionnaire.",
                    "is_required": required,
                    "is_active": True,
                    "low_stock_threshold": threshold,
                },
            )
            ShopStockMovement.objects.get_or_create(
                branch=branch,
                product=product,
                reference=f"STK-DEMO-{product.pk}",
                defaults={
                    "movement_type": ShopStockMovement.TYPE_IN,
                    "quantity": quantity,
                    "created_by": manager,
                },
            )
            created_products.append(product)

        if not inscriptions:
            return
        student = getattr(inscriptions[0], "student", None)
        if not student:
            return
        order, _ = ShopOrder.objects.get_or_create(
            branch=branch,
            inscription=inscriptions[0],
            student=student.user,
            reference=f"CMD-DEMO-{inscriptions[0].pk}",
            defaults={"status": ShopOrder.STATUS_PENDING_PAYMENT, "created_by": manager},
        )
        for product in created_products[:2]:
            ShopOrderItem.objects.get_or_create(
                order=order,
                product=product,
                defaults={"quantity": 1, "unit_price": product.unit_price, "is_required": product.is_required},
            )
        order.refresh_total()
        shop_payment, _ = ShopPayment.objects.get_or_create(
            order=order,
            reference=f"RVS-DEMO-{order.pk}",
            defaults={
                "amount": order.total_amount,
                "method": ShopPayment.METHOD_CASH,
                "status": ShopPayment.STATUS_PENDING,
                "created_by": manager,
            },
        )
        validate_shop_payment(shop_payment, user=manager)
