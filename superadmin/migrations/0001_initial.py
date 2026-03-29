from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SuperadminCockpitPreference',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sidebar_collapsed', models.BooleanField(default=False)),
                ('dashboard_period', models.CharField(choices=[('7d', '7 jours'), ('30d', '30 jours'), ('quarter', 'Trimestre')], default='7d', max_length=16)),
                ('widget_autorefresh', models.BooleanField(default=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=models.deletion.CASCADE, related_name='superadmin_cockpit_pref', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Préférence Cockpit Superadmin',
                'verbose_name_plural': 'Préférences Cockpit Superadmin',
            },
        ),
    ]

