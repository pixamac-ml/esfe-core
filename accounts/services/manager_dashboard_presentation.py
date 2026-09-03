"""Presentation contract for the certified manager dashboard workspace.

The manager business view owns queries and branch scoping.  This module only
normalizes already-authorized values for the UI Core components rendered inside
the certified Director of Studies shell.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.contrib.humanize.templatetags.humanize import intcomma
from django.urls import reverse
from django.utils import formats

from admissions.models import Candidature
from accounts.models import (
    BranchCashMovement,
    BranchExpense,
    BranchMonthlyClosure,
    Donation,
    PayrollEntry,
    TeacherHonorariumEntry,
)
from inscriptions.models import Inscription
from payments.models import Payment
from shop.models import ShopProduct


SECTION_PRESENTATION = {
    "overview": {
        "eyebrow": "Gestionnaire / Pilotage du jour",
        "title": "Espace de travail de l'annexe",
        "subtitle": "Traitez les opérations ouvertes ; le reste demeure accessible dans l'historique.",
        "components": ("page_header", "stat_card", "panel", "alert", "empty_state"),
    },
    "candidatures": {
        "eyebrow": "Gestionnaire / Parcours étudiant",
        "title": "Candidatures",
        "subtitle": "Traiter les dossiers entrants, demander les complements et ouvrir le parcours d'inscription.",
        "components": ("page_header", "stat_card", "filter_bar", "data_table", "status_badge", "empty_state"),
    },
    "inscriptions": {
        "eyebrow": "Gestionnaire / Parcours étudiant",
        "title": "Inscriptions",
        "subtitle": "Finaliser les dossiers acceptes et suivre leur situation administrative et financiere.",
        "components": ("page_header", "stat_card", "filter_bar", "data_table", "status_badge", "drawer"),
    },
    "reenrollment": {
        "eyebrow": "Gestionnaire / Parcours étudiant",
        "title": "Réinscriptions",
        "subtitle": "Préparer les dossiers validés pédagogiquement, suivre le paiement existant et laisser le moteur activer la nouvelle année.",
        "components": ("page_header", "stat_card", "filter_bar", "data_table", "status_badge", "empty_state"),
    },
    "paiements": {
        "eyebrow": "Gestionnaire / Finance",
        "title": "Paiements",
        "subtitle": "Controler les justificatifs, les sessions espece et la validation des encaissements.",
        "components": ("page_header", "stat_card", "panel", "filter_bar", "data_table", "confirm_dialog"),
    },
    "salaires": {
        "eyebrow": "Gestionnaire / Personnel",
        "title": "Salaires du personnel",
        "subtitle": "Verifier, corriger, valider puis payer les fiches automatiquement preparees.",
        "components": ("page_header", "stat_card", "filter_bar", "data_table", "status_badge", "modal"),
    },
    "honoraires": {
        "eyebrow": "Gestionnaire / Enseignement",
        "title": "Honoraires enseignants",
        "subtitle": "Contrôler les heures validées, rendre les fiches disponibles et tracer chaque paiement.",
        "components": ("page_header", "stat_card", "filter_bar", "data_table", "status_badge", "modal"),
    },
    "depenses": {
        "eyebrow": "Gestionnaire / Exploitation",
        "title": "Depenses",
        "subtitle": "Soumettre, approuver, payer et tracer les sorties de l'annexe.",
        "components": ("page_header", "stat_card", "panel", "form_field", "filter_bar", "data_table"),
    },
    "caisse": {
        "eyebrow": "Gestionnaire / Tresorerie",
        "title": "Caisse",
        "subtitle": "Suivre les entrees, les sorties, les synchronisations et les pieces de caisse.",
        "components": ("page_header", "stat_card", "panel", "filter_bar", "data_table", "confirm_dialog"),
    },
    "rapport": {
        "eyebrow": "Gestionnaire / Contrôle et archives",
        "title": "Rapports et archives",
        "subtitle": "Consulter une période, contrôler les flux et exporter le rapport de l'annexe.",
        "components": ("page_header", "filter_bar", "stat_card", "alert", "data_table", "chart_panel"),
    },
    "cloture": {
        "eyebrow": "Gestionnaire / Contrôle et clôture",
        "title": "Clôture mensuelle et archives",
        "subtitle": "Contrôler la période, la clôturer sans suppression et conserver ses archives.",
        "components": ("page_header", "stat_card", "alert", "panel", "data_table", "confirm_dialog"),
    },
    "boutique": {
        "eyebrow": "Gestionnaire / Exploitation",
        "title": "Boutique",
        "subtitle": "Piloter le catalogue, le stock, les commandes et la caisse boutique de l'annexe.",
        "components": ("page_header", "stat_card", "tabs", "filter_bar", "data_table", "drawer", "modal"),
    },
    "dons": {
        "eyebrow": "Gestionnaire / Exploitation",
        "title": "Dons et donations",
        "subtitle": "Enregistrer les appuis financiers ou en nature et conserver leur tracabilite.",
        "components": ("page_header", "stat_card", "panel", "form_field", "data_table", "empty_state"),
    },
    "settings": {
        "eyebrow": "Gestionnaire / Compte",
        "title": "Profil professionnel et securite",
        "subtitle": "Consulter l'identite institutionnelle et les acces rattaches a cette annexe.",
        "components": ("page_header", "panel", "profile_view", "security_settings"),
    },
}


# A manager section is a business domain.  These are deliberately limited to
# workflows that already exist in the manager workspace; a tab must never be
# a promise for a future, empty screen.
MANAGER_SUBVIEW_DEFINITIONS = {
    "candidatures": (
        ("overview", "Vue d'ensemble", "layout-dashboard"),
        ("list", "Candidatures", "files"),
        ("to_process", "À traiter", "clock-3"),
    ),
    "inscriptions": (
        ("overview", "Vue d'ensemble", "layout-dashboard"),
        ("list", "Inscriptions", "id-card"),
        ("pending", "En attente", "clock-3"),
    ),
    "reenrollment": (
        ("overview", "Tableau opérationnel", "refresh-cw"),
    ),
    "paiements": (
        ("overview", "Vue d'ensemble", "layout-dashboard"),
        ("payments", "Paiements", "credit-card"),
        ("cash_sessions", "Sessions espèces", "badge-dollar-sign"),
        ("to_validate", "À valider", "circle-check"),
    ),
    "salaires": (
        ("overview", "Vue d'ensemble", "layout-dashboard"),
        ("entries", "Fiches", "files"),
        ("to_validate", "À contrôler", "scan-search"),
        ("to_pay", "À payer", "wallet-cards"),
        ("history", "Historique", "history"),
    ),
    "honoraires": (
        ("overview", "Vue d'ensemble", "layout-dashboard"),
        ("entries", "Fiches", "files"),
        ("to_validate", "À contrôler", "scan-search"),
        ("to_pay", "À payer", "wallet-cards"),
        ("history", "Historique", "history"),
    ),
    "depenses": (
        ("overview", "Vue d'ensemble", "layout-dashboard"),
        ("expenses", "Dépenses", "receipt"),
        ("new", "Nouvelle dépense", "plus"),
        ("to_approve", "À approuver", "circle-check"),
    ),
    "caisse": (
        ("overview", "Vue d'ensemble", "layout-dashboard"),
        ("wallets", "Mini-caisses", "wallet"),
        ("movements", "Mouvements", "arrow-left-right"),
        ("operations", "Opérations", "plus"),
    ),
    "rapport": (
        ("overview", "Vue d'ensemble", "layout-dashboard"),
        ("movements", "Mouvements", "arrow-left-right"),
        ("exports", "Exports", "download"),
    ),
    "cloture": (
        ("overview", "Vue d'ensemble", "layout-dashboard"),
        ("closures", "Clôtures", "lock"),
        ("archives", "Archives", "archive"),
    ),
    "dons": (
        ("overview", "Vue d'ensemble", "layout-dashboard"),
        ("register", "Enregistrer", "plus"),
        ("history", "Historique", "history"),
    ),
    "boutique": (
        ("sell", "Vendre", "shopping-cart"),
        ("to_collect", "À encaisser", "badge-dollar-sign"),
        ("to_prepare", "À préparer", "package-check"),
        ("to_deliver", "À remettre", "package-open"),
        ("stock", "Stock & articles", "package"),
        ("journal", "Journal", "book-open-check"),
    ),
}

# A focused tab starts with the matching existing server-side filter.  The
# user can still refine it through the normal filter bar; branch filtering
# remains owned by the queryset layer.
MANAGER_SUBVIEW_FILTERS = {
    ("candidatures", "to_process"): {"cand_status": "open"},
    ("inscriptions", "pending"): {"ins_status": "open"},
    ("paiements", "to_validate"): {"pay_status": "pending"},
    ("salaires", "to_validate"): {"salary_status": "draft"},
    ("salaires", "to_pay"): {"salary_status": "payable"},
    ("salaires", "history"): {"salary_status": "paid"},
    ("honoraires", "to_validate"): {"honorarium_status": "draft"},
    ("honoraires", "to_pay"): {"honorarium_status": "payable"},
    ("honoraires", "history"): {"honorarium_status": "paid"},
    ("depenses", "to_approve"): {"expense_status": "submitted"},
    ("boutique", "to_collect"): {"shop_status": "pending_payment"},
    ("boutique", "to_prepare"): {"shop_status": "paid"},
    ("boutique", "to_deliver"): {"shop_status": "ready"},
}


def normalize_manager_subview(section, raw_subview):
    """Return a safe, existing subview for a manager business domain."""

    allowed = {item[0] for item in MANAGER_SUBVIEW_DEFINITIONS.get(section, ())}
    subview = str(raw_subview or "overview").strip().lower()
    return subview if subview in allowed else "overview"


def manager_subcontent_template(section):
    """Return the HTMX subcontent partial for a manager business domain."""

    if section in MANAGER_SUBVIEW_DEFINITIONS:
        return f"accounts/dashboard/partials/manager_subcontents/{section}.html"
    return ""


def manager_subcontent_target(section):
    return f"#manager-{section}-subcontent"


def manager_subcontent_indicator(section):
    return f"#manager-{section}-loading"


def _manager_section_query(section, context, **params):
    """Build a GET query preserving the active subview when relevant."""

    query = {"section": section, **params}
    subview = context.get("manager_subview") or ""
    if subview and subview != "overview":
        query["view"] = subview
    return query


def _manager_subnav_items(*, section, active, dashboard_url, subcontent_url, counts=None):
    definitions = MANAGER_SUBVIEW_DEFINITIONS.get(section, ())
    if not definitions:
        return []
    target = manager_subcontent_target(section)
    indicator = manager_subcontent_indicator(section)
    items = []
    counts = counts or {}
    for item_id, label, icon in definitions:
        query = {"section": section, "view": item_id}
        query.update(MANAGER_SUBVIEW_FILTERS.get((section, item_id), {}))
        encoded_query = urlencode(query)
        items.append(
            {
                "id": item_id,
                "label": label,
                "icon": icon,
                "count": counts.get(item_id),
                "href": f"{dashboard_url}?{encoded_query}",
                "hx_get": f"{subcontent_url}?{encoded_query}",
                "hx_target": target,
                "hx_swap": "innerHTML",
                "hx_push_url": f"{dashboard_url}?{encoded_query}",
                "hx_indicator": indicator,
                "hx_sync": f"{target}:replace",
            }
        )
    return items


def _augment_manager_filters(filters, *, section, subview):
    if not filters or not subview or subview == "overview":
        return filters
    payload = dict(filters)
    hidden_fields = list(payload.get("hidden_fields") or [])
    if not any(field.get("name") == "view" for field in hidden_fields):
        hidden_fields.append({"name": "view", "value": subview})
    payload["hidden_fields"] = hidden_fields
    reset_query = urlencode({"section": section, "view": subview})
    payload["reset_url"] = f"{payload.get('action', '')}?{reset_query}"
    return payload


def _money(value):
    return intcomma(value or 0)


def build_payment_stat_card(
    *,
    month_total=0,
    today_total=0,
    today_count=0,
    pending_count=0,
    pending_amount=0,
):
    return {
        "label": "Encaissements du mois",
        "value": _money(month_total),
        "unit": "FCFA",
        "icon": "circle-dollar-sign",
        "tone": "success",
        "description": (
            f"Aujourd'hui : {_money(today_total)} FCFA ({intcomma(today_count or 0)} paiement(s)) ; "
            f"{intcomma(pending_count or 0)} en attente pour {_money(pending_amount)} FCFA."
        ),
    }


def build_cash_stat_card(*, balance=0, cash_in_month=0, cash_out_month=0):
    balance = balance or 0
    cash_in_month = cash_in_month or 0
    cash_out_month = cash_out_month or 0
    net_month = (cash_in_month or 0) - (cash_out_month or 0)
    return {
        "label": "Caisse disponible",
        "value": _money(balance),
        "unit": "FCFA",
        "icon": "vault",
        "tone": "info" if balance >= 0 else "danger",
        "description": (
            f"Mois : +{_money(cash_in_month)} / -{_money(cash_out_month)} FCFA ; "
            f"net {_money(net_month)} FCFA."
        ),
    }


def _overview_stat_cards(context):
    intelligence = context.get("manager_intelligence") or {}
    cash_stats = context.get("cash_stats") or {}
    return [
        {
            "label": "Etudiants",
            "value": intcomma(context.get("total_students") or 0),
            "icon": "users",
            "tone": "primary",
            "description": "Inscriptions actives de l'annexe",
        },
        build_payment_stat_card(
            month_total=context.get("total_month"),
            today_total=context.get("total_today"),
            today_count=context.get("validated_today_count"),
            pending_count=context.get("pending_payments"),
            pending_amount=context.get("pending_payments_amount"),
        ),
        {
            "label": "Alertes actives",
            "value": intcomma(len(intelligence.get("alerts") or [])),
            "icon": "triangle-alert",
            "tone": "warning" if intelligence.get("alerts") else "success",
            "description": "Elements critiques a traiter",
        },
        build_cash_stat_card(
            balance=cash_stats.get("available_balance"),
            cash_in_month=cash_stats.get("in_month"),
            cash_out_month=cash_stats.get("out_month"),
        ),
    ]


def _payment_stat_cards(context):
    stats = context.get("payment_stats") or {}
    return [
        {
            "label": "Montant encaissé",
            "value": _money(stats.get("total_amount")),
            "unit": "FCFA",
            "icon": "circle-dollar-sign",
            "tone": "success",
            "description": f"{intcomma(stats.get('validated') or 0)} paiement(s) validé(s)",
        },
        {
            "label": "Aujourd'hui",
            "value": _money(context.get("total_today")),
            "unit": "FCFA",
            "icon": "calendar-check",
            "tone": "primary",
            "description": f"{intcomma(context.get('validated_today_count') or 0)} paiement(s) validé(s)",
        },
        {
            "label": "À contrôler",
            "value": intcomma(stats.get("pending") or 0),
            "icon": "clock-3",
            "tone": "warning" if stats.get("pending") else "neutral",
            "description": "Paiements en attente de décision",
        },
        {
            "label": "Sessions espèces",
            "value": intcomma(context.get("active_cash_sessions_count") or 0),
            "icon": "badge-dollar-sign",
            "tone": "info",
            "description": "Sessions actuellement ouvertes",
        },
    ]


def _choice_options(choices, selected, *, empty_label):
    return [
        {"value": "", "label": empty_label, "selected": not selected},
        *[
            {"value": value, "label": label, "selected": value == selected}
            for value, label in choices
        ],
    ]


def _payment_filters(context, *, dashboard_url):
    pay_status = context.get("pay_status") or ""
    pay_method = context.get("pay_method") or ""
    pay_date = context.get("pay_date") or ""
    pay_search = context.get("pay_search") or ""
    period_choices = (
        ("today", "Aujourd'hui"),
        ("week", "Cette semaine"),
        ("month", "Ce mois"),
    )
    active_filters = []
    if pay_status:
        active_filters.append(dict(Payment.STATUS_CHOICES).get(pay_status, pay_status))
    if pay_method:
        active_filters.append(dict(Payment.METHOD_CHOICES).get(pay_method, pay_method))
    if pay_date:
        active_filters.append(dict(period_choices).get(pay_date, pay_date))
    if pay_search:
        active_filters.append(f'Recherche : "{pay_search}"')
    return {
        "action": dashboard_url,
        "reset_url": f"{dashboard_url}?section=paiements",
        "hidden_fields": [{"name": "section", "value": "paiements"}],
        "active_filters": active_filters,
        "items": [
            {
                "name": "pay_status",
                "label": "Statut",
                "options": _choice_options(Payment.STATUS_CHOICES, pay_status, empty_label="Tous les statuts"),
            },
            {
                "name": "pay_method",
                "label": "Moyen",
                "options": _choice_options(Payment.METHOD_CHOICES, pay_method, empty_label="Tous les moyens"),
            },
            {
                "name": "pay_date",
                "label": "Période",
                "options": _choice_options(period_choices, pay_date, empty_label="Toutes les périodes"),
            },
            {
                "name": "pay_q",
                "label": "Référence ou étudiant",
                "value": pay_search,
                "placeholder": "Nom, reçu, référence…",
                "clearable": True,
            },
        ],
    }


def build_payment_table_row(payment, capabilities=()):
    """Normalize one already branch-scoped payment for the shared data table."""

    capabilities = frozenset(capabilities or ())
    status_tones = {
        Payment.STATUS_VALIDATED: "success",
        Payment.STATUS_PENDING: "warning",
        Payment.STATUS_CANCELLED: "danger",
    }
    row_target = f"#manager-payment-row-{payment.pk}"
    detail_action = {
        "label": "Voir",
        "title": "Consulter le paiement",
        "icon": "eye",
        "get_url": reverse("accounts:htmx_payment_detail", args=[payment.pk]),
        "target": "#manager-modal-content",
        "swap": "innerHTML",
        "open_overlay": "manager-modal",
    }
    actions = [detail_action]
    if payment.status == Payment.STATUS_PENDING:
        if "validate_payment" in capabilities:
            actions.append(
                {
                    "label": "Valider",
                    "icon": "check",
                    "tone": "success",
                    "post_url": reverse("accounts:htmx_payment_validate", args=[payment.pk]),
                    "target": row_target,
                    "swap": "outerHTML",
                    "csrf": True,
                    "confirm": "Valider ce paiement et créditer la caisse ?",
                }
            )
        if "cancel_payment" in capabilities:
            actions.append(
                {
                    "label": "Annuler",
                    "icon": "x",
                    "tone": "danger",
                    "post_url": reverse("accounts:htmx_payment_cancel", args=[payment.pk]),
                    "target": row_target,
                    "swap": "outerHTML",
                    "csrf": True,
                    "confirm": "Annuler ce paiement en attente ?",
                }
            )
    elif payment.status == Payment.STATUS_VALIDATED and "correct_payment" in capabilities:
        actions.append(
            {
                "label": "Corriger",
                "title": "Ouvrir la correction sécurisée",
                "icon": "pen",
                "tone": "warning",
                "get_url": reverse("accounts:htmx_payment_detail", args=[payment.pk]),
                "target": "#manager-modal-content",
                "swap": "innerHTML",
                "open_overlay": "manager-modal",
            }
        )
    if payment.receipt_pdf:
        actions.append(
            {
                "label": "Reçu",
                "icon": "file-text",
                "href": reverse("accounts:manager_payment_receipt_pdf", args=[payment.pk]),
                "external": True,
            }
        )

    paid_at = payment.paid_at or payment.created_at
    return {
        "id": f"manager-payment-row-{payment.pk}",
        "label": payment.reference,
        "cells": [
            {
                "value": payment.reference,
                "secondary": f"Reçu : {payment.receipt_number}" if payment.receipt_number else "",
                "strong": True,
            },
            {
                "value": payment.inscription.candidature.full_name,
                "secondary": payment.inscription.public_token,
                "href": reverse("inscriptions:public_detail", args=[payment.inscription.public_token]),
                "external": True,
            },
            {"value": f"{_money(payment.amount)} FCFA", "amount": True},
            {"value": payment.get_method_display()},
            {"value": payment.get_status_display(), "tone": status_tones.get(payment.status, "neutral")},
            {"value": formats.date_format(paid_at, "d/m/Y H:i") if paid_at else "—"},
        ],
        "actions": actions,
    }


def _payment_table(context, *, capabilities, dashboard_url):
    payments = context.get("payments")
    rows = [build_payment_table_row(payment, capabilities) for payment in payments.object_list]
    query = _manager_section_query(
        "paiements",
        context,
        pay_status=context.get("pay_status") or "",
        pay_method=context.get("pay_method") or "",
        pay_date=context.get("pay_date") or "",
        pay_q=context.get("pay_search") or "",
    )

    def page_url(number):
        return f"{dashboard_url}?{urlencode({**query, 'pay_page': number})}"

    return {
        "headers": ["Référence", "Étudiant", "Montant", "Moyen", "Statut", "Date"],
        "rows": rows,
        "result_count": payments.paginator.count,
        "page": payments.number,
        "page_count": payments.paginator.num_pages,
        "previous_url": page_url(payments.previous_page_number()) if payments.has_previous() else "",
        "next_url": page_url(payments.next_page_number()) if payments.has_next() else "",
    }


def _admission_stat_cards(context):
    stats = context.get("candidature_stats") or {}
    return [
        {"label": "Nouvelles", "value": intcomma(stats.get("submitted") or 0), "icon": "inbox", "tone": "primary", "description": "Dossiers soumis à examiner"},
        {"label": "En analyse", "value": intcomma(stats.get("under_review") or 0), "icon": "search-check", "tone": "warning", "description": "Décision administrative attendue"},
        {"label": "À compléter", "value": intcomma(stats.get("to_complete") or 0), "icon": "file-warning", "tone": "info", "description": "Compléments demandés au candidat"},
        {"label": "Acceptées", "value": intcomma(stats.get("accepted") or 0), "icon": "circle-check", "tone": "success", "description": "Dossiers prêts pour l'inscription"},
    ]


def _admission_filters(context, *, dashboard_url):
    status = context.get("cand_status") or ""
    search = context.get("cand_search") or ""
    activity_date = context.get("cand_activity_date") or ""
    status_choices = (("accepted", "Acceptée (toutes)"),) + tuple(
        choice for choice in Candidature.STATUS_CHOICES if choice[0] not in {"accepted", "accepted_with_reserve"}
    )
    status_choices = (("open", "À traiter"),) + status_choices
    active_filters = []
    if status:
        active_filters.append(dict(status_choices).get(status, status))
    if search:
        active_filters.append(f'Recherche : "{search}"')
    if activity_date:
        active_filters.append(f"Activité : {activity_date}")
    return {
        "action": dashboard_url,
        "reset_url": f"{dashboard_url}?section=candidatures",
        "hidden_fields": [{"name": "section", "value": "candidatures"}],
        "active_filters": active_filters,
        "items": [
            {"name": "cand_status", "label": "Statut", "options": _choice_options(status_choices, status, empty_label="Tous les statuts")},
            {"name": "cand_date", "label": "Date d'activité", "type": "date", "value": activity_date},
            {"name": "cand_q", "label": "Candidat", "value": search, "placeholder": "Nom ou adresse email…", "clearable": True},
        ],
    }


def build_candidature_table_row(candidature, capabilities=()):
    capabilities = frozenset(capabilities or ())
    status_tones = {
        "submitted": "primary",
        "under_review": "warning",
        "to_complete": "info",
        "accepted": "success",
        "accepted_with_reserve": "success",
        "rejected": "danger",
    }
    target = f"#candidature-{candidature.pk}"
    actions = [
        {
            "label": "Voir",
            "icon": "eye",
            "get_url": reverse("accounts:htmx_candidature_detail", args=[candidature.pk]),
            "target": "#manager-modal-content",
            "swap": "innerHTML",
            "open_overlay": "manager-modal",
        }
    ]
    if "manage_admissions" in capabilities and candidature.status in {"submitted", "under_review"}:
        if candidature.status == "submitted":
            actions.append(
                {
                    "label": "Analyser",
                    "icon": "search-check",
                    "post_url": reverse("accounts:htmx_candidature_under_review", args=[candidature.pk]),
                    "target": target,
                    "swap": "outerHTML",
                    "csrf": True,
                    "confirm": "Passer cette candidature en analyse ?",
                }
            )
        actions.extend(
            [
                {
                    "label": "Accepter",
                    "icon": "check",
                    "tone": "success",
                    "post_url": reverse("accounts:htmx_candidature_accept", args=[candidature.pk]),
                    "target": target,
                    "swap": "outerHTML",
                    "csrf": True,
                    "confirm": "Accepter cette candidature ?",
                },
                {
                    "label": "Compléter",
                    "icon": "file-warning",
                    "tone": "warning",
                    "post_url": reverse("accounts:htmx_candidature_to_complete", args=[candidature.pk]),
                    "target": target,
                    "swap": "outerHTML",
                    "csrf": True,
                    "confirm": "Demander des compléments pour cette candidature ?",
                },
                {
                    "label": "Refuser",
                    "icon": "x",
                    "tone": "danger",
                    "post_url": reverse("accounts:htmx_candidature_reject", args=[candidature.pk]),
                    "target": target,
                    "swap": "outerHTML",
                    "csrf": True,
                    "confirm": "Refuser cette candidature ?",
                },
            ]
        )
    elif "create_inscription" in capabilities and candidature.status in {"accepted", "accepted_with_reserve"}:
        try:
            has_inscription = candidature.inscription is not None
        except Inscription.DoesNotExist:
            has_inscription = False
        if not has_inscription:
            actions.append(
                {
                    "label": "Inscrire",
                    "icon": "id-card",
                    "tone": "success",
                    "get_url": reverse("accounts:htmx_inscription_positioning", args=[candidature.pk]),
                    "target": "#manager-modal-content",
                    "swap": "innerHTML",
                    "open_overlay": "manager-modal",
                }
            )
    if "delete_candidature" in capabilities and candidature.status == "rejected":
        actions.append(
            {
                "label": "Supprimer",
                "icon": "trash-2",
                "tone": "danger",
                "post_url": reverse("accounts:htmx_candidature_delete", args=[candidature.pk]),
                "target": target,
                "swap": "outerHTML",
                "csrf": True,
                "confirm": "Supprimer cette candidature rejetée ?",
            }
        )
    submitted_at = candidature.submitted_at
    return {
        "id": f"candidature-{candidature.pk}",
        "label": candidature.full_name,
        "cells": [
            {"value": candidature.full_name, "secondary": candidature.email, "strong": True},
            {"value": candidature.programme.title, "secondary": getattr(candidature.programme.cycle, "name", "")},
            {"value": candidature.get_status_display(), "tone": status_tones.get(candidature.status, "neutral")},
            {"value": formats.date_format(submitted_at, "d/m/Y H:i") if submitted_at else "—"},
        ],
        "actions": actions,
    }


def _admission_table(context, *, capabilities, dashboard_url):
    page = context.get("candidatures")
    rows = [build_candidature_table_row(item, capabilities) for item in page.object_list]
    query = _manager_section_query(
        "candidatures",
        context,
        cand_status=context.get("cand_status") or "",
        cand_date=context.get("cand_activity_date") or "",
        cand_q=context.get("cand_search") or "",
    )

    def page_url(number):
        return f"{dashboard_url}?{urlencode({**query, 'cand_page': number})}"

    return {
        "headers": ["Candidat", "Programme", "Statut", "Soumission"],
        "rows": rows,
        "result_count": page.paginator.count,
        "page": page.number,
        "page_count": page.paginator.num_pages,
        "previous_url": page_url(page.previous_page_number()) if page.has_previous() else "",
        "next_url": page_url(page.next_page_number()) if page.has_next() else "",
    }


def _inscription_stat_cards(context):
    stats = context.get("inscription_stats") or {}
    return [
        {"label": "Actives", "value": intcomma(stats.get("active") or 0), "icon": "circle-check", "tone": "success", "description": "Dossiers administrativement actifs"},
        {"label": "Premier paiement", "value": intcomma(stats.get("awaiting") or 0), "icon": "clock-3", "tone": "warning", "description": "Inscriptions en attente de règlement"},
        {"label": "Paiement partiel", "value": intcomma(stats.get("partial") or 0), "icon": "circle-dollar-sign", "tone": "info", "description": "Dossiers avec un solde restant"},
        {"label": "Créées", "value": intcomma(stats.get("created") or 0), "icon": "id-card", "tone": "primary", "description": "Dossiers à finaliser"},
    ]


def _inscription_filters(context, *, dashboard_url):
    status = context.get("ins_status") or ""
    search = context.get("ins_search") or ""
    activity_date = context.get("ins_activity_date") or ""
    status_choices = (("open", "À finaliser"),) + tuple(Inscription.STATUS_CHOICES)
    active_filters = []
    if status:
        active_filters.append(dict(Inscription.STATUS_CHOICES).get(status, status))
    if search:
        active_filters.append(f'Recherche : "{search}"')
    if activity_date:
        active_filters.append(f"Activité : {activity_date}")
    return {
        "action": dashboard_url,
        "reset_url": f"{dashboard_url}?section=inscriptions",
        "hidden_fields": [{"name": "section", "value": "inscriptions"}],
        "active_filters": active_filters,
        "items": [
            {"name": "ins_status", "label": "Statut", "options": _choice_options(status_choices, status, empty_label="Tous les statuts")},
            {"name": "ins_date", "label": "Date d'activité", "type": "date", "value": activity_date},
            {"name": "ins_q", "label": "Étudiant ou token", "value": search, "placeholder": "Nom, email ou token…", "clearable": True},
        ],
    }


def build_inscription_table_row(inscription, capabilities=()):
    status_tones = {
        Inscription.STATUS_ACTIVE: "success",
        Inscription.STATUS_AWAITING_PAYMENT: "warning",
        Inscription.STATUS_PARTIAL: "info",
        Inscription.STATUS_CANCELLED: "danger",
        Inscription.STATUS_EXPIRED: "danger",
    }
    actions = [
        {
            "label": "Voir",
            "icon": "eye",
            "get_url": reverse("accounts:htmx_inscription_detail", args=[inscription.pk]),
            "target": "#manager-modal-content",
            "swap": "innerHTML",
            "open_overlay": "manager-modal",
        },
        {
            "label": "Fiche",
            "icon": "file-text",
            "href": reverse("accounts:manager_inscription_sheet_pdf", args=[inscription.pk]),
            "external": True,
        },
    ]
    return {
        "id": f"inscription-row-{inscription.pk}",
        "label": inscription.candidature.full_name,
        "cells": [
            {"value": inscription.candidature.full_name, "secondary": inscription.candidature.email, "strong": True},
            {"value": inscription.public_token, "href": reverse("inscriptions:public_detail", args=[inscription.public_token]), "external": True},
            {"value": inscription.candidature.programme.title, "secondary": inscription.academic_level or ""},
            {"value": inscription.get_status_display(), "tone": status_tones.get(inscription.status, "neutral")},
            {"value": f"{_money(inscription.balance)} FCFA", "amount": True},
        ],
        "actions": actions,
    }


def _inscription_table(context, *, capabilities, dashboard_url):
    page = context.get("inscriptions")
    rows = [build_inscription_table_row(item, capabilities) for item in page.object_list]
    query = _manager_section_query(
        "inscriptions",
        context,
        ins_status=context.get("ins_status") or "",
        ins_date=context.get("ins_activity_date") or "",
        ins_q=context.get("ins_search") or "",
    )

    def page_url(number):
        return f"{dashboard_url}?{urlencode({**query, 'ins_page': number})}"

    return {
        "headers": ["Étudiant", "Token", "Programme", "Statut", "Solde"],
        "rows": rows,
        "result_count": page.paginator.count,
        "page": page.number,
        "page_count": page.paginator.num_pages,
        "previous_url": page_url(page.previous_page_number()) if page.has_previous() else "",
        "next_url": page_url(page.next_page_number()) if page.has_next() else "",
    }


def _cash_stat_cards(context):
    stats = context.get("cash_stats") or {}
    balance = stats.get("available_balance") or 0
    return [
        {"label": "Entrées du mois", "value": _money(stats.get("in_month")), "unit": "FCFA", "icon": "trending-up", "tone": "success", "description": "Mouvements créditeurs enregistrés"},
        {"label": "Sorties du mois", "value": _money(stats.get("out_month")), "unit": "FCFA", "icon": "trending-down", "tone": "danger", "description": "Mouvements débiteurs enregistrés"},
        {"label": "Caisse disponible", "value": _money(balance), "unit": "FCFA", "icon": "vault", "tone": "primary" if balance >= 0 else "danger", "description": "Solde réel après versements"},
        {"label": "Mouvements", "value": intcomma(stats.get("movements") or 0), "icon": "arrow-left-right", "tone": "info", "description": "Historique complet de l'annexe"},
    ]


def _cash_filters(context, *, dashboard_url):
    movement_type = context.get("cash_type") or ""
    source = context.get("cash_source") or ""
    search = context.get("cash_search") or ""
    activity_date = context.get("cash_activity_date") or ""
    active_filters = []
    if movement_type:
        active_filters.append(dict(BranchCashMovement.TYPE_CHOICES).get(movement_type, movement_type))
    if source:
        active_filters.append(dict(BranchCashMovement.SOURCE_CHOICES).get(source, source))
    if search:
        active_filters.append(f'Recherche : "{search}"')
    if activity_date:
        active_filters.append(f"Date : {activity_date}")
    return {
        "action": dashboard_url,
        "reset_url": f"{dashboard_url}?section=caisse",
        "hidden_fields": [{"name": "section", "value": "caisse"}],
        "active_filters": active_filters,
        "items": [
            {"name": "cash_type", "label": "Type", "options": _choice_options(BranchCashMovement.TYPE_CHOICES, movement_type, empty_label="Tous les types")},
            {"name": "cash_source", "label": "Source", "options": _choice_options(BranchCashMovement.SOURCE_CHOICES, source, empty_label="Toutes les sources")},
            {"name": "cash_date", "label": "Date", "type": "date", "value": activity_date},
            {"name": "cash_q", "label": "Mouvement", "value": search, "placeholder": "Libellé, référence ou note…", "clearable": True},
        ],
    }


def build_cash_movement_table_row(movement):
    sign = "+" if movement.movement_type == BranchCashMovement.TYPE_IN else "−"
    return {
        "id": f"manager-cash-movement-{movement.pk}",
        "label": movement.label,
        "cells": [
            {"value": formats.date_format(movement.movement_date, "d/m/Y")},
            {"value": movement.get_movement_type_display(), "tone": "success" if movement.movement_type == BranchCashMovement.TYPE_IN else "danger"},
            {"value": movement.get_source_display(), "secondary": movement.source_reference or ""},
            {"value": f"{sign}{_money(movement.amount)} FCFA", "amount": True},
            {"value": movement.label, "secondary": movement.reference or movement.receipt_number or "", "strong": True},
        ],
        "actions": [
            {
                "label": "Pièce",
                "icon": "file-text",
                "href": reverse("accounts:htmx_manager_cash_movement_receipt", args=[movement.pk]),
                "external": True,
            }
        ],
    }


def _cash_table(context, *, dashboard_url):
    page = context.get("cash_movements")
    rows = [build_cash_movement_table_row(item) for item in page.object_list]
    query = _manager_section_query(
        "caisse",
        context,
        cash_type=context.get("cash_type") or "",
        cash_source=context.get("cash_source") or "",
        cash_date=context.get("cash_activity_date") or "",
        cash_q=context.get("cash_search") or "",
    )

    def page_url(number):
        return f"{dashboard_url}?{urlencode({**query, 'cash_page': number})}"

    return {
        "headers": ["Date", "Type", "Source", "Montant", "Libellé"],
        "rows": rows,
        "result_count": page.paginator.count,
        "page": page.number,
        "page_count": page.paginator.num_pages,
        "previous_url": page_url(page.previous_page_number()) if page.has_previous() else "",
        "next_url": page_url(page.next_page_number()) if page.has_next() else "",
    }


def _expense_stat_cards(context):
    stats = context.get("expense_stats") or {}
    return [
        {"label": "Charges du mois", "value": _money(stats.get("month_amount")), "unit": "FCFA", "icon": "receipt", "tone": "danger", "description": "Hors dépenses rejetées"},
        {"label": "Montant en attente", "value": _money(stats.get("pending_amount")), "unit": "FCFA", "icon": "clock-3", "tone": "warning", "description": "Soumises ou approuvées"},
        {"label": "À approuver", "value": intcomma(stats.get("submitted") or 0), "icon": "file-check", "tone": "primary", "description": "Décision du gestionnaire requise"},
        {"label": "Payées", "value": intcomma(stats.get("paid") or 0), "icon": "circle-check", "tone": "success", "description": f"{_money(stats.get('paid_month_amount'))} FCFA ce mois"},
    ]


def _expense_filters(context, *, dashboard_url):
    status = context.get("expense_status") or ""
    category = context.get("expense_category") or ""
    search = context.get("expense_search") or ""
    active_filters = []
    if status:
        active_filters.append(dict(BranchExpense.STATUS_CHOICES).get(status, status))
    if category:
        active_filters.append(dict(BranchExpense.CATEGORY_CHOICES).get(category, category))
    if search:
        active_filters.append(f'Recherche : "{search}"')
    return {
        "action": dashboard_url,
        "reset_url": f"{dashboard_url}?section=depenses",
        "hidden_fields": [{"name": "section", "value": "depenses"}],
        "active_filters": active_filters,
        "items": [
            {"name": "expense_status", "label": "Statut", "options": _choice_options(BranchExpense.STATUS_CHOICES, status, empty_label="Tous les statuts")},
            {"name": "expense_category", "label": "Catégorie", "options": _choice_options(BranchExpense.CATEGORY_CHOICES, category, empty_label="Toutes les catégories")},
            {"name": "expense_q", "label": "Dépense", "value": search, "placeholder": "Titre, fournisseur ou référence…", "clearable": True},
        ],
    }


def build_expense_table_row(expense):
    status_tones = {
        BranchExpense.STATUS_DRAFT: "neutral",
        BranchExpense.STATUS_SUBMITTED: "warning",
        BranchExpense.STATUS_APPROVED: "primary",
        BranchExpense.STATUS_PAID: "success",
        BranchExpense.STATUS_REJECTED: "danger",
    }
    actions = []
    if expense.can_be_approved:
        actions.append(
            {
                "label": "Approuver",
                "icon": "check",
                "tone": "success",
                "post_url": reverse("accounts:htmx_manager_expense_approve", args=[expense.pk]),
                "csrf": True,
                "confirm": f"Approuver cette dépense de {_money(expense.amount)} FCFA ?",
            }
        )
    if expense.status not in {BranchExpense.STATUS_PAID, BranchExpense.STATUS_REJECTED}:
        actions.append(
            {
                "label": "Rejeter",
                "icon": "x",
                "tone": "danger",
                "post_url": reverse("accounts:htmx_manager_expense_reject", args=[expense.pk]),
                "csrf": True,
                "confirm": "Rejeter cette dépense ?",
            }
        )
    if expense.can_be_paid:
        actions.append(
            {
                "label": "Payer",
                "icon": "banknote",
                "tone": "success",
                "post_url": reverse("accounts:htmx_manager_expense_pay", args=[expense.pk]),
                "csrf": True,
                "confirm": f"Payer {_money(expense.amount)} FCFA et débiter la caisse ?",
            }
        )
    if expense.receipt and str(expense.receipt.name).lower().endswith(".pdf"):
        actions.append(
            {
                "label": "Justificatif",
                "icon": "file-text",
                "href": reverse("accounts:manager_expense_supporting_document_pdf", args=[expense.pk]),
                "external": True,
            }
        )
    return {
        "id": f"manager-expense-{expense.pk}",
        "label": expense.title,
        "cells": [
            {"value": expense.title, "secondary": expense.supplier or expense.reference or "", "strong": True},
            {"value": expense.get_category_display()},
            {"value": f"{_money(expense.amount)} FCFA", "amount": True},
            {"value": expense.get_status_display(), "tone": status_tones.get(expense.status, "neutral")},
            {"value": formats.date_format(expense.expense_date, "d/m/Y")},
        ],
        "actions": actions,
    }


def _expense_table(context, *, dashboard_url):
    page = context.get("expenses")
    rows = [build_expense_table_row(item) for item in page.object_list]
    query = _manager_section_query(
        "depenses",
        context,
        expense_status=context.get("expense_status") or "",
        expense_category=context.get("expense_category") or "",
        expense_q=context.get("expense_search") or "",
    )

    def page_url(number):
        return f"{dashboard_url}?{urlencode({**query, 'expense_page': number})}"

    return {
        "headers": ["Dépense", "Catégorie", "Montant", "Statut", "Date"],
        "rows": rows,
        "result_count": page.paginator.count,
        "page": page.number,
        "page_count": page.paginator.num_pages,
        "previous_url": page_url(page.previous_page_number()) if page.has_previous() else "",
        "next_url": page_url(page.next_page_number()) if page.has_next() else "",
    }


def _payroll_stat_cards(context):
    stats = context.get("payroll_stats") or {}
    return [
        {"label": "Personnel concerné", "value": intcomma(stats.get("employees") or 0), "icon": "users", "tone": "primary", "description": "Profils staff de l'annexe"},
        {"label": "Fiches préparées", "value": intcomma(stats.get("prepared") or 0), "icon": "file-check", "tone": "info", "description": "Préparation automatique ou synchronisée"},
        {"label": "Déjà payé", "value": _money(stats.get("paid_total")), "unit": "FCFA", "icon": "circle-check", "tone": "success", "description": f"{intcomma(stats.get('paid') or 0)} fiche(s) soldée(s)"},
        {"label": "Reste à payer", "value": _money(stats.get("remaining_total")), "unit": "FCFA", "icon": "wallet-cards", "tone": "warning" if stats.get("remaining_total") else "neutral", "description": f"Net prévu : {_money(stats.get('due_total'))} FCFA"},
    ]


def _payroll_filters(context, *, dashboard_url):
    status = context.get("salary_status") or ""
    search = context.get("salary_search") or ""
    month = context.get("salary_month_value") or ""
    status_choices = tuple(PayrollEntry.STATUS_CHOICES) + (
        ("payable", "À payer (disponible ou partiel)"),
        ("missing", "Sans fiche"),
    )
    active_filters = []
    if status:
        active_filters.append(dict(status_choices).get(status, status))
    if month:
        active_filters.append(f"Mois : {month}")
    if search:
        active_filters.append(f'Recherche : "{search}"')
    return {
        "action": dashboard_url,
        "reset_url": f"{dashboard_url}?section=salaires",
        "hidden_fields": [{"name": "section", "value": "salaires"}],
        "active_filters": active_filters,
        "items": [
            {"name": "salary_month", "label": "Mois de paie", "type": "month", "value": month},
            {"name": "salary_status", "label": "Statut", "options": _choice_options(status_choices, status, empty_label="Tous les statuts")},
            {"name": "salary_q", "label": "Employé", "value": search, "placeholder": "Nom, code ou fonction…", "clearable": True},
        ],
    }


def build_payroll_table_row(profile, *, salary_month_value):
    entry = getattr(profile, "current_payroll", None)
    status_tones = {
        PayrollEntry.STATUS_DRAFT: "neutral",
        PayrollEntry.STATUS_READY: "primary",
        PayrollEntry.STATUS_PARTIAL: "warning",
        PayrollEntry.STATUS_PAID: "success",
    }
    detail_url = reverse("accounts:htmx_manager_salary_detail", args=[profile.user_id])
    if salary_month_value:
        detail_url = f"{detail_url}?{urlencode({'salary_month': salary_month_value})}"
    action_label = (
        "Contrôler" if not entry or entry.status == PayrollEntry.STATUS_DRAFT
        else "Payer" if entry.status in {PayrollEntry.STATUS_READY, PayrollEntry.STATUS_PARTIAL}
        else "Voir"
    )
    actions = [
        {
            "label": action_label,
            "icon": "banknote" if action_label == "Payer" else "scan-search" if action_label == "Contrôler" else "eye",
            "get_url": detail_url,
            "target": "#manager-modal-content",
            "swap": "innerHTML",
            "open_overlay": "manager-modal",
        }
    ]
    if entry:
        actions.append(
            {
                "label": "Fiche de paie",
                "icon": "file-text",
                "href": reverse("accounts:manager_payroll_sheet_pdf", args=[entry.pk]),
                "external": True,
            }
        )
    base_salary = entry.base_salary if entry else profile.salary_base
    return {
        "id": f"manager-payroll-profile-{profile.user_id}",
        "label": profile.user.get_full_name() or profile.user.username,
        "cells": [
            {"value": profile.user.get_full_name() or profile.user.username, "secondary": profile.get_position_display() or profile.position or profile.employee_code or "", "strong": True},
            {"value": f"{_money(base_salary)} FCFA", "amount": True},
            {"value": f"{_money(entry.net_salary)} FCFA" if entry else "—", "amount": bool(entry)},
            {"value": f"{_money(entry.paid_amount)} FCFA" if entry else "—", "amount": bool(entry)},
            {"value": f"{_money(entry.remaining_salary)} FCFA" if entry else "—", "amount": bool(entry), "tone": "warning" if entry and entry.remaining_salary else "neutral"},
            {"value": entry.get_status_display() if entry else "À vérifier", "tone": status_tones.get(entry.status, "neutral") if entry else "neutral"},
        ],
        "actions": actions,
    }


def _payroll_table(context, *, dashboard_url):
    page = context.get("payroll_entries")
    month = context.get("salary_month_value") or ""
    rows = [build_payroll_table_row(item, salary_month_value=month) for item in page.object_list]
    query = _manager_section_query(
        "salaires",
        context,
        salary_month=month,
        salary_status=context.get("salary_status") or "",
        salary_q=context.get("salary_search") or "",
    )

    def page_url(number):
        return f"{dashboard_url}?{urlencode({**query, 'salary_page': number})}"

    return {
        "headers": ["Employé", "Salaire officiel", "Net", "Payé", "Reste", "Statut"],
        "rows": rows,
        "result_count": page.paginator.count,
        "page": page.number,
        "page_count": page.paginator.num_pages,
        "previous_url": page_url(page.previous_page_number()) if page.has_previous() else "",
        "next_url": page_url(page.next_page_number()) if page.has_next() else "",
    }


def _report_stat_cards(context):
    summary = context.get("report_summary") or {}
    closure_possible = bool(context.get("report_closure_possible"))
    return [
        {"label": "Recettes totales", "value": _money(summary.get("total_revenue")), "unit": "FCFA", "icon": "trending-up", "tone": "success", "description": "Encaissements consolidés de la période"},
        {"label": "Dépenses totales", "value": _money(summary.get("total_expenses")), "unit": "FCFA", "icon": "trending-down", "tone": "danger", "description": "Charges consolidées de la période"},
        {"label": "Résultat net", "value": _money(summary.get("net_result")), "unit": "FCFA", "icon": "scale", "tone": "primary" if (summary.get("net_result") or 0) >= 0 else "danger", "description": "Recettes moins dépenses"},
        {"label": "Versement bancaire recommandé", "value": _money(context.get("report_recommended_bank_transfer")), "unit": "FCFA", "icon": "landmark", "tone": "info", "description": "Montant disponible après réserve de caisse"},
        {"label": "Caisse réelle", "value": _money(summary.get("available_cash_balance")), "unit": "FCFA", "icon": "vault", "tone": "success" if closure_possible else "warning", "description": "Clôture possible" if closure_possible else "Contrôles requis avant clôture"},
    ]


def _report_filters(context, *, dashboard_url):
    period = context.get("report_period") or {}
    preset = period.get("preset") or "month"
    cash_type = context.get("report_cash_type") or ""
    cash_source = context.get("report_cash_source") or ""
    active_filters = [period.get("label") or "Période courante"]
    if cash_type:
        active_filters.append(dict(context.get("report_type_options") or ()).get(cash_type, cash_type))
    if cash_source:
        active_filters.append(dict(context.get("report_source_options") or ()).get(cash_source, cash_source))
    return {
        "action": dashboard_url,
        "reset_url": f"{dashboard_url}?section=rapport",
        "hidden_fields": [{"name": "section", "value": "rapport"}],
        "active_filters": active_filters,
        "items": [
            {
                "name": "report_period",
                "label": "Période",
                "options": _choice_options(
                    (
                        ("month", "Mois"),
                        ("today", "Aujourd'hui"),
                        ("yesterday", "Hier"),
                        ("week", "Semaine"),
                        ("two_weeks", "Deux semaines"),
                        ("three_months", "Trois mois"),
                        ("semester", "Semestre"),
                        ("year", "Année"),
                        ("custom", "Personnalisée"),
                    ),
                    preset,
                    empty_label="Période",
                ),
            },
            {"name": "report_start", "label": "Du", "type": "date", "value": formats.date_format(period.get("start"), "Y-m-d") if period.get("start") else ""},
            {"name": "report_end", "label": "Au", "type": "date", "value": formats.date_format(period.get("end"), "Y-m-d") if period.get("end") else ""},
            {"name": "cash_type", "label": "Flux", "options": _choice_options(context.get("report_type_options") or (), cash_type, empty_label="Tous les flux")},
            {"name": "cash_source", "label": "Source", "options": _choice_options(context.get("report_source_options") or (), cash_source, empty_label="Toutes les sources")},
        ],
    }


def _report_rows_table(context):
    rows = [
        {
            "id": f"manager-report-summary-{index}",
            "label": item.get("label"),
            "cells": [
                {"value": item.get("label"), "strong": True},
                {"value": f"{_money(item.get('amount'))} FCFA", "amount": True},
            ],
        }
        for index, item in enumerate(context.get("report_rows") or (), start=1)
    ]
    return {"headers": ["Indicateur", "Montant"], "rows": rows, "result_count": len(rows), "page": 1, "page_count": 1}


def _report_movement_table(context):
    movements = context.get("report_movements") or ()
    rows = []
    for movement in movements:
        rows.append(
            {
                "id": f"manager-report-movement-{movement.pk}",
                "label": movement.label,
                "cells": [
                    {"value": formats.date_format(movement.movement_date, "d/m/Y")},
                    {"value": movement.label, "secondary": movement.reference or "", "strong": True},
                    {"value": movement.get_source_display()},
                    {"value": movement.get_movement_type_display(), "tone": "success" if movement.movement_type == BranchCashMovement.TYPE_IN else "danger"},
                    {"value": f"{_money(movement.amount)} FCFA", "amount": True},
                ],
            }
        )
    return {
        "headers": ["Date", "Libellé", "Source", "Flux", "Montant"],
        "rows": rows,
        "result_count": context.get("report_movements_count") or len(rows),
        "page": 1,
        "page_count": 1,
    }


def _annual_revenue_table(context):
    rows = []
    for item in context.get("annual_revenue_rows") or ():
        year = item.get("paid_at__year")
        if year is None:
            continue
        rows.append(
            {
                "id": f"manager-annual-revenue-{year}",
                "label": str(year),
                "cells": [
                    {"value": year, "strong": True},
                    {"value": f"{_money(item.get('total_amount'))} FCFA", "amount": True},
                    {"value": item.get("payments_count") or 0},
                ],
            }
        )
    return {
        "headers": ["Année", "Encaissements", "Paiements validés"],
        "rows": rows,
        "result_count": len(rows),
        "page": 1,
        "page_count": 1,
    }


def _report_presentation(context, *, dashboard_url):
    period = context.get("report_period") or {}
    export_query = {
        "section": "rapport",
        "report_period": period.get("preset") or "month",
        "report_start": formats.date_format(period.get("start"), "Y-m-d") if period.get("start") else "",
        "report_end": formats.date_format(period.get("end"), "Y-m-d") if period.get("end") else "",
        "cash_type": context.get("report_cash_type") or "",
        "cash_source": context.get("report_cash_source") or "",
    }
    source_rows = context.get("report_source_rows") or ()
    return {
        "filters": _report_filters(context, dashboard_url=dashboard_url),
        "summary_table": _report_rows_table(context),
        "movement_table": _report_movement_table(context),
        "annual_revenue_table": _annual_revenue_table(context),
        "chart_labels": [item.get("label") for item in source_rows],
        "chart_datasets": [
            {"label": "Entrées", "data": [item.get("in_total") or 0 for item in source_rows], "backgroundColor": "#16a34a"},
            {"label": "Sorties", "data": [item.get("out_total") or 0 for item in source_rows], "backgroundColor": "#ef4444"},
        ],
        "xlsx_url": f"{reverse('accounts:manager_export_report_xlsx')}?{urlencode(export_query)}",
        "pdf_url": f"{reverse('accounts:manager_export_report_pdf')}?{urlencode(export_query)}",
    }


def _honorarium_stat_cards(context):
    stats = context.get("honorarium_stats") or {}
    return [
        {"label": "Enseignants", "value": intcomma(stats.get("teachers") or 0), "icon": "graduation-cap", "tone": "primary", "description": "Enseignants rattachés à l'annexe"},
        {"label": "Fiches préparées", "value": intcomma(stats.get("prepared") or 0), "icon": "file-check", "tone": "info", "description": "Heures validées × tarif officiel"},
        {"label": "Honoraires payés", "value": _money(stats.get("paid_total")), "unit": "FCFA", "icon": "circle-check", "tone": "success", "description": f"{intcomma(stats.get('paid') or 0)} fiche(s) soldée(s)"},
        {"label": "Reste à payer", "value": _money(stats.get("remaining_total")), "unit": "FCFA", "icon": "wallet-cards", "tone": "warning" if stats.get("remaining_total") else "neutral", "description": "Séparé des salaires du personnel"},
    ]


def _honorarium_filters(context, *, dashboard_url):
    status = context.get("honorarium_status") or ""
    search = context.get("honorarium_search") or ""
    month = context.get("salary_month_value") or ""
    status_choices = tuple(TeacherHonorariumEntry.STATUS_CHOICES) + (
        ("payable", "À payer (disponible ou partiel)"),
        ("missing", "Sans fiche"),
    )
    active_filters = []
    if status:
        active_filters.append(dict(status_choices).get(status, status))
    if month:
        active_filters.append(f"Mois : {month}")
    if search:
        active_filters.append(f'Recherche : "{search}"')
    return {
        "action": dashboard_url,
        "reset_url": f"{dashboard_url}?section=honoraires",
        "hidden_fields": [{"name": "section", "value": "honoraires"}],
        "active_filters": active_filters,
        "items": [
            {"name": "salary_month", "label": "Mois", "type": "month", "value": month},
            {"name": "honorarium_status", "label": "Statut", "options": _choice_options(status_choices, status, empty_label="Tous les statuts")},
            {"name": "honorarium_q", "label": "Enseignant", "value": search, "placeholder": "Nom, code ou fonction…", "clearable": True},
        ],
    }


def build_honorarium_table_row(profile, *, salary_month_value):
    entry = getattr(profile, "current_honorarium", None)
    status_tones = {
        TeacherHonorariumEntry.STATUS_DRAFT: "neutral",
        TeacherHonorariumEntry.STATUS_READY: "primary",
        TeacherHonorariumEntry.STATUS_PARTIAL: "warning",
        TeacherHonorariumEntry.STATUS_PAID: "success",
    }
    detail_url = reverse("accounts:htmx_manager_teacher_honorarium_detail", args=[profile.user_id])
    if salary_month_value:
        detail_url = f"{detail_url}?{urlencode({'salary_month': salary_month_value})}"
    action_label = (
        "Contrôler" if not entry or entry.status == TeacherHonorariumEntry.STATUS_DRAFT
        else "Payer" if entry.status in {TeacherHonorariumEntry.STATUS_READY, TeacherHonorariumEntry.STATUS_PARTIAL}
        else "Voir"
    )
    actions = [{"label": action_label, "icon": "banknote" if action_label == "Payer" else "scan-search" if action_label == "Contrôler" else "eye", "get_url": detail_url, "target": "#manager-modal-content", "swap": "innerHTML", "open_overlay": "manager-modal"}]
    if entry:
        actions.append({"label": "Bordereau", "icon": "file-text", "href": reverse("accounts:manager_honorarium_statement_pdf", args=[entry.pk]), "external": True})
    return {
        "id": f"manager-honorarium-profile-{profile.user_id}",
        "label": profile.user.get_full_name() or profile.user.username,
        "cells": [
            {"value": profile.user.get_full_name() or profile.user.username, "secondary": profile.employee_code or "Enseignant", "strong": True},
            {"value": f"{_money(entry.hourly_rate if entry else profile.teacher_hourly_rate)} FCFA", "amount": True},
            {"value": f"{entry.validated_hours} h" if entry else "—"},
            {"value": f"{_money(entry.net_amount)} FCFA" if entry else "—", "amount": bool(entry)},
            {"value": f"{_money(entry.paid_amount)} FCFA" if entry else "—", "amount": bool(entry)},
            {"value": f"{_money(entry.remaining_amount)} FCFA" if entry else "—", "amount": bool(entry), "tone": "warning" if entry and entry.remaining_amount else "neutral"},
            {"value": entry.get_status_display() if entry else "À vérifier", "tone": status_tones.get(entry.status, "neutral") if entry else "neutral"},
        ],
        "actions": actions,
    }


def _honorarium_table(context, *, dashboard_url):
    page = context.get("honorarium_entries")
    month = context.get("salary_month_value") or ""
    rows = [build_honorarium_table_row(item, salary_month_value=month) for item in page.object_list]
    query = _manager_section_query(
        "honoraires",
        context,
        salary_month=month,
        honorarium_status=context.get("honorarium_status") or "",
        honorarium_q=context.get("honorarium_search") or "",
    )

    def page_url(number):
        return f"{dashboard_url}?{urlencode({**query, 'honorarium_page': number})}"

    return {
        "headers": ["Enseignant", "Taux", "Heures", "Net", "Payé", "Reste", "Statut"],
        "rows": rows,
        "result_count": page.paginator.count,
        "page": page.number,
        "page_count": page.paginator.num_pages,
        "previous_url": page_url(page.previous_page_number()) if page.has_previous() else "",
        "next_url": page_url(page.next_page_number()) if page.has_next() else "",
    }


def _closure_tables(context, *, subcontent_url):
    closure_tones = {
        BranchMonthlyClosure.STATUS_DRAFT: "neutral",
        BranchMonthlyClosure.STATUS_VALIDATED: "primary",
        BranchMonthlyClosure.STATUS_CLOSED: "success",
    }
    closures_page = context.get("monthly_closures")
    transfers_page = context.get("bank_transfers")
    closure_rows = []
    for closure in closures_page.object_list if closures_page else ():
        actions = []
        if closure.status == BranchMonthlyClosure.STATUS_DRAFT:
            actions.append({"label": "Valider", "icon": "check", "post_url": reverse("accounts:htmx_manager_monthly_closure_validate", args=[closure.pk]), "csrf": True, "confirm": f"Valider la clôture de {closure.period_month:%m/%Y} ?"})
        elif closure.status == BranchMonthlyClosure.STATUS_VALIDATED:
            actions.append({"label": "Clôturer", "icon": "lock", "post_url": reverse("accounts:htmx_manager_monthly_closure_close", args=[closure.pk]), "csrf": True, "confirm": f"Clôturer définitivement {closure.period_month:%m/%Y} ?", "tone": "success"})
        transfer = getattr(closure, "bank_transfer", None)
        closure_rows.append(
            {
                "id": f"manager-closure-{closure.pk}",
                "label": f"Clôture {closure.period_month:%m/%Y}",
                "cells": [
                    {"value": formats.date_format(closure.period_month, "m/Y"), "strong": True},
                    {"value": closure.get_status_display(), "tone": closure_tones.get(closure.status, "neutral")},
                    {"value": f"{_money(closure.result_amount)} FCFA", "amount": True},
                    {"value": f"{_money(transfer.amount)} FCFA" if transfer else "—", "amount": bool(transfer)},
                    {"value": transfer.reference if transfer else "Aucun versement"},
                ],
                "actions": actions,
            }
        )
    transfer_rows = []
    for transfer in transfers_page.object_list if transfers_page else ():
        actions = []
        if transfer.proof and transfer.proof.name.lower().endswith(".pdf"):
            actions.append({"label": "Bordereau", "icon": "file-text", "href": reverse("accounts:manager_bank_transfer_slip_pdf", args=[transfer.pk]), "external": True})
        transfer_rows.append(
            {
                "id": f"manager-bank-transfer-{transfer.pk}",
                "label": transfer.reference,
                "cells": [
                    {"value": transfer.bank_name, "strong": True},
                    {"value": transfer.reference},
                    {"value": formats.date_format(transfer.transfer_date, "d/m/Y")},
                    {"value": f"{_money(transfer.amount)} FCFA", "amount": True},
                    {"value": transfer.comment or "—"},
                ],
                "actions": actions,
            }
        )
    def page_url(param_name, number):
        query = {"section": "cloture", "view": "archives", param_name: number}
        if closures_page:
            query["closure_page"] = closures_page.number
        if transfers_page:
            query["transfer_page"] = transfers_page.number
        query[param_name] = number
        return f"{subcontent_url}?{urlencode(query)}"

    def table_payload(page, rows, headers, param_name):
        return {
            "headers": headers,
            "rows": rows,
            "result_count": page.paginator.count if page else 0,
            "page": page.number if page else 1,
            "page_count": page.paginator.num_pages if page else 1,
            "previous_url": page_url(param_name, page.previous_page_number()) if page and page.has_previous() else "",
            "next_url": page_url(param_name, page.next_page_number()) if page and page.has_next() else "",
        }
    return {
        "closures": table_payload(closures_page, closure_rows, ["Periode", "Etat", "Resultat", "Versement", "Reference"], "closure_page"),
        "transfers": table_payload(transfers_page, transfer_rows, ["Banque", "Reference", "Date", "Montant", "Commentaire"], "transfer_page"),
    }
def _donation_stat_cards(context):
    stats = context.get("donation_stats") or {}
    return [
        {"label": "Dons enregistrés", "value": intcomma(stats.get("count") or 0), "icon": "hand-heart", "tone": "primary", "description": "Historique de l'annexe"},
        {"label": "Montant total", "value": _money(stats.get("total")), "unit": "FCFA", "icon": "landmark", "tone": "success", "description": "Appuis financiers cumulés"},
        {"label": "Ce mois", "value": _money(stats.get("this_month")), "unit": "FCFA", "icon": "calendar-days", "tone": "info", "description": "Dons reçus sur la période"},
    ]


def _donation_table(context, *, dashboard_url, subcontent_url):
    page = context.get("donations")
    rows = []
    for donation in page.object_list if page else ():
        actions = [{"label": "Reçu", "icon": "file-text", "href": reverse("accounts:manager_donation_receipt_pdf", args=[donation.pk]), "external": True}]
        rows.append(
            {
                "id": f"manager-donation-{donation.pk}",
                "label": donation.donor_name,
                "cells": [
                    {"value": donation.donor_name, "secondary": donation.receipt_number or "Reçu généré automatiquement", "strong": True},
                    {"value": f"{_money(donation.amount)} FCFA", "amount": True},
                    {"value": donation.get_motif_display()},
                    {"value": donation.get_payment_method_display()},
                    {"value": formats.date_format(donation.date, "d/m/Y")},
                ],
                "actions": actions,
            }
        )
    def page_url(number):
        return f"{subcontent_url}?{urlencode({'section': 'dons', 'view': 'history', 'donation_page': number})}"

    return {
        "headers": ["Donateur", "Montant", "Motif", "Paiement", "Date"],
        "rows": rows,
        "result_count": page.paginator.count if page else 0,
        "page": page.number if page else 1,
        "page_count": page.paginator.num_pages if page else 1,
        "previous_url": page_url(page.previous_page_number()) if page and page.has_previous() else "",
        "next_url": page_url(page.next_page_number()) if page and page.has_next() else "",
    }


def _shop_stat_cards(context):
    stats = context.get("shop_stats") or {}
    return [
        {"label": "Ventes du jour", "value": _money(stats.get("today_sales")), "unit": "FCFA", "icon": "trending-up", "tone": "success", "description": "Recettes boutique encaissées aujourd’hui"},
        {"label": "Tickets du jour", "value": intcomma(stats.get("today_sales_count") or 0), "icon": "receipt-text", "tone": "primary", "description": "Ventes réellement validées"},
        {"label": "À encaisser", "value": intcomma(stats.get("pending_orders") or 0), "icon": "badge-dollar-sign", "tone": "warning", "description": "Commandes en attente de règlement"},
        {"label": "À préparer", "value": intcomma(stats.get("paid_not_delivered") or 0), "icon": "package-check", "tone": "primary", "description": "Ventes encaissées à préparer"},
        {"label": "À remettre", "value": intcomma(stats.get("ready_orders") or 0), "icon": "package-open", "tone": "info", "description": "Commandes prêtes pour le client"},
    ]


def _shop_order_table(context, *, orders=None):
    status_tones = {
        "draft": "neutral",
        "pending_payment": "warning",
        "paid": "primary",
        "ready": "info",
        "delivered": "success",
        "cancelled": "danger",
    }
    current_view = context.get("manager_subview") or "sell"
    rows = []
    for order in (orders if orders is not None else context.get("shop_orders") or ()):
        actions = []
        for payment in order.payments.all():
            if payment.status == "pending":
                actions.append(
                    {
                        "label": "Valider paiement",
                        "icon": "check",
                        "post_url": f"{reverse('shop:manager_payment_validate', args=[payment.pk])}?view={current_view}",
                        "target": "#manager-shop-module",
                        "swap": "outerHTML",
                        "csrf": True,
                        "confirm": f"Valider le paiement de la commande {order.reference} ?",
                        "tone": "success",
                    }
                )
            if payment.receipt_pdf:
                actions.append({"label": "Reçu", "icon": "file-text", "href": reverse("shop:payment_receipt", args=[payment.pk]), "external": True})
        if order.status == "paid":
            actions.append(
                {
                    "label": "Préparer",
                    "icon": "package-check",
                    "post_url": f"{reverse('shop:manager_order_mark_ready', args=[order.pk])}?view={current_view}",
                    "target": "#manager-shop-module",
                    "swap": "outerHTML",
                    "csrf": True,
                    "confirm": f"Marquer la commande {order.reference} comme prête ?",
                }
            )
        if order.status == "ready":
            actions.append(
                {
                    "label": "Remettre",
                    "icon": "package-open",
                    "post_url": f"{reverse('shop:manager_order_deliver', args=[order.pk])}?view={current_view}",
                    "target": "#manager-shop-module",
                    "swap": "outerHTML",
                    "csrf": True,
                    "confirm": f"Confirmer la remise de la commande {order.reference} ?",
                    "tone": "success",
                }
            )
        item_summary = ", ".join(f"{item.quantity} × {item.product.name}" for item in order.items.all()) or "Aucun article"
        rows.append(
            {
                "id": f"manager-shop-order-{order.pk}",
                "label": order.reference,
                "cells": [
                    {"value": order.reference, "secondary": formats.date_format(order.created_at, "d/m/Y H:i"), "strong": True},
                    {"value": order.buyer_display, "secondary": order.get_buyer_type_display()},
                    {"value": item_summary},
                    {"value": f"{_money(order.total_amount)} FCFA", "amount": True},
                    {"value": order.get_status_display(), "tone": status_tones.get(order.status, "neutral")},
                ],
                "actions": actions,
            }
        )
    return {"headers": ["Commande", "Acheteur", "Articles", "Total", "État"], "rows": rows, "result_count": len(rows), "page": 1, "page_count": 1}


def _shop_order_queues(context):
    queues = context.get("shop_order_queues") or {}
    return {
        "pending": _shop_order_table(context, orders=queues.get("pending") or ()),
        "paid": _shop_order_table(context, orders=queues.get("paid") or ()),
        "ready": _shop_order_table(context, orders=queues.get("ready") or ()),
    }


def _shop_journal_tables(context):
    payment_rows = []
    for payment in context.get("shop_recent_payments") or ():
        payment_rows.append(
            {
                "id": f"shop-payment-journal-{payment.pk}",
                "label": payment.reference or str(payment.pk),
                "cells": [
                    {"value": payment.reference or "Paiement boutique", "secondary": formats.date_format(payment.paid_at, "d/m/Y H:i"), "strong": True},
                    {"value": payment.order.buyer_display, "secondary": payment.order.reference},
                    {"value": payment.get_method_display()},
                    {"value": f"{_money(payment.amount)} FCFA", "amount": True},
                    {"value": payment.get_status_display(), "tone": "success" if payment.status == "validated" else "warning" if payment.status == "pending" else "danger"},
                ],
                "actions": ([{"label": "Reçu", "icon": "file-text", "href": reverse("shop:payment_receipt", args=[payment.pk]), "external": True}] if payment.receipt_pdf else []),
            }
        )
    movement_rows = []
    tone_by_type = {"in": "success", "out": "warning", "adjustment": "info"}
    for movement in context.get("shop_recent_stock_movements") or ():
        movement_rows.append(
            {
                "id": f"shop-stock-journal-{movement.pk}",
                "label": movement.reference or str(movement.pk),
                "cells": [
                    {"value": formats.date_format(movement.created_at, "d/m/Y H:i"), "secondary": movement.reference or "Sans référence", "strong": True},
                    {"value": movement.product.name},
                    {"value": movement.get_movement_type_display(), "tone": tone_by_type.get(movement.movement_type, "neutral")},
                    {"value": f"{movement.quantity:+d}", "amount": True},
                    {"value": movement.notes or "—", "secondary": movement.created_by.get_full_name() if movement.created_by_id else "Système"},
                ],
            }
        )
    return {
        "payments": {"headers": ["Référence", "Client", "Paiement", "Montant", "État"], "rows": payment_rows, "result_count": len(payment_rows), "page": 1, "page_count": 1},
        "stock": {"headers": ["Date", "Article", "Mouvement", "Quantité", "Motif / auteur"], "rows": movement_rows, "result_count": len(movement_rows), "page": 1, "page_count": 1},
    }


def _shop_journal_filters(context, *, action_url):
    query = context.get("shop_journal_query") or ""
    journal_date = context.get("shop_journal_date") or ""
    active_filters = []
    if query:
        active_filters.append(f'Recherche : "{query}"')
    if journal_date:
        active_filters.append(f"Date : {journal_date}")
    return {
        "action": action_url,
        "reset_url": f"{action_url}?{urlencode({'section': 'boutique', 'view': 'journal'})}",
        "hidden_fields": [
            {"name": "section", "value": "boutique"},
            {"name": "view", "value": "journal"},
        ],
        "active_filters": active_filters,
        "items": [
            {"name": "shop_date", "label": "Date", "type": "date", "value": journal_date},
            {"name": "shop_q", "label": "Référence, client ou article", "value": query, "placeholder": "Rechercher…", "clearable": True},
        ],
    }


def _shop_catalogue_table(context):
    rows = []
    for product in context.get("shop_catalogue_products") or ():
        stock = product.inventory_stock if hasattr(product, "inventory_stock") else product.current_stock
        low_stock = product.inventory_low if hasattr(product, "inventory_low") else product.is_low_stock
        action = "Archiver" if product.is_active else "Réactiver"
        rows.append(
            {
                "id": f"manager-shop-product-{product.pk}",
                "label": product.name,
                "cells": [
                    {"value": product.name, "secondary": product.get_category_display(), "strong": True},
                    {"value": f"{_money(product.unit_price)} FCFA", "amount": True},
                    {"value": str(stock), "secondary": f"Seuil : {product.low_stock_threshold}", "tone": "danger" if low_stock else "success"},
                    {"value": "Obligatoire" if product.is_required else "Libre", "tone": "primary" if product.is_required else "neutral"},
                    {"value": "Actif" if product.is_active else "Archivé", "tone": "success" if product.is_active else "neutral"},
                ],
                "actions": [{
                    "label": action,
                    "icon": "archive" if product.is_active else "rotate-ccw",
                    "post_url": reverse("shop:manager_product_delete", args=[product.pk]),
                    "target": "#manager-shop-module",
                    "swap": "outerHTML",
                    "csrf": True,
                    "confirm": f"{action} l'article {product.name} ?",
                    "tone": "warning" if product.is_active else "success",
                }],
            }
        )
    return {
        "headers": ["Article", "Prix unitaire", "Stock", "Usage", "Publication"],
        "rows": rows,
        "result_count": len(rows),
        "page": 1,
        "page_count": 1,
    }


def _shop_stock_filters(context, *, action_url):
    query = context.get("shop_stock_query") or ""
    state = context.get("shop_stock_state") or ""
    category = context.get("shop_stock_category") or ""
    active_filters = []
    if query:
        active_filters.append(f'Recherche : "{query}"')
    if state:
        active_filters.append(
            {
                "low": "Au seuil d'alerte",
                "available": "Stock disponible",
                "active": "Articles actifs",
                "archived": "Articles archivés",
            }.get(state, state)
        )
    if category:
        labels = {value: label for value, label in ShopProduct.CATEGORY_CHOICES}
        active_filters.append(f"Catégorie : {labels.get(category, category)}")
    return {
        "action": action_url,
        "reset_url": f"{action_url}?{urlencode({'section': 'boutique', 'view': 'stock'})}",
        "hidden_fields": [
            {"name": "section", "value": "boutique"},
            {"name": "view", "value": "stock"},
        ],
        "active_filters": active_filters,
        "items": [
            {"name": "shop_stock_q", "label": "Article", "value": query, "placeholder": "Rechercher…", "clearable": True},
            {"name": "shop_stock_category", "label": "Catégorie", "options": _choice_options(ShopProduct.CATEGORY_CHOICES, category, empty_label="Toutes les catégories")},
            {"name": "shop_stock_state", "label": "État du stock", "options": _choice_options((
                ("low", "Au seuil d’alerte"),
                ("available", "Disponible"),
                ("active", "Articles actifs"),
                ("archived", "Articles archivés"),
            ), state, empty_label="Tous les états")},
        ],
    }


def build_manager_dashboard_presentation(
    *,
    active_section,
    context,
    capabilities=(),
    dashboard_url="",
    workspace_url="",
    subcontent_url="",
    active_subview="overview",
):
    """Return the UI-only contract for one manager workspace section."""

    section = active_section if active_section in SECTION_PRESENTATION else "overview"
    subview = normalize_manager_subview(section, active_subview)
    page_header = dict(SECTION_PRESENTATION[section])
    page_header.pop("components", None)
    header_actions = []
    stat_cards = []
    filters = {}
    table = {}
    catalogue_table = {}
    shop_order_queues = {}
    shop_journal_tables = {}
    report = {}
    closure_tables = {}
    subview_counts = {}

    if section == "overview":
        stat_cards = _overview_stat_cards(context)
        header_actions = [
            {"label": "Rapport", "icon": "chart-column", "href": "?section=rapport", "primary": False},
            {"label": "Ouvrir la caisse", "icon": "vault", "href": "?section=caisse", "primary": True},
        ]
    elif section == "paiements":
        stat_cards = _payment_stat_cards(context)
        filters = _payment_filters(context, dashboard_url=dashboard_url)
        table = _payment_table(
            context,
            capabilities=capabilities,
            dashboard_url=dashboard_url,
        )
        header_actions = [
            {
                "label": "Passages et réinscriptions",
                "icon": "refresh-cw",
                "href": f"{dashboard_url}?section=reenrollment",
                "primary": False,
            }
        ]
    elif section == "candidatures":
        stat_cards = _admission_stat_cards(context)
        filters = _admission_filters(context, dashboard_url=dashboard_url)
        table = _admission_table(context, capabilities=capabilities, dashboard_url=dashboard_url)
        header_actions = [{"label": "Voir les inscriptions", "icon": "id-card", "href": f"{dashboard_url}?section=inscriptions", "primary": True}]
    elif section == "inscriptions":
        stat_cards = _inscription_stat_cards(context)
        filters = _inscription_filters(context, dashboard_url=dashboard_url)
        table = _inscription_table(context, capabilities=capabilities, dashboard_url=dashboard_url)
        header_actions = [{"label": "Voir les candidatures", "icon": "file-check", "href": f"{dashboard_url}?section=candidatures", "primary": False}]
    elif section == "reenrollment":
        header_actions = [{"label": "Encaissements", "icon": "credit-card", "href": f"{dashboard_url}?section=paiements", "primary": False}]
    elif section == "caisse":
        stat_cards = _cash_stat_cards(context)
        filters = _cash_filters(context, dashboard_url=dashboard_url)
        table = _cash_table(context, dashboard_url=dashboard_url)
        header_actions = [{"label": "Rapport financier", "icon": "chart-no-axes-combined", "href": f"{dashboard_url}?section=rapport", "primary": False}]
    elif section == "depenses":
        stat_cards = _expense_stat_cards(context)
        filters = _expense_filters(context, dashboard_url=dashboard_url)
        table = _expense_table(context, dashboard_url=dashboard_url)
        header_actions = [{"label": "Voir la caisse", "icon": "vault", "href": f"{dashboard_url}?section=caisse", "primary": False}]
    elif section == "salaires":
        stat_cards = _payroll_stat_cards(context)
        filters = _payroll_filters(context, dashboard_url=dashboard_url)
        table = _payroll_table(context, dashboard_url=dashboard_url)
        payroll_stats = context.get("payroll_stats") or {}
        subview_counts = {
            "to_validate": payroll_stats.get("to_review") or 0,
            "to_pay": payroll_stats.get("payable") or 0,
            "history": payroll_stats.get("paid") or 0,
        }
        header_actions = [{"label": "Voir la caisse", "icon": "vault", "href": f"{dashboard_url}?section=caisse", "primary": False}]
    elif section == "honoraires":
        stat_cards = _honorarium_stat_cards(context)
        filters = _honorarium_filters(context, dashboard_url=dashboard_url)
        table = _honorarium_table(context, dashboard_url=dashboard_url)
        honorarium_stats = context.get("honorarium_stats") or {}
        subview_counts = {
            "to_validate": honorarium_stats.get("to_review") or 0,
            "to_pay": honorarium_stats.get("payable") or 0,
            "history": honorarium_stats.get("paid") or 0,
        }
        header_actions = [{"label": "Voir la caisse", "icon": "vault", "href": f"{dashboard_url}?section=caisse", "primary": False}]
    elif section == "rapport":
        stat_cards = _report_stat_cards(context)
        report = _report_presentation(context, dashboard_url=dashboard_url)
        filters = report["filters"]
        table = report["movement_table"]
        header_actions = [
            {"label": "Exporter Excel", "icon": "sheet", "href": report["xlsx_url"], "primary": True, "external": True},
            {"label": "État PDF", "icon": "file-text", "href": report["pdf_url"], "primary": False, "external": True},
        ]
    elif section == "cloture":
        closure_tables = _closure_tables(
            context,
            subcontent_url=subcontent_url or workspace_url or dashboard_url,
        )
        header_actions = [{"label": "Rapport financier", "icon": "chart-no-axes-combined", "href": f"{dashboard_url}?section=rapport", "primary": False}]
    elif section == "dons":
        stat_cards = _donation_stat_cards(context)
        table = _donation_table(
            context,
            dashboard_url=dashboard_url,
            subcontent_url=subcontent_url or workspace_url or dashboard_url,
        )
        header_actions = [{"label": "Voir la caisse", "icon": "vault", "href": f"{dashboard_url}?section=caisse", "primary": False}]
    elif section == "boutique":
        stat_cards = _shop_stat_cards(context)
        shop_order_queues = _shop_order_queues(context)
        catalogue_table = _shop_catalogue_table(context)
        shop_journal_tables = _shop_journal_tables(context)
        if subview == "to_collect":
            table = shop_order_queues["pending"]
        elif subview == "to_prepare":
            table = shop_order_queues["paid"]
        elif subview == "to_deliver":
            table = shop_order_queues["ready"]
        elif subview == "stock":
            table = catalogue_table
            filters = _shop_stock_filters(
                context,
                action_url=subcontent_url or workspace_url or dashboard_url,
            )
        elif subview == "journal":
            table = shop_journal_tables["payments"]
            filters = _shop_journal_filters(
                context,
                action_url=subcontent_url or workspace_url or dashboard_url,
            )
        stats = context.get("shop_stats") or {}
        subview_counts = {
            "to_collect": stats.get("pending_orders") or 0,
            "to_prepare": stats.get("paid_not_delivered") or 0,
            "to_deliver": stats.get("ready_orders") or 0,
            "stock": stats.get("low_stock") or 0,
        }
        header_actions = [{"label": "Voir la caisse", "icon": "vault", "href": f"{dashboard_url}?section=caisse", "primary": False}]

    filters = _augment_manager_filters(filters, section=section, subview=subview)
    subcontent_endpoint = subcontent_url or workspace_url or dashboard_url

    return {
        "section": section,
        "subview": subview,
        "subnavigation": _manager_subnav_items(
            section=section,
            active=subview,
            dashboard_url=dashboard_url,
            subcontent_url=subcontent_endpoint,
            counts=subview_counts,
        ),
        "subcontent_template": manager_subcontent_template(section),
        "subcontent_target": manager_subcontent_target(section),
        "subcontent_indicator": manager_subcontent_indicator(section),
        "page_header": page_header,
        "header_actions": header_actions,
        "stat_cards": stat_cards,
        "filters": filters,
        "table": table,
        "catalogue_table": catalogue_table,
        "shop_order_queues": shop_order_queues,
        "shop_journal_tables": shop_journal_tables,
        "report": report,
        "closure_tables": closure_tables,
        "component_targets": SECTION_PRESENTATION[section]["components"],
    }
