from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("inscriptions", "0005_alter_statushistory_options_inscription_updated_at_and_more"),
        ("shop", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="shopproduct",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="shop/products/"),
        ),
        migrations.AddField(
            model_name="shoporder",
            name="buyer_type",
            field=models.CharField(
                choices=[("student", "Etudiant"), ("walk_in", "Vente comptoir")],
                db_index=True,
                default="student",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="shoporder",
            name="customer_email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="shoporder",
            name="customer_name",
            field=models.CharField(blank=True, max_length=180),
        ),
        migrations.AddField(
            model_name="shoporder",
            name="customer_phone",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="shoporder",
            name="prepared_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="shoporder",
            name="prepared_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="prepared_shop_orders", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name="shoporder",
            name="inscription",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="shop_orders", to="inscriptions.inscription"),
        ),
        migrations.AlterField(
            model_name="shoporder",
            name="student",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="shop_orders", to=settings.AUTH_USER_MODEL),
        ),
    ]
