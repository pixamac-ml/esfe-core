# Generated manually for controlled payment correction audit trail.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("branches", "0002_branch_image"),
        ("payments", "0005_payment_cash_session"),
    ]

    operations = [
        migrations.CreateModel(
            name="PaymentCorrection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("old_amount", models.PositiveBigIntegerField()),
                ("new_amount", models.PositiveBigIntegerField()),
                ("delta_amount", models.BigIntegerField()),
                ("reason", models.TextField()),
                ("corrected_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "corrected_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payment_corrections",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "payment",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="corrections",
                        to="payments.payment",
                    ),
                ),
            ],
            options={
                "ordering": ["-corrected_at"],
            },
        ),
        migrations.CreateModel(
            name="FinancialLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("payment_created", "Paiement cree"),
                            ("payment_validated", "Paiement valide"),
                            ("payment_cancelled", "Paiement annule"),
                            ("payment_corrected", "Paiement corrige"),
                            ("expense", "Depense"),
                            ("export", "Export"),
                            ("print", "Impression"),
                        ],
                        db_index=True,
                        max_length=40,
                    ),
                ),
                ("old_amount", models.PositiveBigIntegerField(blank=True, null=True)),
                ("new_amount", models.PositiveBigIntegerField(blank=True, null=True)),
                ("delta_amount", models.BigIntegerField(default=0)),
                ("reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="financial_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "branch",
                    models.ForeignKey(
                        blank=True,
                        db_index=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="financial_logs",
                        to="branches.branch",
                    ),
                ),
                (
                    "correction",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="financial_logs",
                        to="payments.paymentcorrection",
                    ),
                ),
                (
                    "payment",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="financial_logs",
                        to="payments.payment",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="paymentcorrection",
            index=models.Index(fields=["payment", "corrected_at"], name="payments_pa_payment_6829aa_idx"),
        ),
        migrations.AddIndex(
            model_name="paymentcorrection",
            index=models.Index(fields=["corrected_by", "corrected_at"], name="payments_pa_correct_259c8b_idx"),
        ),
        migrations.AddIndex(
            model_name="financiallog",
            index=models.Index(fields=["branch", "created_at"], name="payments_fi_branch__1e6602_idx"),
        ),
        migrations.AddIndex(
            model_name="financiallog",
            index=models.Index(fields=["action", "created_at"], name="payments_fi_action_fbc783_idx"),
        ),
        migrations.AddIndex(
            model_name="financiallog",
            index=models.Index(fields=["payment", "created_at"], name="payments_fi_payment_bd2da0_idx"),
        ),
    ]
