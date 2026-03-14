# inscriptions/admin.py

from django.contrib import admin, messages
from django.db import transaction
from django.utils.html import format_html
from django.utils import timezone
import secrets

from .models import Inscription, StatusHistory
from inscriptions.services import create_inscription_from_candidature
from admissions.models import Candidature


# ==================================================
# ACTION : ACCEPTER CANDIDATURE
# ==================================================

@admin.action(description="Accepter la candidature et creer l'inscription")
def accepter_candidature(modeladmin, request, queryset):

    created = 0
    skipped = 0

    for candidature in queryset:

        if candidature.status not in ["submitted", "under_review"]:
            skipped += 1
            continue

        if hasattr(candidature, "inscription"):
            skipped += 1
            continue

        programme = candidature.programme
        amount_due = programme.total_price

        with transaction.atomic():

            candidature.status = "accepted"
            candidature.reviewed_at = timezone.now()
            candidature.save(update_fields=["status", "reviewed_at"])

            create_inscription_from_candidature(
                candidature=candidature,
                amount_due=amount_due
            )

        created += 1

    if created:
        modeladmin.message_user(
            request,
            f"{created} inscription(s) creee(s).",
            messages.SUCCESS
        )

    if skipped:
        modeladmin.message_user(
            request,
            f"{skipped} candidature(s) ignoree(s).",
            messages.WARNING
        )


# ==================================================
# ACTION : REGENERER CODE ACCES
# ==================================================

@admin.action(description="Regenerer code d'acces")
def regenerate_access_code(modeladmin, request, queryset):

    for inscription in queryset:
        inscription.access_code = secrets.token_urlsafe(6)
        inscription.save(update_fields=["access_code"])

    messages.success(request, "Code(s) regeneres.")


# ==================================================
# ACTION : ARCHIVER
# ==================================================

@admin.action(description="Archiver inscription")
def archive_inscriptions(modeladmin, request, queryset):

    updated = queryset.update(
        is_archived=True,
        archived_at=timezone.now()
    )

    messages.success(request, f"{updated} inscription(s) archivee(s).")


# ==================================================
# ACTION : RESTAURER
# ==================================================

@admin.action(description="Restaurer inscription archivee")
def restore_inscriptions(modeladmin, request, queryset):

    updated = queryset.update(
        is_archived=False,
        archived_at=None
    )

    messages.success(request, f"{updated} inscription(s) restauree(s).")


# ==================================================
# ACTIONS STATUT
# ==================================================

@admin.action(description="Passer en Active")
def mark_active(modeladmin, request, queryset):
    updated = queryset.exclude(status="active").update(status="active")
    messages.success(request, f"{updated} inscription(s) active(s).")


@admin.action(description="Passer en Suspendue")
def mark_suspended(modeladmin, request, queryset):
    updated = queryset.update(status="suspended")
    messages.success(request, f"{updated} inscription(s) suspendue(s).")


@admin.action(description="Passer en Expiree")
def mark_expired(modeladmin, request, queryset):
    updated = queryset.update(status="expired")
    messages.success(request, f"{updated} inscription(s) expiree(s).")


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
    # LIST DISPLAY
    # ==================================================

    list_display = (
        "id",
        "reference",
        "candidate_name",
        "programme_title",
        "access_code",
        "status_badge",
        "amount_due_display",
        "amount_paid_display",
        "balance_display",
        "archive_badge",
        "created_at",
        "public_link",
    )

    list_filter = (
        "status",
        "is_archived",
        "created_at",
    )

    ordering = ("-created_at",)

    list_per_page = 30

    search_fields = (
        "reference",
        "public_token",
        "access_code",
        "candidature__first_name",
        "candidature__last_name",
        "candidature__programme__title",
    )

    autocomplete_fields = ("candidature",)

    # ==================================================
    # READONLY
    # ==================================================

    readonly_fields = (
        "reference",
        "public_token",
        "access_code",
        "amount_paid",
        "created_at",
        "archived_at",
    )

    # ==================================================
    # FIELDSETS
    # ==================================================

    fieldsets = (

        ("Candidature", {
            "fields": ("candidature",)
        }),

        ("Statut", {
            "fields": ("status",)
        }),

        ("Finances", {
            "fields": (
                "amount_due",
                "amount_paid",
            )
        }),

        ("Acces", {
            "fields": (
                "public_token",
                "access_code",
            )
        }),

        ("Archivage", {
            "fields": (
                "is_archived",
                "archived_at",
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
    # DISPLAY METHODS
    # ==================================================

    @admin.display(description="Candidat")
    def candidate_name(self, obj):

        c = obj.candidature
        return f"{c.last_name} {c.first_name}"

    @admin.display(description="Programme")
    def programme_title(self, obj):

        return obj.candidature.programme.title

    @admin.display(description="Statut")
    def status_badge(self, obj):

        colors = {
            "created": "#0d6efd",
            "awaiting_payment": "#ffc107",
            "partial_paid": "#0dcaf0",
            "active": "#198754",
            "suspended": "#dc3545",
            "expired": "#6c757d",
            "completed": "#20c997",
        }

        return format_html(
            '<span style="padding:4px 8px;border-radius:4px;background:{};color:white;font-weight:600;">{}</span>',
            colors.get(obj.status, "#6c757d"),
            obj.get_status_display()
        )

    @admin.display(description="Archive")
    def archive_badge(self, obj):
        if obj.is_archived:
            return format_html(
                '<span style="color:{};font-weight:600;">{}</span>',
                "#dc3545",
                "Archivé"
            )

        return format_html(
            '<span style="color:{};font-weight:600;">{}</span>',
            "#198754",
            "Actif"
        )

    @admin.display(description="Total")
    def amount_due_display(self, obj):
        return format_html("<strong>{} FCFA</strong>", obj.amount_due or 0)


    @admin.display(description="Paye")
    def amount_paid_display(self, obj):

        return format_html("{} FCFA", obj.amount_paid)

    @admin.display(description="Solde")
    def balance_display(self, obj):

        return format_html("<strong>{} FCFA</strong>", obj.balance)

    @admin.display(description="Lien dossier")
    def public_link(self, obj):

        return format_html(
            '<a href="{}" target="_blank">Ouvrir</a>',
            obj.get_public_url()
        )

    # ==================================================
    # ACTIONS
    # ==================================================

    actions = [

        regenerate_access_code,

        archive_inscriptions,
        restore_inscriptions,

        mark_active,
        mark_suspended,
        mark_expired,
        mark_completed,

    ]


# ==================================================
# ADMIN HISTORIQUE
# ==================================================

@admin.register(StatusHistory)
class StatusHistoryAdmin(admin.ModelAdmin):

    list_display = (
        "inscription",
        "previous_status",
        "new_status",
        "created_at",
    )

    search_fields = (
        "inscription__reference",
    )

    ordering = ("-created_at",)

    readonly_fields = (
        "inscription",
        "previous_status",
        "new_status",
        "created_at",
    )