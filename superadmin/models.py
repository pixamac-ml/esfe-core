from django.conf import settings
from django.db import models


class SuperadminCockpitPreference(models.Model):
    PERIOD_7D = '7d'
    PERIOD_30D = '30d'
    PERIOD_QUARTER = 'quarter'

    PERIOD_CHOICES = (
        (PERIOD_7D, '7 jours'),
        (PERIOD_30D, '30 jours'),
        (PERIOD_QUARTER, 'Trimestre'),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='superadmin_cockpit_pref',
    )
    sidebar_collapsed = models.BooleanField(default=False)
    dashboard_period = models.CharField(max_length=16, choices=PERIOD_CHOICES, default=PERIOD_7D)
    widget_autorefresh = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Préférence Cockpit Superadmin'
        verbose_name_plural = 'Préférences Cockpit Superadmin'

    def __str__(self):
        return f'CockpitPref<{self.user_id}>'
