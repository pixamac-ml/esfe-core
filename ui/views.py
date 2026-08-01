import json
from functools import wraps

from django.conf import settings
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from accounts.dashboards.helpers import get_user_branch
from accounts.forms import SystemProfileForm, UserPreferenceForm
from accounts.models import Profile, UserPreference
from notification_center.selectors import get_user_in_app_messages, get_user_unread_count
from branches.models import Branch
from shop.models import ShopProduct
from students.models import Student

from ui.components.account.preference_settings import PreferenceSettings
from ui.components.account.profile_card import ProfileCard
from ui.components.account.profile_dropdown import ProfileDropdown
from ui.components.account.profile_editor import ProfileEditor
from ui.components.account.profile_view import ProfileView
from ui.components.account.security_settings import SecuritySettings
from ui.components.notifications.badge import NotificationBadge
from ui.components.notifications.bell import NotificationBell
from ui.components.notifications.drawer import NotificationDrawer
from ui.components.notifications.item import NotificationItem
from ui.components.notifications.list import NotificationList
from ui.components.shop.product_card import ProductCard
from ui.components.shop.product_detail_drawer import ProductDetailDrawer
from ui.components.shop.product_grid import ProductGrid
from ui.components.student.identity_card import StudentIdentityCard
from ui.components.student.progress_card import StudentProgressCard
from ui.components.student.status_card import StudentStatusCard


DEMO_ROWS = [
    {"name": "Aminata Traoré", "status": "Actif", "tone": "success", "context": "Bamako", "amount": "125 000 FCFA"},
    {"name": "Moussa Diarra", "status": "En attente", "tone": "warning", "context": "Sikasso", "amount": "98 500 FCFA"},
    {"name": "Fatoumata Koné", "status": "Actif", "tone": "success", "context": "Bamako", "amount": "210 000 FCFA"},
    {"name": "Ibrahim Coulibaly", "status": "Suspendu", "tone": "danger", "context": "Kayes", "amount": "-15 000 FCFA"},
    {"name": "Awa Maïga", "status": "Actif", "tone": "success", "context": "Ségou", "amount": "76 250 FCFA"},
    {"name": "Oumar Sangaré", "status": "Archivé", "tone": "neutral", "context": "Mopti", "amount": "0 FCFA"},
]


def ui_system_access(view):
    """Apply the catalogue access policy to full pages and fragments."""

    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not settings.DEBUG and not request.user.is_superuser:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


def _toast_response(response, message, tone="success"):
    response["HX-Trigger"] = json.dumps(
        {"ui:toast": {"message": message, "tone": tone}}, ensure_ascii=True
    )
    return response


def _system_navigation():
    ui_core_families = (
        ("Fondations", "foundations", "palette"),
        ("Navigation", "navigation", "panel-left"),
        ("Layout", "layout", "layout-dashboard"),
        ("Données et KPI", "data", "gauge"),
        ("Tableaux", "tables", "table-2"),
        ("Filtres", "filters", "list-filter"),
        ("Formulaires", "forms", "text-cursor-input"),
        ("Feedback", "feedback", "message-square"),
        ("Overlays", "overlays", "panels-top-left"),
        ("Productivité", "productivity", "zap"),
        ("Visualisation", "visualization", "chart-no-axes-combined"),
        ("Planning", "planning", "calendar-days"),
        ("Responsive", "responsive", "smartphone"),
        ("Accessibilité", "accessibility", "accessibility"),
        ("Dashboard", "dashboard-example", "blocks"),
    )
    domain_families = (
        ("Compte & Profil", "domain-account", "user"),
        ("Notifications", "domain-notifications", "bell"),
        ("Étudiants", "domain-student", "graduation-cap"),
        ("Boutique", "domain-shop", "shopping-bag"),
    )
    return [
        {
            "label": "UI Core",
            "items": [
                {
                    "label": label,
                    "url": f"#{anchor}",
                    "icon": icon,
                    "active": anchor == "foundations",
                    "badge": None,
                    "disabled": False,
                }
                for label, anchor, icon in ui_core_families
            ],
        },
        {
            "label": "Composants Métier",
            "items": [
                {
                    "label": label,
                    "url": f"#{anchor}",
                    "icon": icon,
                    "active": False,
                    "badge": None,
                    "disabled": False,
                }
                for label, anchor, icon in domain_families
            ],
        },
    ]


