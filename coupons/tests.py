"""Tests pour le systeme de coupons : validation, application, perimetre annexe/formation."""

from datetime import date, timedelta
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from academics.models import AcademicClass, AcademicYear
from admissions.models import Candidature
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme
from inscriptions.models import Inscription
from inscriptions.services import create_inscription_from_candidature
from payments.models import FinancialLog, Payment

from coupons.models import Coupon, CouponRedemption
from coupons.services.application import apply_coupon
from coupons.services.validation import get_valid_coupon
from notifier.models import NotificationMessage
from portal.dg.coupons_service import create_coupon
from portal.dg.forms import DgCouponForm


User = get_user_model()
USER_MANAGER = cast(Any, User._default_manager)


def _create_branch(code="TST", name="Test Annexe"):
    return Branch.objects.create(name=name, code=code, slug=f"annexe-{code.lower()}")


def _create_programme(title="LP Informatique"):
    cycle, _ = Cycle.objects.get_or_create(
        name="Licence", defaults={"min_duration_years": 3, "max_duration_years": 4},
    )
    diploma, _ = Diploma.objects.get_or_create(name="Licence Pro", defaults={"level": "superieur"})
    filiere, _ = Filiere.objects.get_or_create(name="Informatique")
    return Programme.objects.create(
        title=title,
        filiere=filiere,
        cycle=cycle,
        diploma_awarded=diploma,
        duration_years=3,
        short_description="Formation en informatique",
        description="Formation en informatique de niveau licence",
    )


def _create_academic_class(programme, branch, level="L1"):
    year, _ = AcademicYear.objects.get_or_create(
        name="2025-2026",
        defaults={"start_date": date(2025, 10, 1), "end_date": date(2026, 7, 31), "is_active": True},
    )
    return AcademicClass.objects.create(programme=programme, branch=branch, academic_year=year, level=level)


def _create_candidature(programme, branch, **kw):
    defaults = dict(
        first_name="Jean",
        last_name="Test",
        email="jean@test.com",
        phone="70000000",
        birth_date=date(2000, 1, 1),
        birth_place="Bamako",
        gender="male",
        academic_year="2025-2026",
        status="accepted",
    )
    defaults.update(kw)
    return Candidature.objects.create(programme=programme, branch=branch, **defaults)


def _create_inscription(candidature, branch, amount_due=100000):
    academic_class = _create_academic_class(candidature.programme, branch)
    return create_inscription_from_candidature(
        candidature=candidature,
        amount_due=amount_due,
        academic_class=academic_class,
        status=Inscription.STATUS_AWAITING_PAYMENT,
    )


