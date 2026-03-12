# inscriptions/admin.py

from django.contrib import admin, messages
from django.db import transaction
from django.utils.html import format_html
from django.utils import timezone
import secrets

from .models import Inscription
from inscriptions.services import create_inscription_from_candidature
from admissions.models import Candidature


# ==================================================
# ACTION ADMIN : ACCEPTER CANDIDATURE
# ==================================================
@admin.action(description="✅ Accepter la candidature et creer l'inscription")
def accepter_candidature(modeladmin, request, queryset):

    created_count = 0
    skipped_count = 0

    for candidature in queryset:

        if candidature.status in ("accepted", "accepted_with_reserve"):
            skipped_count += 1
            continue

        if hasattr(candidature, "inscription"):
            skipped_count += 1
            continue

        programme = candidature.programme
        amount_due = programme.total_price

        with transaction.atomic():
            create_inscription_from_candidature(
                candidature=candidature,
                amount_due=amount_due
            )

            candidature.status = "accepted"
            candidature.save(update_fields=["status"])

        created_count += 1

    if created_count:
        modeladmin.message_user(
            request,
            f"{created_count} inscription(s) creee(s) avec succes.",
            level=messages.SUCCESS
        )

    if skipped_count:
        modeladmin.message_user(
            request,
            f"{skipped_count} candidature(s) ignoree(s) "
            f"(deja acceptee ou inscription existante).",
            level=messages.WARNING
        )


# ==================================================
# ACTION ADMIN : REGENERER CODE D'ACCES
# ==================================================
@admin.action(description="Regenerer le code d'acces")
def regenerate_access_code(modeladmin, request, queryset):

    for inscription in queryset:
        inscription.access_code = secrets.token_urlsafe(6)
        inscription.save(update_fields=["access_code"])

    modeladmin.message_user(
        request,
        "Code(s) d'acces regeneré(s) avec succes.",
        level=messages.SUCCESS
    )


# ==================================================
# ACTIONS POUR CHANGER LE STATUT
# ==================================================

@admin.action(description="Passer en Active")
def mark_active(modeladmin, request, queryset):
    updated = queryset.exclude(status="active").update(status="active")
    messages.success(request, f"{updated} inscription(s) passee(s) en Active.")

@admin.action(description="Passer en Suspendue")
def mark_suspended(modeladmin, request, queryset):
    updated = queryset.update(status="suspended")
    messages.success(request, f"{updated} inscription(s) suspendue(s).")

@admin.action(description="Passer en Expiree")
def mark_expired(modeladmin, request, queryset):
    updated = queryset.update(status="expired")
    messages.success(request, f"{updated} inscription(s) expiree(s).")

@admin.action(description="Passer en Transferlee")
def mark_transferred(modeladmin, request, queryset):
    updated = queryset.update(status="transferred")
    messages.success(request, f"{updated} inscription(s) transferee(s).")

@admin.action(description="Passer en Terminee")
def mark_completed(modeladmin, request, queryset):
    updated = queryset.update(status="completed")
    messages.success(request, f"{updated} inscription(s) terminee(s).")


# ==================================================
# ADMIN INSCRIPTION
# ==================================================
@admin.register(Inscription)
class InscriptionAdmin(admin.ModelAdmin):

    # ==================================================
    # LISTE
    # ==================================================
    list_display = (
        "id",
        "reference",
        "candidate_name",
        "programme_title",
        "status_badge",
        "amount_due_display",
        "amount_paid_display",
        "balance_display",
        "access_code_display",
        "created_at",
        "public_link",
    )

    list_filter = ("status",)
    ordering = ("-created_at",)
    list_per_page = 25

    search_fields = (
        "reference",
        "public_token",
        "access_code",
        "candidature__first_name",
        "candidature__last_name",
        "candidature__programme__title",
    )

    # ==================================================
    # CHAMPS
    # ==================================================
    readonly_fields = (
        "reference",
        "public_token",
        "access_code",
        "amount_paid",
        "created_at",
    )

    fieldsets = (
        ("Candidature", {
            "fields": ("candidature",)
        }),
        ("Statut", {
            "fields": ("status",)
        }),
        ("Finances (copie figee)", {
            "description": (
                "Le montant a payer est copie depuis le programme "
                "au moment de l'acceptation. "
                "Il peut etre ajuste ici en cas particulier."
            ),
            "fields": (
                "amount_due",
                "amount_paid",
            )
        }),
        ("Securite d'acces", {
            "description": "Code requis pour acceder au dossier etudiant.",
            "fields": (
                "public_token",
                "access_code",
            )
        }),
        ("Systeme", {
            "fields": (
                "reference",
                "created_at",
            )
        }),
    )


    # ==================================================
    # METHODES D'AFFICHAGE
    # ==================================================

    @admin.action(description="Generer code d'acces si absent")
    def generate_missing_access_codes(modeladmin, request, queryset):

        generated = 0

        for inscription in queryset:
            if not inscription.access_code:
                inscription.access_code = secrets.token_urlsafe(6)
                inscription.save(update_fields=["access_code"])
                generated += 1

        modeladmin.message_user(
            request,
            f"{generated} code(s) genere(s).",
            level=messages.SUCCESS
        )

    @admin.display(description="Candidat")
    def candidate_name(self, obj):
        c = obj.candidature
        return f"{c.last_name} {c.first_name}"

    @admin.display(description="Formation")
    def programme_title(self, obj):
        return obj.candidature.programme.title

    @admin.display(description="Statut")
    def status_badge(self, obj):
        colors = {
            "created": "#0d6efd",
            "active": "#198754",
            "suspended": "#dc3545",
            "expired": "#6c757d",
            "transferred": "#fd7e14",
            "completed": "#20c997",
        }
        return format_html(
            '<span style="padding:4px 8px; border-radius:4px; '
            'background:{}; color:white; font-weight:600;">{}</span>',
            colors.get(obj.status, "#6c757d"),
            obj.get_status_display()
        )

    @admin.display(description="Total")
    def amount_due_display(self, obj):
        return format_html("<strong>{} FCFA</strong>", obj.amount_due)

    @admin.display(description="Paye")
    def amount_paid_display(self, obj):
        return format_html("{} FCFA", obj.amount_paid)

    @admin.display(description="Solde")
    def balance_display(self, obj):
        return format_html(
            "<strong>{} FCFA</strong>",
            obj.balance
        )

    @admin.display(description="Code d'acces")
    def access_code_display(self, obj):
        return format_html(
            '<span style="font-weight:600; color:#0d6efd;">{}</span>',
            obj.access_code
        )

    @admin.display(description="Lien public etudiant")
    def public_link(self, obj):
        return format_html(
            '<a href="{}" target="_blank" style="font-weight:600;">'
            'Ouvrir le dossier</a>',
            obj.get_public_url()
        )

    # AJOUT DES NOUVELLES ACTIONS
    actions = [
        accepter_candidature,
        regenerate_access_code,
        generate_missing_access_codes,
        mark_active,
        mark_suspended,
        mark_expired,
        mark_transferred,
        mark_completed,
    ]