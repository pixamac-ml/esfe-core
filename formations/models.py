from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from unidecode import unidecode


# ==================================================
# CYCLE (Licence / Master / Doctorat)
# ==================================================
class Cycle(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)

    min_duration_years = models.PositiveSmallIntegerField()
    max_duration_years = models.PositiveSmallIntegerField()

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["min_duration_years"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = unidecode(self.name).lower()
            base = base.replace("'", "").replace("’", "")
            self.slug = slugify(base)
        super().save(*args, **kwargs)


# ==================================================
# DIPLÔME
# ==================================================
class Diploma(models.Model):
    name = models.CharField(max_length=150, unique=True)
    level = models.CharField(
        max_length=50,
        choices=[
            ("secondaire", "Secondaire"),
            ("superieur", "Supérieur"),
        ]
    )

    def __str__(self):
        return self.name


# ==================================================
# FILIÈRE
# ==================================================
class Filiere(models.Model):
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


# ==================================================
# PROGRAMME
# ==================================================
class Programme(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)

    filiere = models.ForeignKey(
        Filiere,
        on_delete=models.PROTECT,
        related_name="programmes"
    )
    cycle = models.ForeignKey(
        Cycle,
        on_delete=models.PROTECT,
        related_name="programmes"
    )
    diploma_awarded = models.ForeignKey(
        Diploma,
        on_delete=models.PROTECT,
        related_name="programmes"
    )

    duration_years = models.PositiveSmallIntegerField()

    short_description = models.CharField(max_length=300)
    description = models.TextField()

    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["title"]
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["is_featured"]),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("formations:detail", args=[self.slug])

    def save(self, *args, **kwargs):
        if not self.slug:
            base = unidecode(self.title).lower()
            base = base.replace("'", "").replace("’", "")
            slug = slugify(base)

            counter = 1
            original_slug = slug
            while Programme.objects.filter(slug=slug).exists():
                slug = f"{original_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)

    # ==================================================
    # LOGIQUE FINANCIÈRE (CLÉ)
    # ==================================================
    def get_inscription_amount_for_year(self, year_number):
        """
        Montant total à payer pour une année donnée :
        somme de toutes les tranches (Fee) de cette année.
        """
        programme_year = self.years.filter(
            year_number=year_number
        ).first()

        if not programme_year:
            return 0

        return sum(
            fee.amount for fee in programme_year.fees.all()
        )


# ==================================================
# ANNÉES DU PROGRAMME
# ==================================================
class ProgrammeYear(models.Model):
    programme = models.ForeignKey(
        Programme,
        related_name="years",
        on_delete=models.CASCADE
    )
    year_number = models.PositiveSmallIntegerField()

    class Meta:
        unique_together = ("programme", "year_number")
        ordering = ["year_number"]

    def __str__(self):
        return f"{self.programme.title} – Année {self.year_number}"


# ==================================================
# FRAIS PAR ANNÉE (TRANCHES)
# ==================================================
class Fee(models.Model):
    programme_year = models.ForeignKey(
        ProgrammeYear,
        related_name="fees",
        on_delete=models.CASCADE
    )
    label = models.CharField(max_length=100)
    amount = models.PositiveIntegerField()
    due_month = models.CharField(max_length=50)

    class Meta:
        ordering = ["amount"]
        unique_together = ("programme_year", "label")

    def __str__(self):
        return f"{self.label} – {self.amount} FCFA"


# ==================================================
# DOCUMENTS REQUIS
# ==================================================
class RequiredDocument(models.Model):
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    is_mandatory = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class ProgrammeRequiredDocument(models.Model):
    programme = models.ForeignKey(
        Programme,
        related_name="required_documents",
        on_delete=models.CASCADE
    )
    document = models.ForeignKey(
        RequiredDocument,
        on_delete=models.PROTECT
    )

    class Meta:
        unique_together = ("programme", "document")