def _create_coupon(**kw):
    defaults = dict(
        code="TESTCOUPON",
        label="Coupon de test",
        discount_type=Coupon.DISCOUNT_PERCENTAGE,
        value=20,
        valid_from=timezone.now() - timedelta(days=1),
        valid_until=timezone.now() + timedelta(days=30),
        max_redemptions=1,
    )
    defaults.update(kw)
    return Coupon.objects.create(**defaults)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CouponValidationTests(TestCase):
    def setUp(self):
        self.branch = _create_branch()
        self.programme = _create_programme()
        self.candidature = _create_candidature(self.programme, self.branch)
        self.inscription = _create_inscription(self.candidature, self.branch)
        self.actor = USER_MANAGER.create_user(username="agent", email="agent@test.com", password="pass1234")

    def test_apply_valid_percentage_coupon_reduces_amount_due(self):
        coupon = _create_coupon(discount_type=Coupon.DISCOUNT_PERCENTAGE, value=20)
        redemption = apply_coupon(code=coupon.code, inscription_id=self.inscription.id, actor=self.actor)
        self.inscription.refresh_from_db()
        self.assertEqual(redemption.amount_before, 100000)
        self.assertEqual(redemption.discount_amount, 20000)
        self.assertEqual(self.inscription.amount_due, 80000)
        self.assertEqual(CouponRedemption.objects.filter(inscription=self.inscription).count(), 1)
        audit = FinancialLog.objects.get(action=FinancialLog.ACTION_COUPON_APPLIED)
        self.assertEqual(audit.branch, self.branch)
        self.assertEqual(audit.metadata["inscription_id"], self.inscription.id)
        self.assertEqual(audit.metadata["coupon_id"], coupon.id)

    def test_apply_valid_fixed_amount_coupon(self):
        coupon = _create_coupon(discount_type=Coupon.DISCOUNT_FIXED, value=15000)
        redemption = apply_coupon(code=coupon.code, inscription_id=self.inscription.id, actor=self.actor)
        self.inscription.refresh_from_db()
        self.assertEqual(redemption.discount_amount, 15000)
        self.assertEqual(self.inscription.amount_due, 85000)

    def test_unknown_code_is_rejected(self):
        with self.assertRaises(ValidationError):
            get_valid_coupon("DOESNOTEXIST", self.inscription)

    def test_disabled_coupon_is_rejected(self):
        coupon = _create_coupon(is_active=False)
        with self.assertRaises(ValidationError):
            get_valid_coupon(coupon.code, self.inscription)

    def test_expired_coupon_is_rejected(self):
        coupon = _create_coupon(
            valid_from=timezone.now() - timedelta(days=60),
            valid_until=timezone.now() - timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            get_valid_coupon(coupon.code, self.inscription)

    def test_quota_exhausted_coupon_is_rejected(self):
        coupon = _create_coupon(max_redemptions=1)
        other_candidature = _create_candidature(
            self.programme, self.branch, email="other@test.com", phone="70000001",
        )
        other_inscription = Inscription.objects.create(
            candidature=other_candidature, amount_due=100000, amount_paid=0,
            status=Inscription.STATUS_AWAITING_PAYMENT,
        )
        apply_coupon(code=coupon.code, inscription_id=other_inscription.id, actor=self.actor)

        with self.assertRaises(ValidationError):
            get_valid_coupon(coupon.code, self.inscription)

    def test_coupon_restricted_to_another_branch_is_rejected(self):
        other_branch = _create_branch(code="OTH", name="Autre annexe")
        coupon = _create_coupon()
        coupon.branches.add(other_branch)
        with self.assertRaises(ValidationError):
            get_valid_coupon(coupon.code, self.inscription)

    def test_coupon_restricted_to_matching_branch_is_accepted(self):
        coupon = _create_coupon()
        coupon.branches.add(self.branch)
        # Ne doit pas lever d'exception.
        get_valid_coupon(coupon.code, self.inscription)

    def test_coupon_restricted_to_another_programme_is_rejected(self):
        other_programme = _create_programme(title="Autre formation")
        coupon = _create_coupon()
        coupon.programmes.add(other_programme)
        with self.assertRaises(ValidationError):
            get_valid_coupon(coupon.code, self.inscription)

    def test_reapplication_on_same_inscription_is_rejected(self):
        coupon = _create_coupon(max_redemptions=5)
        apply_coupon(code=coupon.code, inscription_id=self.inscription.id, actor=self.actor)
        with self.assertRaises(ValidationError):
            get_valid_coupon(coupon.code, self.inscription)

    def test_application_after_full_payment_is_rejected(self):
        coupon = _create_coupon()
        Payment.objects.create(
            inscription=self.inscription,
            amount=self.inscription.amount_due,
            status=Payment.STATUS_VALIDATED,
            method=Payment.METHOD_CASH,
        )
        self.inscription.update_financial_state()
        with self.assertRaises(ValidationError):
            get_valid_coupon(coupon.code, self.inscription)

    def test_discount_never_reduces_below_amount_already_paid(self):
        coupon = _create_coupon(discount_type=Coupon.DISCOUNT_FIXED, value=100000)
        Payment.objects.create(
            inscription=self.inscription,
            amount=40000,
            status=Payment.STATUS_VALIDATED,
            method=Payment.METHOD_CASH,
        )
        self.inscription.update_financial_state()
        redemption = apply_coupon(code=coupon.code, inscription_id=self.inscription.id, actor=self.actor)
        self.assertEqual(redemption.amount_after, 40000)

    def test_branch_guard_prevents_cross_branch_application(self):
        other_branch = _create_branch(code="SEC", name="Annexe securisee")
        coupon = _create_coupon(max_redemptions=5)
        with self.assertRaises(Inscription.DoesNotExist):
            apply_coupon(
                code=coupon.code,
                inscription_id=self.inscription.id,
                actor=self.actor,
                branch=other_branch,
            )


def _create_staff_user(username, branch, position):
    user = USER_MANAGER.create_user(username=username, email=f"{username}@test.com", password="pass1234")
    profile = user.profile
    profile.branch = branch
    profile.position = position
    profile.save(update_fields=["branch", "position", "updated_at"])
    return user


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CouponNotificationTests(TestCase):
    def setUp(self):
        self.branch = _create_branch()
        self.other_branch = _create_branch(code="OTH3", name="Autre annexe 3")
        self.dg = USER_MANAGER.create_user(username="dg", email="dg@test.com", password="pass1234")
        self.secretary = _create_staff_user("secretary1", self.branch, "secretary")
        self.other_secretary = _create_staff_user("secretary2", self.other_branch, "secretary")

    def test_coupon_creation_notifies_only_targeted_branch(self):
        form = DgCouponForm(data={
            "code": "PROMO2026",
            "label": "Promo test",
            "discount_type": Coupon.DISCOUNT_PERCENTAGE,
            "value": "10",
            "branches": [str(self.branch.id)],
            "valid_until": (timezone.now() + timedelta(days=10)).strftime("%Y-%m-%dT%H:%M"),
            "max_redemptions": "1",
        })
        self.assertTrue(form.is_valid(), form.errors)
        create_coupon(actor=self.dg, form=form)

        self.assertTrue(
            NotificationMessage.objects.filter(recipient=self.secretary, event_type="coupon_created").exists()
        )
        self.assertFalse(
            NotificationMessage.objects.filter(recipient=self.other_secretary, event_type="coupon_created").exists()
        )


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CouponModelTests(TestCase):
    def test_applies_to_with_no_restriction_matches_everything(self):
        branch = _create_branch()
        programme = _create_programme()
        coupon = _create_coupon()
        self.assertTrue(coupon.applies_to(branch=branch, programme=programme))

    def test_applies_to_requires_both_branch_and_programme_match(self):
        branch = _create_branch()
        other_branch = _create_branch(code="OTH2", name="Autre 2")
        programme = _create_programme()
        coupon = _create_coupon()
        coupon.branches.add(branch)
        coupon.programmes.add(programme)
        self.assertTrue(coupon.applies_to(branch=branch, programme=programme))
        self.assertFalse(coupon.applies_to(branch=other_branch, programme=programme))