def gallery(request):
    ctx = {
        # --- Avatar group ---
        "sample_avatars": [
            {"initials": "JD"}, {"initials": "AK"},
            {"initials": "ML"}, {"initials": "SB"}, {"initials": "TR"},
        ],
        # --- KPI row ---
        "kpi_cards": [
            {"label": "Étudiants", "value": "1 234", "icon": "users"},
            {"label": "Enseignants", "value": "89", "icon": "graduation-cap"},
            {"label": "Classes", "value": "24", "icon": "school"},
            {"label": "Taux réussite", "value": "94%", "icon": "award"},
        ],
        # --- DataTable ---
        "table_headers": [
            {"label": "Nom"},
            {"label": "Prénom"},
            {"label": "Classe", "sortable": True, "sort_url": "?sort=classe"},
            {"label": "Moyenne", "sortable": True, "sort_url": "?sort=moyenne", "sorted": True, "sort_dir": "desc"},
        ],
        "table_rows": [
            {"id": 1, "cells": [{"value": "Diakité"}, {"value": "Moussa"}, {"value": "6e A"}, {"value": "14,5", "editable": True, "field": "note"}]},
            {"id": 2, "cells": [{"value": "Traoré"}, {"value": "Aminata"}, {"value": "5e B"}, {"value": "16,2", "editable": True, "field": "note"}]},
            {"id": 3, "cells": [{"value": "Keita"}, {"value": "Souleymane"}, {"value": "4e C"}, {"value": "12,8", "editable": True, "field": "note"}]},
        ],
        "empty_rows": [],
        # --- Select ---
        "classe_options": [
            {"value": "6e", "label": "6e"},
            {"value": "5e", "label": "5e"},
            {"value": "4e", "label": "4e"},
        ],
        # --- Combobox ---
        "city_options": [
            {"value": "bko", "label": "Bamako"},
            {"value": "bke", "label": "Burkina"},
            {"value": "abj", "label": "Abidjan"},
        ],
        # --- Radio ---
        "genre_options": [
            {"value": "M", "label": "Masculin"},
            {"value": "F", "label": "Féminin"},
        ],
        # --- FilterBar ---
        "filter_options": [
            {
                "name": "classe", "placeholder": "Classe",
                "options": [{"value": "6e", "label": "6e"}, {"value": "5e", "label": "5e"}],
            },
            {
                "name": "statut", "placeholder": "Statut",
                "options": [{"value": "actif", "label": "Actif"}, {"value": "inactif", "label": "Inactif"}],
            },
        ],
        # --- Breadcrumb ---
        "breadcrumb_items": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Gestion"},
            {"label": "Étudiants"},
        ],
        # --- Tabs ---
        "tab_items": [
            {"id": "infos", "label": "Informations", "icon": "info"},
            {"id": "notes", "label": "Notes", "icon": "file-text"},
            {"id": "paiements", "label": "Paiements", "icon": "wallet"},
        ],
        # --- Stepper ---
        "step_items": [
            {"label": "Inscription"},
            {"label": "Documents"},
            {"label": "Paiement"},
            {"label": "Confirmation"},
        ],
        "vertical_step_items": [
            {"label": "Création dossier", "description": "Remplir le formulaire en ligne", "icon": "file-text"},
            {"label": "Validation documents", "description": "Fournir les pièces justificatives", "icon": "folder-check"},
            {"label": "Paiement frais", "description": "Régler les frais de scolarité", "icon": "wallet"},
            {"label": "Inscription finalisée", "description": "Confirmation et accès plateforme", "icon": "graduation-cap"},
        ],
        # --- Timeline ---
        "timeline_items": [
            {"title": "Inscription", "description": "Moussa Diakité inscrit en 6e A", "date": "12 juin", "tone": "primary", "icon": "user-plus"},
            {"title": "Paiement", "description": "Frais de scolarité 2025-2026 réglés", "date": "12 juin", "tone": "success", "icon": "wallet"},
            {"title": "Alerte", "description": "Absence non justifiée signalée", "date": "11 juin", "tone": "danger", "icon": "alert-triangle"},
        ],
        # --- Dropdown items ---
        "dropdown_items": [
            {"label": "Voir", "icon": "eye", "url": "#"},
            {"label": "Modifier", "icon": "pencil", "url": "#"},
            {"label": "Supprimer", "icon": "trash-2", "url": "#", "danger": True, "divider": True},
        ],
        # --- Cell samples ---
        "status_cell_items": [
            {"label": "Payé", "tone": "success", "icon": "check-circle"},
            {"label": "En attente", "tone": "warning", "icon": "clock"},
            {"label": "En retard", "tone": "danger", "icon": "alert-circle"},
            {"label": "Inscrit", "tone": "primary", "icon": "user-check"},
            {"label": "Brouillon", "tone": "neutral"},
        ],
        # --- Schedule samples ---
        "schedule_slots": [
            {"day": 0, "start": 1, "end": 3, "label": "Mathématiques", "teacher": "M. Koné", "room": "101", "color": "school-primary"},
            {"day": 0, "start": 4, "end": 5, "label": "Physique", "teacher": "Mme Diallo", "room": "103", "color": "success"},
            {"day": 1, "start": 2, "end": 4, "label": "Français", "teacher": "M. Traoré", "room": "102", "color": "info"},
            {"day": 1, "start": 5, "end": 6, "label": "Anglais", "teacher": "Mme Sanogo", "room": "201", "color": "warning"},
            {"day": 2, "start": 0, "end": 2, "label": "Histoire", "teacher": "M. Camara", "room": "104", "color": "school-primary"},
            {"day": 2, "start": 3, "end": 5, "label": "SV.Terre", "teacher": "Mme Keita", "room": "105", "color": "success"},
            {"day": 3, "start": 1, "end": 2, "label": "Anglais", "teacher": "Mme Sanogo", "room": "201", "color": "warning"},
            {"day": 3, "start": 4, "end": 6, "label": "Mathématiques", "teacher": "M. Koné", "room": "101", "color": "school-primary"},
            {"day": 4, "start": 2, "end": 4, "label": "EPS", "teacher": "M. Diarra", "room": "Stade", "color": "info"},
            {"day": 4, "start": 5, "end": 7, "label": "Physique", "teacher": "Mme Diallo", "room": "103", "color": "success"},
        ],
        "sample_actions": [
            {"icon": "eye", "url": "#", "title": "Voir"},
            {"divider": True},
            {"icon": "pencil", "url": "#", "title": "Modifier"},
            {"icon": "trash-2", "url": "#", "title": "Supprimer"},
        ],
    }
    return render(request, "ui/gallery.html", ctx)


