from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django_ckeditor_5.fields import CKEditor5Field
from formations.models import Filiere

from .storage import memoire_private_storage


class Memoire(models.Model):
    class Niveau(models.TextChoices):
        LICENCE = "licence", "Licence"
        MASTER = "master", "Master"
        DOCTORAT = "doctorat", "Doctorat"

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        PUBLIE = "publie", "Publié"

    titre = models.CharField(max_length=300)
    slug = models.SlugField(max_length=320, unique=True)
    auteurs = models.CharField(max_length=300, help_text="Auteur(s) du mémoire")
    encadreur = models.CharField(max_length=200, blank=True)
    filiere = models.ForeignKey(
        Filiere, on_delete=models.PROTECT, related_name="memoires"
    )
    niveau = models.CharField(max_length=20, choices=Niveau.choices)
    annee = models.PositiveIntegerField()

    resume = CKEditor5Field(
        "Résumé", config_name="default",
        help_text="Résumé / abstract affiché publiquement.",
    )
    mots_cles = models.CharField(max_length=300, blank=True, help_text="Séparés par des virgules")

    # Fichier source PRIVÉ — jamais servi directement au public.
    fichier_source = models.FileField(
        upload_to="memoires/sources/", storage=memoire_private_storage
    )
    nb_pages = models.PositiveIntegerField(default=0)

    est_mis_en_avant = models.BooleanField(default=False, db_index=True, verbose_name="Mis en avant")
    statut = models.CharField(
        max_length=20, choices=Statut.choices, default=Statut.BROUILLON, db_index=True
    )
    nombre_vues = models.PositiveIntegerField(default=0)

    date_depot = models.DateTimeField(default=timezone.now, blank=True)
    date_publication = models.DateTimeField(null=True, blank=True)

    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="memoires_deposes"
    )

    class Meta:
        verbose_name = "Mémoire"
        verbose_name_plural = "Mémoires"
        ordering = ["-date_publication", "-date_depot"]
        indexes = [
            models.Index(fields=["statut", "niveau"]),
            models.Index(fields=["-nombre_vues"]),
        ]

    def __str__(self):
        return f"{self.titre} ({self.annee})"

    def get_absolute_url(self):
        return reverse("memoires:detail", kwargs={"slug": self.slug})

    @property
    def est_public(self):
        return self.statut == self.Statut.PUBLIE


class PageMemoire(models.Model):
    """Image pré-générée d'une page (corps protégé, non copiable)."""

    memoire = models.ForeignKey(Memoire, on_delete=models.CASCADE, related_name="pages")
    numero = models.PositiveIntegerField()
    image = models.ImageField(upload_to="memoires/pages/", storage=memoire_private_storage)

    class Meta:
        verbose_name = "Page de mémoire"
        verbose_name_plural = "Pages de mémoire"
        ordering = ["numero"]
        constraints = [
            models.UniqueConstraint(fields=["memoire", "numero"], name="unique_page_par_memoire"),
        ]


class ConsultationLog(models.Model):
    """Journal des consultations -> permet le classement 'les plus consultés du mois'."""

    memoire = models.ForeignKey(Memoire, on_delete=models.CASCADE, related_name="consultations")
    date = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Consultation"
        verbose_name_plural = "Consultations"
        indexes = [models.Index(fields=["memoire", "date"])]
