"""Presentation contracts for the Director of Studies UI Core dashboard."""

from urllib.parse import urlencode

from django.urls import reverse

from notification_center.selectors import get_user_unread_count
from portal.models import TransferRequest
from ui.services.navigation import build_director_navigation


def _dashboard_url(section):
    return f"{reverse('accounts_portal:portal_dashboard')}?{urlencode({'section': section})}"


def _workspace_url(section):
    return f"{reverse('accounts_portal:director_workspace')}?{urlencode({'section': section})}"


def _class_table_rows(class_cards):
    rows = []
    for item in class_cards[:6]:
        bucket = item.get("workflow_bucket")
        if bucket == "ready":
            status = ("Prête", "success")
        elif bucket == "rejected":
            status = ("À revoir", "danger")
        else:
            status = ("En cours", "warning")
        rows.append(
            {
                "label": item["class"].display_name,
                "cells": [
                    {"value": item["class"].display_name},
                    {"value": item.get("student_count") or 0},
                    {"value": f"{item.get('progress') or 0} %"},
                    {"value": status[0], "tone": status[1]},
                ],
            }
        )
    return rows


def build_director_dashboard_presentation(request, workspace):
    """Map existing business context to presentation-only UI Core contracts."""

    active_section = workspace.get("section") or "home"
    branch = workspace.get("branch")
    class_cards = workspace.get("class_cards") or []
    tasks = workspace.get("tasks_center") or []
    academic_year = workspace.get("director_active_academic_year")
    if academic_year is None and class_cards:
        academic_year = class_cards[0]["class"].academic_year

    pending_transfers = (
        TransferRequest.objects.filter(
            branch=branch,
            status=TransferRequest.STATUS_SUBMITTED,
        ).count()
        if branch else 0
    )
    badges = {
        "evaluations": len(workspace.get("ready_to_publish") or []),
        "enseignants": workspace.get("teacher_unassigned_count") or None,
        "transferts": pending_transfers or None,
        "messagerie": get_user_unread_count(request.user) or None,
    }
    kpis = [
        {
            "label": "Classes actives",
            "value": workspace.get("total_classes") or 0,
            "icon": "school",
            "tone": "primary",
            "description": "Dans votre périmètre",
            "href": _dashboard_url("programme"),
            "hx_get": _workspace_url("programme"),
        },
        {
            "label": "Enseignants",
            "value": workspace.get("teachers_total") or 0,
            "icon": "users",
            "tone": "info",
            "description": "Affectés à l'annexe",
            "href": _dashboard_url("enseignants"),
            "hx_get": _workspace_url("enseignants"),
        },
        {
            "label": "Semestres suivis",
            "value": workspace.get("total_semesters") or 0,
            "icon": "calendar-range",
            "tone": "neutral",
            "description": "Périodes académiques",
            "href": _dashboard_url("programme"),
            "hx_get": _workspace_url("programme"),
        },
        {
            "label": "Résultats à publier",
            "value": len(workspace.get("ready_to_publish") or []),
            "icon": "send",
            "tone": "success",
            "description": "Semestres finalisés",
            "href": _dashboard_url("evaluations"),
            "hx_get": _workspace_url("evaluations"),
        },
        {
            "label": "Affectations à revoir",
            "value": workspace.get("teacher_unassigned_count") or 0,
            "icon": "triangle-alert",
            "tone": "warning",
            "description": "Enseignants non affectés",
            "href": _dashboard_url("enseignants"),
            "hx_get": _workspace_url("enseignants"),
        },
        {
            "label": "Documents publiés",
            "value": workspace.get("admin_doc_published_count") or 0,
            "icon": "file-check-2",
            "tone": "accent",
            "description": "Correspondances disponibles",
            "href": _dashboard_url("correspondances"),
            "hx_get": _workspace_url("correspondances"),
        },
    ]
    quick_actions = [
        {"key": "calendrier", "label": "Calendrier", "icon": "calendar-days"},
        {
            "key": "evaluations_calendar",
            "label": "Sessions d'évaluations",
            "icon": "clipboard-check",
        },
        {"key": "enseignants", "label": "Enseignants", "icon": "users"},
        {"key": "planification", "label": "Emploi du temps", "icon": "calendar-range"},
        {"key": "correspondances", "label": "Documents", "icon": "file-plus-2"},
        {"key": "messagerie", "label": "Messagerie", "icon": "messages-square"},
    ]
    for action in quick_actions:
        action.update(
            {
                "url": _dashboard_url(action["key"]),
                "hx_get": _workspace_url(action["key"]),
            }
        )

    return {
        "director_navigation": build_director_navigation(
            request.user,
            active_section=active_section,
            badges=badges,
        ),
        "director_kpis": kpis,
        "director_quick_actions": quick_actions,
        "director_class_headers": [
            {"label": "Classe"},
            {"label": "Étudiants"},
            {"label": "Progression"},
            {"label": "Statut"},
        ],
        "director_class_table_rows": _class_table_rows(class_cards),
        "director_context_label": " · ".join(
            value
            for value in (
                getattr(branch, "name", None) or "Périmètre global",
                getattr(academic_year, "name", None),
            )
            if value
        ),
        "director_active_academic_year": academic_year,
        "director_task_summary": tasks[0]["message"] if tasks else "",
        "director_task_count": len(tasks),
        "director_active_section": active_section,
        "notification_count": get_user_unread_count(request.user),
        "notifications_url": reverse("notification_center:notifications"),
        "preview_url": reverse("accounts_portal:director_notifications_preview"),
        "center_url": _workspace_url("messagerie"),
        "director_teacher_filters": [
            {
                "label": "Rechercher un enseignant",
                "name": "teacher_q",
                "type": "search",
                "value": workspace.get("teacher_q") or "",
                "placeholder": "Nom, prénom ou identifiant",
                "clearable": True,
            }
        ],
        "director_teacher_filter_action": _workspace_url("enseignants"),
        "director_teacher_filter_reset": _workspace_url("enseignants"),
        "director_teacher_active_filters": (
            [f"Recherche : {workspace.get('teacher_q')}"]
            if workspace.get("teacher_q")
            else []
        ),
    }