@ui_system_access
def ui_system(request):
    """Protected, non-business reference page for UI Core."""

    scope = getattr(request, "access_scope", None) or {}
    branch = scope.get("branch")
    context = {
        "page_title": "UI Core | ESFE",
        "navigation_groups": _system_navigation(),
        "user_display_name": request.user.get_full_name() or request.user.get_username(),
        "user_role": scope.get("position") or scope.get("role") or "Utilisateur",
        "branch_name": getattr(branch, "name", "") if branch else "",
        "sample_breadcrumbs": [
            {"label": "UI", "url": request.path},
            {"label": "Système"},
        ],
        "sample_tabs": [
            {"id": "overview", "label": "Vue générale", "icon": "layout-dashboard", "count": 12},
            {"id": "activity", "label": "Activité", "icon": "history", "count": 4},
            {"id": "disabled", "label": "Indisponible", "disabled": True},
        ],
        "sample_menu": [
            {"label": "Consulter", "icon": "eye"},
            {"label": "Dupliquer", "icon": "copy"},
            {"label": "Action indisponible", "icon": "lock", "disabled": True, "separator": True},
            {"label": "Supprimer", "icon": "trash-2", "danger": True, "separator": True},
        ],
        "sample_timeline": [
            {"title": "Mise à jour terminée", "description": "Le fragment a été remplacé sans navigation.", "date": "09:42", "icon": "refresh-cw"},
            {"title": "Validation reçue", "description": "Le formulaire technique est valide.", "date": "09:40", "icon": "circle-check"},
            {"title": "Contrôle requis", "description": "Exemple de contenu long qui reste lisible sur petit écran.", "date": "Hier", "icon": "triangle-alert"},
        ],
        "chart_labels": ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin"],
        "chart_datasets": [
            {
                "label": "Activité",
                "data": [18, 24, 21, 35, 31, 42],
                "borderColor": "ui-primary",
                "backgroundColor": "ui-primary-soft",
                "tension": 0.35,
                "fill": True,
            }
        ],
        "demo_table_url": reverse("ui:system_demo_table"),
        "demo_modal_url": reverse("ui:system_demo_modal"),
        "demo_drawer_url": reverse("ui:system_demo_drawer"),
        "demo_form_url": reverse("ui:system_demo_form"),
        "demo_confirm_url": reverse("ui:system_demo_confirm"),
        "demo_refresh_url": reverse("ui:system_demo_refresh"),
        "demo_error_url": reverse("ui:system_demo_error"),
        "domain_families": DOMAIN_FAMILIES,
    }
    return render(request, "ui/system.html", context)


