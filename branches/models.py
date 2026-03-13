# branches/models.py

from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Branch(models.Model):
    """
    Représente une école/annexe de l'institution.
    """

    name = models.CharField(
        max_length=150,
        unique=True,
        verbose_name="Nom de l'annexe"
    )

    code = models.CharField(
        max_length=10,
        unique=True,
        help_text="Code court (ex: KC, BC, KT)"
    )

    slug = models.SlugField(unique=True)

    address = models.TextField(blank=True)

    city = models.CharField(max_length=100, default="Bamako")

    phone = models.CharField(max_length=30, blank=True)

    email = models.EmailField(blank=True)

    manager = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_branches"
    )

    is_active = models.BooleanField(default=True)

    accepts_online_registration = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Annexe"
        verbose_name_plural = "Annexes"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"