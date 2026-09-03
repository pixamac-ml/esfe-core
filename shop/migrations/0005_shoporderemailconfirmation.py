from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("shop", "0004_rename_shop_shopcas_expires_6918b4_idx_shop_shopca_expires_9e1c65_idx_and_more"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="ShopOrderEmailConfirmation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.PositiveIntegerField()), ("otp_code_hash", models.CharField(max_length=256)),
                ("expires_at", models.DateTimeField(db_index=True)), ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("resend_count", models.PositiveSmallIntegerField(default=0)), ("last_sent_at", models.DateTimeField(blank=True, null=True)),
                ("status", models.CharField(choices=[("pending", "En attente de confirmation"), ("confirmed", "Confirmee"), ("expired", "Expiree"), ("cancelled", "Annulee")], db_index=True, default="pending", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("branch", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="shop_order_email_confirmations", to="branches.branch")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="shop_order_email_confirmations", to=settings.AUTH_USER_MODEL)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="email_order_confirmations", to="shop.shopproduct")),
                ("order", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="email_confirmation", to="shop.shoporder")),
            ],
            options={"indexes": [models.Index(fields=["student", "status", "expires_at"], name="shop_shopor_student_535be3_idx")]},
        )
    ]
