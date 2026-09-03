from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from unittest.mock import patch
from django.urls import reverse

from branches.models import Branch
from notifier.models import NotificationMessage
from formations.models import Cycle, Diploma, Filiere, Programme
from inscriptions.models import Inscription
from admissions.models import Candidature
from accounts.models import BranchCashMovement
from payments.models import PaymentAgent
from shop.models import ShopOrder, ShopOrderEmailConfirmation, ShopPayment, ShopProduct, ShopStockMovement
from shop.services.shop_service import create_counter_order, create_shop_payment, validate_shop_payment, confirm_student_remote_order, request_student_remote_order_confirmation
from django.core.exceptions import ValidationError
from students.models import Student


User = get_user_model()


class ShopWorkflowTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name="Annexe Shop", code="ASH", slug="annexe-shop")
        self.manager = User.objects.create_user(
            username="manager_shop",
            email="manager_shop@example.com",
            password="pass1234",
            is_staff=True,
        )
        group, _ = Group.objects.get_or_create(name="gestionnaire")
        self.manager.groups.add(group)
        manager_profile = self.manager.profile
        manager_profile.branch = self.branch
        manager_profile.position = "annex_manager"
        manager_profile.save(update_fields=["branch", "position", "updated_at"])

        cycle = Cycle.objects.create(name="Licence", theme="accent", min_duration_years=1, max_duration_years=5)
        diploma = Diploma.objects.create(name="Diplome Shop", level="superieur")
        filiere = Filiere.objects.create(name="Filiere Shop")
        self.programme = Programme.objects.create(
            title="Programme Shop",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="Programme Shop",
            description="Programme Shop",
        )
        self.student_user = User.objects.create_user(
            username="student_shop",
            email="student_shop@example.com",
            password="pass1234",
        )
        candidature = Candidature.objects.create(
            first_name="Shop",
            last_name="Student",
            birth_date="2000-01-01",
            birth_place="Bamako",
            gender="male",
            email="student_shop@example.com",
            phone="70000000",
            programme=self.programme,
            branch=self.branch,
            academic_year="2026-2027",
            entry_year=1,
            status="accepted",
        )
        inscription = Inscription.objects.create(candidature=candidature, amount_due=100000, status=Inscription.STATUS_PARTIAL)
        self.student = Student.objects.create(user=self.student_user, inscription=inscription, matricule="SHOP-001")
        self.product = ShopProduct.objects.create(
            branch=self.branch,
            name="Blouse pratique",
            category=ShopProduct.CATEGORY_BLOUSE,
            description="Blouse officielle.",
            unit_price=15000,
            is_required=True,
            is_active=True,
        )

    def test_validated_student_shop_payment_creates_cash_and_notification(self):
        ShopStockMovement.objects.create(
            branch=self.branch,
            product=self.product,
            movement_type=ShopStockMovement.TYPE_IN,
            quantity=3,
            reference="STK-ASH-2026-000001",
            created_by=self.manager,
        )
        order = ShopOrder.objects.create(
            branch=self.branch,
            inscription=self.student.inscription,
            student=self.student_user,
            buyer_type=ShopOrder.BUYER_STUDENT,
            customer_name="Shop Student",
            customer_email="student_shop@example.com",
            reference="CMD-ASH-2026-000001",
            status=ShopOrder.STATUS_PENDING_PAYMENT,
            created_by=self.manager,
            total_amount=15000,
        )
        order.items.create(product=self.product, quantity=1, unit_price=15000, is_required=True)
        payment = create_shop_payment(order, 15000, ShopPayment.METHOD_CASH, self.student_user, auto_validate=False)

        validate_shop_payment(payment, user=self.manager)

        payment.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(payment.status, ShopPayment.STATUS_VALIDATED)
        self.assertEqual(order.status, ShopOrder.STATUS_PAID)
        self.assertEqual(
            ShopStockMovement.objects.filter(order=order, movement_type=ShopStockMovement.TYPE_OUT).count(),
            1,
        )
        self.assertTrue(
            BranchCashMovement.objects.filter(
                branch=self.branch,
                source=BranchCashMovement.SOURCE_SHOP,
                movement_type=BranchCashMovement.TYPE_IN,
                source_reference=payment.reference,
            ).exists()
        )
        self.assertEqual(self.product.current_stock, 2)
        self.assertTrue(
            NotificationMessage.objects.filter(
                recipient=self.student_user,
                event_type="shop_purchase_validated",
            ).exists()
        )

    def test_staff_manager_cannot_download_other_branch_shop_receipt(self):
        order = ShopOrder.objects.create(
            branch=self.branch,
            student=self.student_user,
            buyer_type=ShopOrder.BUYER_STUDENT,
            customer_name="Shop Student",
            reference="CMD-SEC-001",
            status=ShopOrder.STATUS_PENDING_PAYMENT,
            created_by=self.manager,
            total_amount=15000,
        )
        payment = ShopPayment.objects.create(
            order=order,
            amount=15000,
            method=ShopPayment.METHOD_CASH,
            status=ShopPayment.STATUS_VALIDATED,
            reference="RVS-SEC-001",
        )
        other_branch = Branch.objects.create(name="Autre Shop", code="AUS", slug="autre-shop")
        other_manager = User.objects.create_user(
            username="other_manager_shop",
            password="pass1234",
            is_staff=True,
        )
        other_manager.groups.add(Group.objects.get(name="gestionnaire"))
        other_manager.profile.branch = other_branch
        other_manager.profile.save(update_fields=["branch", "updated_at"])
        self.client.force_login(other_manager)

        response = self.client.get(reverse("shop:payment_receipt", args=[payment.pk]))
        self.assertEqual(response.status_code, 403)

    def test_manager_can_create_counter_order_for_walk_in_customer(self):
        ShopStockMovement.objects.create(
            branch=self.branch,
            product=self.product,
            movement_type=ShopStockMovement.TYPE_IN,
            quantity=5,
            reference="STK-ASH-2026-000002",
            created_by=self.manager,
        )
        order, payment = create_counter_order(
            branch=self.branch,
            product=self.product,
            quantity=2,
            payment_method=ShopPayment.METHOD_CASH,
            created_by=self.manager,
            customer_name="Client Comptoir",
            customer_email="client@example.com",
            customer_phone="77000000",
            immediate_settlement=True,
        )

        self.assertEqual(order.branch, self.branch)
        self.assertEqual(order.buyer_type, ShopOrder.BUYER_WALK_IN)
        self.assertEqual(order.customer_name, "Client Comptoir")
        self.assertEqual(order.total_amount, 30000)
        self.assertEqual(payment.status, ShopPayment.STATUS_VALIDATED)

        movement = BranchCashMovement.objects.filter(
            branch=self.branch,
            source=BranchCashMovement.SOURCE_SHOP,
            movement_type=BranchCashMovement.TYPE_IN,
            source_reference=payment.reference,
        ).first()
        self.assertIsNotNone(movement)
        self.assertEqual(movement.amount, payment.amount)
        outs = ShopStockMovement.objects.filter(order=order, movement_type=ShopStockMovement.TYPE_OUT)
        self.assertEqual(outs.count(), 1)
        self.assertEqual(self.product.current_stock, 3)

    def test_counter_sale_supports_multiple_lines_with_one_cash_entry(self):
        second_product = ShopProduct.objects.create(
            branch=self.branch,
            name="Badge étudiant",
            category=ShopProduct.CATEGORY_BADGE,
            unit_price=2000,
            is_active=True,
        )
        for product, quantity, reference in (
            (self.product, 5, "STK-MULTI-001"),
            (second_product, 8, "STK-MULTI-002"),
        ):
            ShopStockMovement.objects.create(
                branch=self.branch,
                product=product,
                movement_type=ShopStockMovement.TYPE_IN,
                quantity=quantity,
                reference=reference,
                created_by=self.manager,
            )

        order, payment = create_counter_order(
            branch=self.branch,
            lines=[
                {"product": self.product, "quantity": 2},
                {"product": second_product, "quantity": 3},
            ],
            payment_method=ShopPayment.METHOD_CASH,
            created_by=self.manager,
            customer_name="Client comptoir",
            immediate_settlement=True,
        )

        self.assertEqual(order.items.count(), 2)
        self.assertEqual(order.total_amount, 36000)
        self.assertEqual(payment.status, ShopPayment.STATUS_VALIDATED)
        self.assertEqual(
            BranchCashMovement.objects.filter(
                branch=self.branch,
                source=BranchCashMovement.SOURCE_SHOP,
                source_reference=payment.reference,
            ).count(),
            1,
        )
        self.assertEqual(self.product.current_stock, 3)
        self.assertEqual(second_product.current_stock, 5)

    def test_manager_stock_adjustment_is_traced_and_cannot_make_stock_negative(self):
        ShopStockMovement.objects.create(
            branch=self.branch,
            product=self.product,
            movement_type=ShopStockMovement.TYPE_IN,
            quantity=3,
            reference="STK-ADJUST-001",
            created_by=self.manager,
        )
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("shop:manager_stock_adjust"),
            {"product": self.product.pk, "quantity": -1, "notes": "Comptage physique du jour"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.product.current_stock, 2)
        adjustment = ShopStockMovement.objects.filter(
            product=self.product,
            movement_type=ShopStockMovement.TYPE_ADJUSTMENT,
        ).get()
        self.assertEqual(adjustment.quantity, -1)
        self.assertEqual(adjustment.notes, "Comptage physique du jour")

    def test_manager_shop_panel_renders_for_branch(self):
        PaymentAgent.objects.create(user=self.manager, branch=self.branch, is_active=True)
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse("accounts_portal:portal_annex_manager"),
            {"section": "boutique"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Poste de vente comptoir")
        self.assertContains(response, "Blouse pratique")
        self.assertContains(response, "À encaisser")
        self.assertContains(response, "Stock &amp; articles")

    def test_manager_shop_stock_and_journal_filters_keep_the_boutique_subview(self):
        self.client.force_login(self.manager)
        dashboard_url = reverse("accounts_portal:portal_annex_manager")

        stock_response = self.client.get(
            dashboard_url,
            {"section": "boutique", "view": "stock", "shop_stock_state": "low"},
        )
        self.assertEqual(stock_response.status_code, 200)
        self.assertContains(stock_response, 'name="shop_stock_q"')
        self.assertContains(stock_response, 'name="shop_stock_category"')
        self.assertContains(stock_response, 'name="shop_stock_state"')
        self.assertContains(stock_response, 'name="view" value="stock"')

        journal_response = self.client.get(
            dashboard_url,
            {"section": "boutique", "view": "journal", "shop_q": "Blouse"},
        )
        self.assertEqual(journal_response.status_code, 200)
        self.assertContains(journal_response, 'name="shop_q"')
        self.assertContains(journal_response, 'name="shop_date"')
        self.assertContains(journal_response, 'name="view" value="journal"')

    def test_manager_archives_and_restores_catalogue_item_without_deleting_it(self):
        ShopStockMovement.objects.create(
            branch=self.branch,
            product=self.product,
            movement_type=ShopStockMovement.TYPE_IN,
            quantity=2,
            reference="STK-ARCHIVE-001",
            created_by=self.manager,
        )
        self.client.force_login(self.manager)
        url = reverse("shop:manager_product_delete", args=[self.product.pk])

        self.client.post(url)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)
        self.assertTrue(ShopProduct.objects.filter(pk=self.product.pk).exists())
        self.assertEqual(self.product.current_stock, 2)

        self.client.post(url)
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)

    def test_public_catalog_renders_branch_products(self):
        response = self.client.get(f"/shop/{self.branch.slug}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.branch.name)
        self.assertContains(response, "Blouse pratique")

    @patch("shop.services.shop_service.NotificationBus.send_email")
    def test_student_email_otp_confirms_order_without_creating_payment_or_stock_output(self, send_email):
        ShopStockMovement.objects.create(branch=self.branch, product=self.product, movement_type=ShopStockMovement.TYPE_IN, quantity=4, reference="STK-OTP-001", created_by=self.manager)
        with patch("shop.services.shop_service._shop_email_otp", return_value="123456"):
            confirmation, _product = request_student_remote_order_confirmation(student=self.student_user, product_id=self.product.pk, quantity=2)
        self.assertEqual(ShopOrder.objects.count(), 0)
        self.assertEqual(confirmation.status, ShopOrderEmailConfirmation.STATUS_PENDING)
        order = confirm_student_remote_order(student=self.student_user, confirmation_id=confirmation.pk, code="123456")
        self.assertEqual(order.status, ShopOrder.STATUS_PENDING_PAYMENT)
        self.assertEqual(order.total_amount, 30000)
        self.assertFalse(ShopPayment.objects.filter(order=order).exists())
        self.assertFalse(ShopStockMovement.objects.filter(order=order, movement_type=ShopStockMovement.TYPE_OUT).exists())
        confirmation.refresh_from_db()
        self.assertEqual(confirmation.status, ShopOrderEmailConfirmation.STATUS_CONFIRMED)
        self.assertEqual(confirmation.order, order)
        self.assertGreaterEqual(send_email.call_count, 2)

    def test_student_can_order_from_public_catalog(self):
        ShopStockMovement.objects.create(
            branch=self.branch,
            product=self.product,
            movement_type=ShopStockMovement.TYPE_IN,
            quantity=4,
            reference="STK-ASH-2026-000003",
            created_by=self.manager,
        )
        response = self.client.post(
            f"/shop/{self.branch.code.lower()}/article/{self.product.id}/commander/",
            {
                "buyer_type": "student",
                "student_identifier": str(self.student_user.id),
                "quantity": 1,
                "payment_method": ShopPayment.METHOD_CASH,
            },
        )

        self.assertEqual(response.status_code, 302)
        order = ShopOrder.objects.get(student=self.student_user)
        self.assertEqual(order.branch, self.branch)
        self.assertEqual(order.status, ShopOrder.STATUS_PENDING_PAYMENT)

    def test_anonymous_buyer_can_initiate_public_order(self):
        ShopStockMovement.objects.create(
            branch=self.branch,
            product=self.product,
            movement_type=ShopStockMovement.TYPE_IN,
            quantity=4,
            reference="STK-ASH-2026-000004",
            created_by=self.manager,
        )
        response = self.client.post(
            f"/shop/{self.branch.code.lower()}/article/{self.product.id}/commander/",
            {
                "buyer_type": "walk_in",
                "customer_first_name": "Acheteur",
                "customer_last_name": "Public",
                "customer_email": "public@example.com",
                "customer_phone": "70000001",
                "quantity": 2,
                "payment_method": ShopPayment.METHOD_ORANGE,
            },
        )

        self.assertEqual(response.status_code, 302)
        order = ShopOrder.objects.get(customer_email="public@example.com")
        self.assertEqual(order.branch, self.branch)
        self.assertEqual(order.buyer_type, ShopOrder.BUYER_WALK_IN)
        self.assertEqual(order.total_amount, 30000)

    def test_public_order_is_blocked_when_stock_is_insufficient(self):
        response = self.client.post(
            f"/shop/{self.branch.code.lower()}/article/{self.product.id}/commander/",
            {
                "buyer_type": "walk_in",
                "customer_first_name": "Client",
                "customer_last_name": "Test",
                "customer_email": "rupture@example.com",
                "customer_phone": "70000001",
                "quantity": 1,
                "payment_method": ShopPayment.METHOD_CASH,
            },
        )

        self.assertContains(response, "Stock insuffisant", status_code=400)

    def test_stock_is_not_decremented_twice_on_delivery(self):
        ShopStockMovement.objects.create(
            branch=self.branch,
            product=self.product,
            movement_type=ShopStockMovement.TYPE_IN,
            quantity=5,
            reference="STK-TEST-001",
            created_by=self.manager,
        )
        order = ShopOrder.objects.create(
            branch=self.branch,
            inscription=self.student.inscription,
            student=self.student_user,
            buyer_type=ShopOrder.BUYER_STUDENT,
            customer_name="Shop Student",
            customer_email="student_shop@example.com",
            reference="CMD-ASH-2026-000002",
            status=ShopOrder.STATUS_PENDING_PAYMENT,
            created_by=self.manager,
            total_amount=15000,
        )
        order.items.create(product=self.product, quantity=1, unit_price=15000, is_required=True)
        payment = create_shop_payment(order, 15000, ShopPayment.METHOD_CASH, self.student_user, auto_validate=False)

        validate_shop_payment(payment, user=self.manager)
        from shop.services.shop_service import deliver_order
        deliver_order(order, self.manager)

        self.assertEqual(
            ShopStockMovement.objects.filter(order=order, movement_type=ShopStockMovement.TYPE_OUT).count(),
            1,
        )
