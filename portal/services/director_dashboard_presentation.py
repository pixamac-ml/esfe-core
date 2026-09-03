"""Presentation contracts for the Director of Studies UI Core dashboard."""

from urllib.parse import urlencode

from django.urls import reverse

from notification_center.selectors import get_user_unread_count
from portal.models import TransferRequest
from ui.services.navigation import build_director_navigation


def _dashboard_url(section, view=None):
    params = {"section": section}
    if view:
        params["view"] = view
    return f"{reverse('accounts_portal:portal_dashboard')}?{urlencode(params)}"


def _workspace_url(section, view=None):
    params = {"section": section}
    if view:
        params["view"] = view
    return f"{reverse('accounts_portal:director_workspace')}?{urlencode(params)}"


def _task_cards(tasks):
    labels = {
        "grades_entry_in_progress": "Saisie des notes",
        "teachers_unassigned": "Affectations",
        "semesters_ready_to_validate": "Validation académique",
        "documents_pending": "Dossiers enseignants",
        "transfers_pending": "Transferts",
        "result_anomalies": "Contrôle des notes",
    }
    icons = {
        "grades_entry_in_progress": "list-checks",
        "teachers_unassigned": "user-round-search",
        "semesters_ready_to_validate": "badge-check",
        "documents_pending": "folder-check",
        "transfers_pending": "arrow-left-right",
        "result_anomalies": "triangle-alert",
    }
    tone_by_level = {"critical": "danger", "warning": "warning", "info": "info"}
    level_labels = {"critical": "Priorité haute", "warning": "À traiter", "info": "À surveiller"}
    cards = []
    for task in tasks:
        section = task.get("target") or "home"
        view = task.get("subview") or "overview"
        cards.append(
            {
                **task,
                "label": labels.get(task.get("category"), "Action académique"),
                "icon": icons.get(task.get("category"), "circle-alert"),
                "tone": tone_by_level.get(task.get("level"), "neutral"),
                "level_label": level_labels.get(task.get("level"), "À traiter"),
                "url": _dashboard_url(section, view),
                "hx_get": _workspace_url(section, view),
            }
        )
    return cards


def _academic_journey(workspace):
    ready_count = len(workspace.get("ready_to_validate") or [])
    publish_count = len(workspace.get("ready_to_publish") or [])
    steps = [
        {
            "number": "01",
            "label": "Structurer",
            "summary": "Classes, semestres, UE et maquettes pédagogiques.",
            "metric": f"{workspace.get('total_classes') or 0} classe(s)",
            "section": "programme",
            "view": "maquettes",
            "icon": "library-big",
        },
        {
            "number": "02",
            "label": "Planifier",
            "summary": "Calendrier académique et emplois du temps.",
            "metric": f"{workspace.get('total_semesters') or 0} semestre(s)",
            "section": "planification",
            "view": "overview",
            "icon": "calendar-range",
        },
        {
            "number": "03",
            "label": "Affecter",
            "summary": "Enseignants, charges et dossiers pédagogiques.",
            "metric": f"{workspace.get('teacher_unassigned_count') or 0} à affecter",
            "section": "enseignants",
            "view": "assignments",
            "icon": "users-round",
        },
        {
            "number": "04",
            "label": "Organiser",
            "summary": "Sessions, examens et évaluations des classes.",
            "metric": "Sessions et présences",
            "section": "evaluations_calendar",
            "view": "sessions",
            "icon": "clipboard-check",
        },
        {
            "number": "05",
            "label": "Contrôler et valider",
            "summary": "Notes, anomalies, délibération et publication.",
            "metric": f"{ready_count + publish_count} décision(s)",
            "section": "evaluations",
            "view": "validation",
            "icon": "badge-check",
        },
        {
            "number": "06",
            "label": "Documenter",
            "summary": "Documents académiques et archives de l'annexe.",
            "metric": f"{workspace.get('admin_doc_published_count') or 0} publié(s)",
            "section": "correspondances",
            "view": "archives",
            "icon": "files",
        },
    ]
    for step in steps:
        step["url"] = _dashboard_url(step["section"], step["view"])
        step["hx_get"] = _workspace_url(step["section"], step["view"])
    return steps


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
    task_cards = _task_cards(tasks)
    badges = {
        "home": len(task_cards) or None,
        "evaluations": (
            len(workspace.get("ready_to_validate") or [])
            + len(workspace.get("ready_to_publish") or [])
        ) or None,
        "enseignants": workspace.get("teacher_unassigned_count") or None,
        "correspondances": workspace.get("admin_doc_draft_count") or None,
        "transferts": pending_transfers or None,
        "messagerie": get_user_unread_count(request.user) or None,
    }
    kpis = [
        {
            "label": "Classes actives",
            "value": workspace.get("total_classes") or 0,
            "icon": "school",
            "tone": "primary",
            "description": "Structure de l'année",
            "href": _dashboard_url("programme", "classes"),
            "hx_get": _workspace_url("programme", "classes"),
        },
        {
            "label": "Enseignants",
            "value": workspace.get("teachers_total") or 0,
            "icon": "users",
            "tone": "info",
            "description": "Équipe de l'annexe",
            "href": _dashboard_url("enseignants", "directory"),
            "hx_get": _workspace_url("enseignants", "directory"),
        },
        {
            "label": "Semestres suivis",
            "value": workspace.get("total_semesters") or 0,
            "icon": "calendar-range",
            "tone": "neutral",
            "description": "Progression académique",
            "href": _dashboard_url("programme", "maquettes"),
            "hx_get": _workspace_url("programme", "maquettes"),
        },
        {
            "label": "Résultats à publier",
            "value": len(workspace.get("ready_to_publish") or []),
            "icon": "send",
            "tone": "success",
            "description": "Semestres finalisés",
            "href": _dashboard_url("evaluations", "validation"),
            "hx_get": _workspace_url("evaluations", "validation"),
        },
        {
            "label": "Affectations à revoir",
            "value": workspace.get("teacher_unassigned_count") or 0,
            "icon": "triangle-alert",
            "tone": "warning",
            "description": "Enseignants non affectés",
            "href": _dashboard_url("enseignants", "assignments"),
            "hx_get": _workspace_url("enseignants", "assignments"),
        },
        {
            "label": "Documents publiés",
            "value": workspace.get("admin_doc_published_count") or 0,
            "icon": "file-check-2",
            "tone": "accent",
            "description": "Archives de l'annexe",
            "href": _dashboard_url("correspondances", "archives"),
            "hx_get": _workspace_url("correspondances", "archives"),
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
        "director_tasks": task_cards,
        "director_academic_journey": _academic_journey(workspace),
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
        "director_task_summary": task_cards[0]["message"] if task_cards else "",
        "director_task_count": len(task_cards),
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
