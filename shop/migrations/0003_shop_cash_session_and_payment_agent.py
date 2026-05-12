from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0005_payment_cash_session"),
        ("shop", "0002_shop_catalog_and_counter_sales"),
    ]

    operations = [
        migrations.CreateModel(
            name="ShopCashPaymentSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("verification_code", models.CharField(max_length=6)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("is_used", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "agent",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="shop_cash_sessions",
                        to="payments.paymentagent",
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cash_sessions",
                        to="shop.shoporder",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="shoppayment",
            name="agent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="shop_payments_collected",
                to="payments.paymentagent",
            ),
        ),
        migrations.AddField(
            model_name="shoppayment",
            name="cash_session",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="payments",
                to="shop.shopcashpaymentsession",
            ),
        ),
        migrations.AddIndex(
            model_name="shopcashpaymentsession",
            index=models.Index(fields=["expires_at"], name="shop_shopcas_expires_6918b4_idx"),
        ),
        migrations.AddIndex(
            model_name="shopcashpaymentsession",
            index=models.Index(fields=["is_used"], name="shop_shopcas_is_used_8f91e7_idx"),
        ),
        migrations.AddIndex(
            model_name="shopcashpaymentsession",
            index=models.Index(fields=["agent", "created_at"], name="shop_shopcas_agent_i_62e6f5_idx"),
        ),
        migrations.AddIndex(
            model_name="shopcashpaymentsession",
            index=models.Index(fields=["order", "agent", "is_used"], name="shop_shopcas_order_i_d4ae18_idx"),
        ),
    ]