@ui_system_access
@require_http_methods(["GET"])
def ui_system_demo_table(request):
    query = request.GET.get("q", "").strip().casefold()
    status = request.GET.get("status", "").strip()
    density = request.GET.get("density", "comfortable")
    state = request.GET.get("state", "default")
    sort = request.GET.get("sort", "name")
    try:
        page = max(int(request.GET.get("page", 1)), 1)
    except ValueError:
        page = 1
    rows = [
        row
        for row in DEMO_ROWS
        if (
            not query
            or query in row["name"].casefold()
            or query in row["context"].casefold()
        )
        and (not status or row["status"] == status)
    ]
    rows.sort(key=lambda row: row.get(sort, row["name"]))
    page_size = 3
    page_count = max((len(rows) + page_size - 1) // page_size, 1)
    page = min(page, page_count)
    visible_rows = rows[(page - 1) * page_size : page * page_size]
    table_rows = [
        {
            "label": row["name"],
            "cells": [
                {"value": row["name"]},
                {"value": row["status"], "tone": row["tone"]},
                {"value": row["context"]},
                {"value": row["amount"], "amount": True},
            ],
        }
        for row in visible_rows
    ]
    query_string = request.GET.get("q", "")
    base_url = reverse("ui:system_demo_table")
    context = {
        "headers": [
            {"label": "Identité", "sort_url": f"{base_url}?sort=name&q={query_string}&status={status}&density={density}"},
            {"label": "Statut", "sort_url": f"{base_url}?sort=status&q={query_string}&status={status}&density={density}"},
            {"label": "Contexte"},
            {"label": "Montant"},
        ],
        "rows": [] if state == "empty" else table_rows,
        "result_count": 0 if state == "empty" else len(rows),
        "page": page,
        "page_count": page_count,
        "query": query_string,
        "status": status,
        "density": density if density in {"comfortable", "compact"} else "comfortable",
        "error": "Erreur de démonstration contrôlée." if state == "error" else "",
        "permission_denied": state == "permission",
        "base_url": base_url,
    }
    return render(request, "ui/partials/system_table_demo.html", context)


@ui_system_access
@require_http_methods(["GET"])
def ui_system_demo_modal(request):
    return render(request, "ui/partials/system_modal_demo.html")


@ui_system_access
@require_http_methods(["GET"])
def ui_system_demo_drawer(request):
    return render(
        request,
        "ui/partials/system_drawer_demo.html",
        {
            "drawer_tabs": [
                {"id": "detail", "label": "Détail", "icon": "file-text"},
                {"id": "history", "label": "Historique", "icon": "history", "count": 3},
            ]
        },
    )


@ui_system_access
@require_http_methods(["GET", "POST"])
def ui_system_demo_form(request):
    values = {"name": "", "email": "", "context": "comfortable"}
    errors = {}
    success = False
    if request.method == "POST":
        values = {
            "name": request.POST.get("name", "").strip(),
            "email": request.POST.get("email", "").strip(),
            "context": request.POST.get("context", "comfortable"),
        }
        if len(values["name"]) < 2:
            errors["name"] = "Saisissez au moins deux caractères."
        if "@" not in values["email"]:
            errors["email"] = "Saisissez une adresse email valide."
        success = not errors
    response = render(
        request,
        "ui/partials/system_form_demo.html",
        {
            "values": values,
            "errors": errors,
            "success": success,
            "form_density_options": [
                {"value": "comfortable", "label": "Comfortable"},
                {"value": "compact", "label": "Compacte"},
            ],
        },
    )
    if success:
        _toast_response(response, "Formulaire validé sans rechargement.")
    return response


@ui_system_access
@require_http_methods(["POST"])
def ui_system_demo_confirm(request):
    response = render(request, "ui/partials/system_confirmation_demo.html")
    return _toast_response(response, "Action fictive confirmée.", "success")


@ui_system_access
@require_http_methods(["GET"])
def ui_system_demo_refresh(request):
    response = render(request, "ui/partials/system_refresh_demo.html")
    return _toast_response(response, "Zone actualisée.", "info")


@ui_system_access
@require_http_methods(["GET"])
def ui_system_demo_error(request):
    return HttpResponse(
        '<div class="rounded-ui-card bg-ui-danger-soft p-4 text-sm text-ui-danger" role="alert">Erreur simulée et contrôlée.</div>',
        status=500,
    )


# ==========================================================
# DOMAIN COMPONENTS CATALOGUE
# ==========================================================

DOMAIN_FAMILIES = [
    {
        "id": "account",
        "label": "Compte & Profil",
        "icon": "user",
        "description": "Composants partagés pour le compte utilisateur, le profil, l'édition et la sécurité.",
        "components": [
            {"name": "account.profile_card", "label": "Carte Profil", "description": "Avatar, nom, rôle, annexe, statut — compact ou étendu.", "states": ["actif", "suspendu", "compact"]},
            {"name": "account.profile_dropdown", "label": "Dropdown Profil", "description": "Menu déroulant avec accès rapide au profil, édition, sécurité, déconnexion.", "states": ["ouvert", "fermé"]},
            {"name": "account.profile_view", "label": "Vue Profil", "description": "Affichage complet du profil avec identité, contacts, métadonnées, actions.", "states": ["complet", "sans photo"]},
            {"name": "account.profile_editor", "label": "Éditeur Profil", "description": "Formulaire HTMX de modification du profil dans un drawer.", "states": ["vide", "rempli", "erreur", "loading"]},
            {"name": "account.security_settings", "label": "Sécurité", "description": "Changement de mot de passe, sessions actives.", "states": ["normal", "loading"]},
            {"name": "account.preference_settings", "label": "Préférences", "description": "Paramètres de notifications, interface, langue.", "states": ["normal", "loading"]},
        ],
    },
    {
        "id": "notifications",
        "label": "Notifications",
        "icon": "bell",
        "description": "Cloche, badge, items, liste, drawer — branchés sur le moteur notifier existant.",
        "components": [
            {"name": "notifications.bell", "label": "Cloche", "description": "Icône cloche avec compteur non lu, état zéro, chargement HTMX.", "states": ["zéro", "1-99", "99+"]},
            {"name": "notifications.badge", "label": "Badge Compteur", "description": "Badge numérique isolé, 3 tailles.", "states": ["sm", "md", "lg"]},
            {"name": "notifications.item", "label": "Item Notification", "description": "Ligne de notification avec icône, titre, résumé, date, priorité, marquer lu.", "states": ["lu", "non lu", "haute priorité"]},
            {"name": "notifications.list", "label": "Liste Notifications", "description": "Liste paginée avec skeleton, état vide, chargement progressif.", "states": ["vide", "loading", "rempli"]},
            {"name": "notifications.drawer", "label": "Drawer Notifications", "description": "Panneau latéral avec liste de notifications et lien vers le centre.", "states": ["ouvert", "fermé", "loading"]},
        ],
    },
    {
        "id": "student",
        "label": "Étudiants",
        "icon": "graduation-cap",
        "description": "Identité, statut, progression — pour les dashboards partagés.",
        "components": [
            {"name": "student.identity_card", "label": "Carte Identité", "description": "Photo, matricule, nom, classe, niveau, filière.", "states": ["actif", "inactif", "sans photo"]},
            {"name": "student.status_card", "label": "Carte Statut", "description": "Statut académique, décision, validations.", "states": ["promu", "redoublant", "transféré", "en attente"]},
            {"name": "student.progress_card", "label": "Carte Progression", "description": "Barres de progression académique globales et par matière.", "states": ["complet", "partiel", "vide"]},
        ],
    },
    {
        "id": "shop",
        "label": "Boutique",
        "icon": "shopping-bag",
        "description": "Produits, grille, détail — pour le catalogue et les commandes.",
        "components": [
            {"name": "shop.product_card", "label": "Carte Produit", "description": "Image, nom, catégorie, prix, stock, action d'ajout.", "states": ["disponible", "indisponible", "rupture de stock"]},
            {"name": "shop.product_grid", "label": "Grille Produits", "description": "Grille responsive avec skeleton, état vide.", "states": ["rempli", "vide", "loading"]},
            {"name": "shop.product_detail_drawer", "label": "Drawer Détail", "description": "Détail produit avec variantes, stock, ajout panier.", "states": ["ouvert", "fermé", "loading"]},
        ],
    },
]


DOMAIN_COMPONENTS = [
    {
        "slug": "account-profile-card",
        "family": "account",
        "name": "account.profile_card",
        "label": "Carte Profil",
        "description": "Badge profil compact ou étendu avec avatar, rôle, annexe et statut.",
        "states": ["actif", "suspendu", "compact"],
        "backend_status": "Backend branché",
        "backend_real": True,
        "used_in_dashboard": False,
        "component_class": ProfileCard,
        "demo_kind": "account-profile-card",
        "files": [
            "ui/components/account/profile_card.py",
            "ui/templates/account/profile_card.html",
        ],
        "dashboard_refs": [
            "accounts_portal:system_profile",
            "accounts_portal:system_profile_edit",
        ],
    },
    {
        "slug": "account-profile-dropdown",
        "family": "account",
        "name": "account.profile_dropdown",
        "label": "Dropdown Profil",
        "description": "Menu de compte avec accès vers profil, sécurité, préférences et déconnexion.",
        "states": ["ouvert", "fermé"],
        "backend_status": "Backend branché",
        "backend_real": True,
        "used_in_dashboard": True,
        "component_class": ProfileDropdown,
        "demo_kind": "account-profile-dropdown",
        "files": [
            "ui/components/account/profile_dropdown.py",
            "ui/templates/account/profile_dropdown.html",
            "portal/views/system_profile.py",
        ],
        "dashboard_refs": [
            "accounts_portal:system_profile",
            "accounts_portal:system_security",
            "accounts_portal:system_profile_edit",
        ],
    },
    {
        "slug": "account-profile-view",
        "family": "account",
        "name": "account.profile_view",
        "label": "Vue Profil",
        "description": "Vue détaillée du profil avec identité, contacts, métadonnées et actions.",
        "states": ["complet", "sans photo"],
        "backend_status": "Backend branché",
        "backend_real": True,
        "used_in_dashboard": True,
        "component_class": ProfileView,
        "demo_kind": "account-profile-view",
        "files": [
            "ui/components/account/profile_view.py",
            "ui/templates/account/profile_view.html",
            "portal/views/system_profile.py",
        ],
        "dashboard_refs": [
            "accounts_portal:system_profile",
        ],
    },
    {
        "slug": "account-profile-editor",
        "family": "account",
        "name": "account.profile_editor",
        "label": "Éditeur Profil",
        "description": "Formulaire HTMX réel pour modifier les champs autorisés du profil système.",
        "states": ["vide", "rempli", "erreur", "loading"],
        "backend_status": "Backend branché",
        "backend_real": True,
        "used_in_dashboard": True,
        "component_class": ProfileEditor,
        "demo_kind": "account-profile-editor",
        "files": [
            "ui/components/account/profile_editor.py",
            "ui/templates/account/profile_editor.html",
            "accounts/forms.py",
            "portal/views/system_profile.py",
        ],
        "dashboard_refs": [
            "accounts_portal:system_profile_edit",
        ],
    },
    {
        "slug": "account-security-settings",
        "family": "account",
        "name": "account.security_settings",
        "label": "Sécurité",
        "description": "Changement de mot de passe et sessions actives via les vues institutionnelles.",
        "states": ["normal", "loading"],
        "backend_status": "Backend branché",
        "backend_real": True,
        "used_in_dashboard": True,
        "component_class": SecuritySettings,
        "demo_kind": "account-security-settings",
        "files": [
            "ui/components/account/security_settings.py",
            "ui/templates/account/security_settings.html",
            "portal/views/system_profile.py",
            "accounts/auth_views.py",
        ],
        "dashboard_refs": [
            "accounts_portal:system_security",
            "accounts_portal:system_change_password",
        ],
    },
    {
        "slug": "account-preference-settings",
        "family": "account",
        "name": "account.preference_settings",
        "label": "Préférences",
        "description": "Préférences utilisateur réelles sauvegardées par le backend existant.",
        "states": ["normal", "loading"],
        "backend_status": "Backend branché",
        "backend_real": True,
        "used_in_dashboard": True,
        "component_class": PreferenceSettings,
        "demo_kind": "account-preference-settings",
        "files": [
            "ui/components/account/preference_settings.py",
            "ui/templates/account/preference_settings.html",
            "accounts/forms.py",
            "accounts/views.py",
        ],
        "dashboard_refs": [
            "accounts:edit_preferences",
        ],
    },
    {
        "slug": "notifications-bell",
        "family": "notifications",
        "name": "notifications.bell",
        "label": "Cloche",
        "description": "Cloche avec compteur réel et chargement HTMX vers le centre de notifications.",
        "states": ["zéro", "1-99", "99+"],
        "backend_status": "Backend branché",
        "backend_real": True,
        "used_in_dashboard": True,
        "component_class": NotificationBell,
        "demo_kind": "notifications-bell",
        "files": [
            "ui/components/notifications/bell.py",
            "ui/templates/notifications/bell.html",
            "notification_center/views.py",
            "notification_center/selectors.py",
        ],
        "dashboard_refs": [
            "notification_center:notifications",
            "notification_center:notifications_widget",
        ],
    },
    {
        "slug": "notifications-badge",
        "family": "notifications",
        "name": "notifications.badge",
        "label": "Badge Compteur",
        "description": "Badge numérique isolé pour les compteurs de notifications.",
        "states": ["sm", "md", "lg"],
        "backend_status": "Backend branché",
        "backend_real": True,
        "used_in_dashboard": True,
        "component_class": NotificationBadge,
        "demo_kind": "notifications-badge",
        "files": [
            "ui/components/notifications/badge.py",
            "ui/templates/notifications/badge.html",
        ],
        "dashboard_refs": [
            "notification_center:notifications",
        ],
    },
    {
        "slug": "notifications-item",
        "family": "notifications",
        "name": "notifications.item",
        "label": "Item Notification",
        "description": "Ligne de notification avec marquage lu et destination sécurisée.",
        "states": ["lu", "non lu", "haute priorité"],
        "backend_status": "Backend branché",
        "backend_real": True,
        "used_in_dashboard": True,
        "component_class": NotificationItem,
        "demo_kind": "notifications-item",
        "files": [
            "ui/components/notifications/item.py",
            "ui/templates/notifications/item.html",
            "notification_center/views.py",
        ],
        "dashboard_refs": [
            "notification_center:notifications",
        ],
    },
    {
        "slug": "notifications-list",
        "family": "notifications",
        "name": "notifications.list",
        "label": "Liste Notifications",
        "description": "Liste paginée avec état vide, loading et chargement progressif.",
        "states": ["vide", "loading", "rempli"],
        "backend_status": "Backend branché",
        "backend_real": True,
        "used_in_dashboard": True,
        "component_class": NotificationList,
        "demo_kind": "notifications-list",
        "files": [
            "ui/components/notifications/list.py",
            "ui/templates/notifications/list.html",
            "notification_center/views.py",
        ],
        "dashboard_refs": [
            "notification_center:notifications",
        ],
    },
    {
        "slug": "notifications-drawer",
        "family": "notifications",
        "name": "notifications.drawer",
        "label": "Drawer Notifications",
        "description": "Drawer latéral relié au centre et au compteur réel.",
        "states": ["ouvert", "fermé", "loading"],
        "backend_status": "Backend branché",
        "backend_real": True,
        "used_in_dashboard": True,
        "component_class": NotificationDrawer,
        "demo_kind": "notifications-drawer",
        "files": [
            "ui/components/notifications/drawer.py",
            "ui/templates/notifications/drawer.html",
            "notification_center/views.py",
        ],
        "dashboard_refs": [
            "notification_center:notifications",
            "notification_center:notifications_widget",
        ],
    },
    {
        "slug": "student-identity-card",
        "family": "student",
        "name": "student.identity_card",
        "label": "Carte Identité",
        "description": "Carte étudiant avec matricule, classe, niveau et filière.",
        "states": ["actif", "inactif", "sans photo"],
        "backend_status": "Backend branché",
        "backend_real": True,
        "used_in_dashboard": True,
        "component_class": StudentIdentityCard,
        "demo_kind": "student-identity-card",
        "files": [
            "ui/components/student/identity_card.py",
            "ui/templates/student/identity_card.html",
            "students/models.py",
            "portal/student/widgets/academics.py",
        ],
        "dashboard_refs": [
            "portal_student:student_dashboard",
        ],
    },
    {
        "slug": "student-status-card",
        "family": "student",
        "name": "student.status_card",
        "label": "Carte Statut",
        "description": "Statut académique et décision annuelle.",
        "states": ["promu", "redoublant", "transféré", "en attente"],
        "backend_status": "Backend branché",
        "backend_real": True,
        "used_in_dashboard": True,
        "component_class": StudentStatusCard,
        "demo_kind": "student-status-card",
        "files": [
            "ui/components/student/status_card.py",
            "ui/templates/student/status_card.html",
            "students/models.py",
        ],
        "dashboard_refs": [
            "portal_student:student_dashboard",
        ],
    },
    {
        "slug": "student-progress-card",
        "family": "student",
        "name": "student.progress_card",
        "label": "Carte Progression",
        "description": "Barres de progression globales ou par matière.",
        "states": ["complet", "partiel", "vide"],
        "backend_status": "Backend branché",
        "backend_real": True,
        "used_in_dashboard": True,
        "component_class": StudentProgressCard,
        "demo_kind": "student-progress-card",
        "files": [
            "ui/components/student/progress_card.py",
            "ui/templates/student/progress_card.html",
            "portal/student/widgets/academics.py",
        ],
        "dashboard_refs": [
            "portal_student:student_dashboard",
        ],
    },
    {
        "slug": "shop-product-card",
        "family": "shop",
        "name": "shop.product_card",
        "label": "Carte Produit",
        "description": "Carte produit avec stock, prix et action d'achat ou d'ajout.",
        "states": ["disponible", "indisponible", "rupture de stock"],
        "backend_status": "Backend branché",
        "backend_real": True,
        "used_in_dashboard": True,
        "component_class": ProductCard,
        "demo_kind": "shop-product-card",
        "files": [
            "ui/components/shop/product_card.py",
            "ui/templates/shop/product_card.html",
            "shop/views.py",
            "shop/models.py",
        ],
        "dashboard_refs": [
            "shop:public_home",
            "shop:public_catalog",
            "shop:manager_product_create",
        ],
    },
    {
        "slug": "shop-product-grid",
        "family": "shop",
        "name": "shop.product_grid",
        "label": "Grille Produits",
        "description": "Grille responsive avec état vide et loading.",
        "states": ["rempli", "vide", "loading"],
        "backend_status": "Backend branché",
        "backend_real": True,
        "used_in_dashboard": True,
        "component_class": ProductGrid,
        "demo_kind": "shop-product-grid",
        "files": [
            "ui/components/shop/product_grid.py",
            "ui/templates/shop/product_grid.html",
            "shop/views.py",
        ],
        "dashboard_refs": [
            "shop:public_catalog",
            "shop:student_required_modal",
        ],
    },
    {
        "slug": "shop-product-detail-drawer",
        "family": "shop",
        "name": "shop.product_detail_drawer",
        "label": "Drawer Détail",
        "description": "Drawer produit avec variantes, stock et ajout au panier.",
        "states": ["ouvert", "fermé", "loading"],
        "backend_status": "Backend branché",
        "backend_real": True,
        "used_in_dashboard": True,
        "component_class": ProductDetailDrawer,
        "demo_kind": "shop-product-detail-drawer",
        "files": [
            "ui/components/shop/product_detail_drawer.py",
            "ui/templates/shop/product_detail_drawer.html",
            "shop/views.py",
            "shop/services/shop_service.py",
        ],
        "dashboard_refs": [
            "shop:public_catalog",
            "shop:student_order_detail",
        ],
    },
]

DOMAIN_COMPONENTS_BY_SLUG = {component["slug"]: component for component in DOMAIN_COMPONENTS}


def _domain_component_family_data(request):
    families = []
    family_index = {family["id"]: {**family, "components": []} for family in DOMAIN_FAMILIES}
    for component in DOMAIN_COMPONENTS:
        dashboard_links = []
        for route_name in component.get("dashboard_refs", []):
            try:
                dashboard_links.append({"label": route_name, "url": reverse(route_name)})
            except Exception:
                dashboard_links.append({"label": route_name, "url": "#"})
        enriched = {
            **component,
            "detail_url": reverse("ui:system_domain_component", kwargs={"slug": component["slug"]}),
            "demo_url": reverse("ui:system_domain_demo", kwargs={"slug": component["slug"]}),
            "dashboard_links": dashboard_links,
        }
        family_index[component["family"]]["components"].append(enriched)
    for family in DOMAIN_FAMILIES:
        families.append(family_index[family["id"]])
    return families


def _resolve_shop_branch(user):
    branch = get_user_branch(user)
    if branch:
        return branch
    return Branch.objects.filter(is_active=True).order_by("name").first()


def _resolve_student_profile(user):
    student = getattr(user, "student_profile", None)
    if student:
        return student
    return (
        Student.objects.select_related("user", "inscription__candidature")
        .filter(is_active=True)
        .order_by("-created_at")
        .first()
    )


def _format_fcfa(value):
    try:
        amount = int(value)
    except (TypeError, ValueError):
        return "0 FCFA"
    return f"{amount:,}".replace(",", " ") + " FCFA"


def _build_demo_kwargs(request, component):
    name = component["name"]
    if name == "account.profile_card":
        profile = Profile.objects.filter(user=request.user).select_related("user").first()
        branch = get_user_branch(request.user)
        return {
            "user": request.user,
            "display_name": request.user.get_full_name() or request.user.get_username(),
            "avatar_url": profile.avatar_url if profile else "",
            "role": getattr(getattr(request.user, "profile", None), "get_position_display", lambda: "")() or "Utilisateur",
            "branch": getattr(branch, "name", ""),
            "status": "active",
            "status_label": "Actif",
            "profile_url": reverse("accounts_portal:system_profile"),
        }
    if name == "account.profile_dropdown":
        return {
            "user": request.user,
            "display_name": request.user.get_full_name() or request.user.get_username(),
            "avatar_url": getattr(getattr(request.user, "profile", None), "avatar_url", "") or "",
            "role": getattr(getattr(request.user, "profile", None), "get_position_display", lambda: "")(),
            "profile_url": reverse("accounts_portal:system_profile"),
            "edit_url": reverse("accounts_portal:system_profile_edit"),
            "security_url": reverse("accounts_portal:system_security"),
            "preferences_url": reverse("accounts:edit_preferences"),
            "logout_url": reverse("accounts:logout"),
        }
    if name == "account.profile_view":
        profile = Profile.objects.filter(user=request.user).select_related("user").first()
        return {
            "display_name": request.user.get_full_name() or request.user.get_username(),
            "avatar_url": profile.avatar_url if profile else "",
            "email": request.user.email,
            "phone": getattr(profile, "phone", "") if profile else "",
            "address": getattr(profile, "address", "") if profile else "",
            "role": getattr(getattr(request.user, "profile", None), "get_position_display", lambda: "")(),
            "branch": getattr(get_user_branch(request.user), "name", ""),
            "status": "active",
            "status_label": "Actif",
            "created_at": getattr(profile, "created_at", None) and profile.created_at.strftime("%B %Y") or "",
            "last_seen": getattr(profile, "last_seen", None) and profile.last_seen.strftime("%d/%m/%Y %H:%M") or "",
            "extra_fields": [
                {"label": "Rôle", "value": getattr(getattr(request.user, "profile", None), "get_position_display", lambda: "")()},
            ],
        }
    if name == "account.profile_editor":
        profile = Profile.objects.filter(user=request.user).select_related("user").first() or Profile(user=request.user)
        form = SystemProfileForm(instance=profile, user=request.user)
        return {
            "form": form,
            "hx_post": reverse("accounts_portal:system_profile_edit"),
            "hx_target": "#profile-editor-container",
        }
    if name == "account.security_settings":
        password_form = PasswordChangeForm(user=request.user)
        return {
            "password_form": password_form,
            "hx_post": reverse("accounts_portal:system_change_password"),
            "hx_target": "#security-container",
            "sessions": [],
        }
    if name == "account.preference_settings":
        preference = UserPreference.objects.filter(user=request.user).select_related("user").first() or UserPreference(user=request.user)
        form = UserPreferenceForm(instance=preference)
        return {
            "form": form,
            "hx_post": reverse("accounts:edit_preferences"),
            "hx_target": "#preferences-container",
        }
    if name == "notifications.bell":
        unread_count = get_user_unread_count(request.user)
        return {
            "unread_count": unread_count,
            "preview_url": reverse("notification_center:notifications_widget"),
            "preview_target": "#notification-dropdown-content",
            "center_url": reverse("notification_center:notifications"),
            "center_target": "#director-workspace",
        }
    if name == "notifications.badge":
        return {"count": get_user_unread_count(request.user), "max_count": 99}
    if name == "notifications.item":
        notifications = get_user_in_app_messages(request.user, limit=1)
        notification = notifications[0] if notifications else None
        return {
            "notification_id": getattr(notification, "id", "demo"),
            "title": getattr(notification, "title", "Nouvelle notification"),
            "summary": getattr(notification, "summary", "Aucune notification récente disponible."),
            "icon": "bell",
            "source": getattr(notification, "source", "Centre de notifications"),
            "time_ago": "à l'instant",
            "is_read": bool(getattr(notification, "read_at", None)),
            "priority": getattr(notification, "priority", "normal"),
            "action_url": reverse("notification_center:notifications"),
            "hx_mark_read": getattr(notification, "mark_read_url", ""),
        }
    if name == "notifications.list":
        notifications = []
        for message in get_user_in_app_messages(request.user, limit=5):
            notifications.append(
                {
                    "id": message.id,
                    "title": getattr(message, "title", "Notification"),
                    "summary": getattr(message, "summary", "") or getattr(message, "body", ""),
                    "icon": "bell",
                    "source": getattr(message, "source", "Centre de notifications"),
                    "time_ago": "à l'instant",
                    "is_read": bool(getattr(message, "read_at", None)),
                    "priority": getattr(message, "priority", "normal"),
                    "action_url": reverse("notification_center:notifications"),
                    "hx_mark_read": reverse("notification_center:mark_notification_read", kwargs={"pk": message.pk}),
                }
            )
        return {
            "notifications": notifications,
            "empty_message": "Aucune notification récente.",
            "mark_all_read_url": reverse("notification_center:mark_all_notifications_read"),
        }
    if name == "notifications.drawer":
        return {
            "drawer_id": "notification-drawer-demo",
            "title": "Notifications",
            "hx_load": reverse("notification_center:notifications_widget"),
            "mark_all_read_url": reverse("notification_center:mark_all_notifications_read"),
            "center_url": reverse("notification_center:notifications"),
        }
    if name == "student.identity_card":
        student = _resolve_student_profile(request.user)
        if student:
            branch = getattr(getattr(student.inscription, "candidature", None), "branch", None)
            return {
                "student": student,
                "matricule": student.matricule,
                "full_name": student.full_name,
                "photo_url": getattr(getattr(student, "photo", None), "url", "") or "",
                "classe": getattr(getattr(student, "current_academic_enrollment", None), "academic_class", None) and getattr(student.current_academic_enrollment.academic_class, "name", "") or "",
                "niveau": getattr(student.programme, "title", ""),
                "filiere": getattr(student.programme, "title", ""),
                "branch": getattr(branch, "name", ""),
                "is_active": student.is_active,
                "detail_url": "#",
            }
        return {}
    if name == "student.status_card":
        student = _resolve_student_profile(request.user)
        if student:
            return {
                "student": student,
                "status": "promoted",
                "status_label": "Promu",
                "decision_date": "15 juin 2026",
                "validation_academic": "Validé",
                "validation_finance": "En attente",
            }
        return {}
    if name == "student.progress_card":
        student = _resolve_student_profile(request.user)
        if student:
            return {
                "title": "Progression académique",
                "items": [
                    {"label": "Semestre 1", "percentage": 70},
                    {"label": "Semestre 2", "percentage": 62},
                ],
                "overall_percentage": 66,
                "overall_label": "Progression globale",
            }
        return {}
    branch = _resolve_shop_branch(request.user)
    products = []
    if branch:
        products = list(
            ShopProduct.objects.filter(branch=branch, is_active=True)
            .prefetch_related("variants")
            .order_by("-is_required", "category", "name")[:6]
        )
    if name == "shop.product_card":
        product = products[0] if products else None
        if product:
            return {
                "product_id": product.pk,
                "name": product.name,
                "image_url": getattr(getattr(product, "image", None), "url", "") or "",
                "category": product.get_category_display(),
                "price": _format_fcfa(product.unit_price),
                "original_price": "",
                "stock": product.current_stock,
                "is_available": product.is_active,
                "action_url": reverse("shop:public_catalog", kwargs={"branch_slug": getattr(branch, "slug", "")}) if branch else "#",
            }
        return {}
    if name == "shop.product_grid":
        product_rows = []
        for product in products[:6]:
            product_rows.append(
                {
                    "id": product.pk,
                    "name": product.name,
                    "image_url": getattr(getattr(product, "image", None), "url", "") or "",
                    "category": product.get_category_display(),
                    "price": _format_fcfa(product.unit_price),
                    "stock": product.current_stock,
                    "is_available": product.is_active,
                    "action_url": reverse("shop:public_catalog", kwargs={"branch_slug": getattr(branch, "slug", "")}) if branch else "#",
                }
            )
        return {
            "products": product_rows,
            "empty_message": "Aucun produit disponible pour cette annexe.",
            "columns": 3,
        }
    if name == "shop.product_detail_drawer":
        product = products[0] if products else None
        if product:
            return {
                "drawer_id": "shop-detail-drawer-demo",
                "product": {
                    "name": product.name,
                    "image_url": getattr(getattr(product, "image", None), "url", "") or "",
                    "category": product.get_category_display(),
                    "description": product.description,
                    "price": _format_fcfa(product.unit_price),
                    "original_price": "",
                    "stock": product.current_stock,
                    "is_available": product.is_active,
                    "variants": [
                        {"name": variant.label, "extra_price": _format_fcfa(variant.extra_price)}
                        for variant in product.variants.filter(is_active=True)[:4]
                    ],
                },
                "hx_add_to_cart": reverse("shop:public_product_order", kwargs={"branch_slug": getattr(branch, "slug", ""), "pk": product.pk}) if branch else "",
            }
        return {}
    return {}


@ui_system_access
@require_http_methods(["GET"])
def ui_domain_catalog(request):
    scope = getattr(request, "access_scope", None) or {}
    branch = scope.get("branch")
    context = {
        "page_title": "Catalogue des composants métier",
        "domain_families": _domain_component_family_data(request),
        "domain_component_count": len(DOMAIN_COMPONENTS),
        "domain_backend_count": sum(1 for component in DOMAIN_COMPONENTS if component["backend_real"]),
        "domain_dashboard_count": sum(1 for component in DOMAIN_COMPONENTS if component["used_in_dashboard"]),
        "ui_system_url": reverse("ui:system"),
        "navigation_groups": _system_navigation(),
        "user_display_name": request.user.get_full_name() or request.user.get_username(),
        "user_role": scope.get("position") or scope.get("role") or "Utilisateur",
        "branch_name": getattr(branch, "name", "") if branch else "",
    }
    return render(request, "ui/system_domains.html", context)


@ui_system_access
@require_http_methods(["GET"])
def ui_domain_component_detail(request, slug):
    component = DOMAIN_COMPONENTS_BY_SLUG.get(slug)
    if not component:
        raise Http404("Composant introuvable.")
    context = {
        "component": {
            **component,
            "detail_url": reverse("ui:system_domain_component", kwargs={"slug": slug}),
            "demo_url": reverse("ui:system_domain_demo", kwargs={"slug": slug}),
        },
        "demo_available": bool(component["backend_real"]),
    }
    return render(request, "ui/partials/system_domain_detail.html", context)


@ui_system_access
@require_http_methods(["GET"])
def ui_domain_component_demo(request, slug):
    component = DOMAIN_COMPONENTS_BY_SLUG.get(slug)
    if not component:
        raise Http404("Composant introuvable.")
    kwargs = _build_demo_kwargs(request, component)
    if not kwargs and component["backend_real"]:
        return render(
            request,
            "ui/partials/system_domain_demo.html",
            {"component": component, "demo_html": "<div class='rounded-ui-card border border-ui-border bg-ui-surface p-4 text-sm text-ui-text-muted'>Aucune donnée de démonstration disponible.</div>"},
        )
    demo_html = component["component_class"].render(kwargs=kwargs)
    return render(
        request,
        "ui/partials/system_domain_demo.html",
        {
            "component": component,
            "demo_html": demo_html,
        },
    )
