# payments/admin.py

from django.contrib import admin, messages
from django.utils.html import format_html

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """
    Administration des paiements.

    RÈGLE D’OR :
    - L’admin NE CONTIENT AUCUNE logique métier
    - Il déclenche un changement de statut
    - Le modèle Payment décide de tout le reste
    """

    # ==================================================
    # LISTE
    # ==================================================
    list_display = (
        "id",
        "inscription_reference",
        "candidate_name",
        "programme",
        "amount_display",
        "method_badge",
        "status_badge",
        "paid_at",
        "receipt_link",
    )

    list_filter = (
        "method",
        "status",
        "paid_at",
    )

    search_fields = (
        "reference",
        "receipt_number",
        "inscription__reference",
        "inscription__candidature__first_name",
        "inscription__candidature__last_name",
        "inscription__candidature__programme__title",
    )

    ordering = ("-paid_at",)
    list_per_page = 25

    # ==================================================
    # LECTURE SEULE
    # ==================================================
    readonly_fields = (
        "paid_at",
        "created_at",
        "receipt_number",
        "receipt_pdf",
    )

    # ==================================================
    # FORMULAIRE ADMIN
    # ==================================================
    fieldsets = (
        ("Inscription", {
            "fields": (
                "inscription",
            )
        }),
        ("Paiement", {
            "fields": (
                "amount",
                "method",
                "status",
                "reference",
            )
        }),
        ("Reçu", {
            "fields": (
                "receipt_number",
                "receipt_pdf",
            )
        }),
        ("Système", {
            "fields": (
                "paid_at",
                "created_at",
            )
        }),
    )

    autocomplete_fields = ("inscription",)

    # ==================================================
    # ACTIONS ADMIN
    # ==================================================
    actions = ("validate_payments",)

    @admin.action(description="✅ Valider les paiements sélectionnés")
    def validate_payments(self, request, queryset):
        """
        Action admin minimale :
        - passe le paiement à VALIDATED
        - TOUT le reste est géré par Payment.save()
        """

        validated_count = 0

        for payment in queryset:
            if payment.status != "pending":
                continue

            payment.status = "validated"
            payment.save(update_fields=["status"])
            validated_count += 1

        if validated_count:
            self.message_user(
                request,
                f"{validated_count} paiement(s) validé(s) avec succès.",
                level=messages.SUCCESS
            )
        else:
            self.message_user(
                request,
                "Aucun paiement en attente à valider.",
                level=messages.WARNING
            )

    # ==================================================
    # MÉTHODES D’AFFICHAGE
    # ==================================================
    @admin.display(description="Référence inscription")
    def inscription_reference(self, obj):
        return obj.inscription.reference

    @admin.display(description="Candidat")
    def candidate_name(self, obj):
        c = obj.inscription.candidature
        return f"{c.last_name} {c.first_name}"

    @admin.display(description="Formation")
    def programme(self, obj):
        return obj.inscription.candidature.programme.title

    @admin.display(description="Montant")
    def amount_display(self, obj):
        return format_html("<strong>{} FCFA</strong>", obj.amount)

    @admin.display(description="Méthode")
    def method_badge(self, obj):
        colors = {
            "cash": "#6c757d",
            "orange_money": "#fd7e14",
            "bank_transfer": "#0d6efd",
        }
        return format_html(
            '<span style="padding:4px 8px; border-radius:4px; '
            'background:{}; color:white; font-weight:600;">{}</span>',
            colors.get(obj.method, "#6c757d"),
            obj.get_method_display()
        )

    @admin.display(description="Statut")
    def status_badge(self, obj):
        colors = {
            "pending": "#ffc107",
            "validated": "#198754",
            "cancelled": "#dc3545",
        }
        return format_html(
            '<span style="padding:4px 8px; border-radius:4px; '
            'background:{}; color:white; font-weight:600;">{}</span>',
            colors.get(obj.status, "#6c757d"),
            obj.get_status_display()
        )

    @admin.display(description="📄 Reçu")
    def receipt_link(self, obj):
        if obj.receipt_pdf:
            return format_html(
                '<a href="{}" target="_blank" style="font-weight:600;">'
                'Télécharger</a>',
                obj.receipt_pdf.url
            )
        return "-"


from django.contrib import admin
from .models import PaymentAgent, CashPaymentSession


@admin.register(PaymentAgent)
class PaymentAgentAdmin(admin.ModelAdmin):
    list_display = ("user", "agent_code", "is_active", "created_at")
    search_fields = ("user__first_name", "user__last_name")
    list_filter = ("is_active",)


@admin.register(CashPaymentSession)
class CashPaymentSessionAdmin(admin.ModelAdmin):
    list_display = (
        "inscription",
        "agent",
        "verification_code",
        "is_used",
        "expires_at",
        "created_at",
    )
    search_fields = (
        "inscription__reference",
        "agent__user__first_name",
        "agent__user__last_name",
    )
    list_filter = ("is_used",)

