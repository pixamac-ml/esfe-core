# ════════════════════════════════════════════════════════════════
#  Ajouts à secretary/services.py
#  Coller à la fin du fichier existant (ou intégrer proprement)
# ════════════════════════════════════════════════════════════════

# ── Import supplémentaires à ajouter en haut de services.py ──
# from news.models import ResultSession
# from shop.models import ShopOrder
# from django.db.models import Q

from django.urls import reverse


def get_academic_results(*, branch=None, limit=20):
    """
    Résultats académiques publiés — lecture seule pour la secrétaire.
    Filtre par annexe si branch fournie.
    """
    from news.models import ResultSession
    qs = ResultSession.objects.filter(is_published=True).order_by("-annee_academique", "filiere", "classe")
    if branch:
        # ResultSession a un champ `annexe` (nom de l'antenne / branch)
        qs = qs.filter(annexe__icontains=branch.name) if hasattr(branch, "name") else qs
    return qs[:limit]


def get_pending_shop_orders(*, branch=None, limit=10):
    """
    Commandes shop en attente de paiement ou prêtes à livrer.
    La secrétaire peut voir + marquer comme remise (statut 'ready' → 'delivered').
    Elle ne peut PAS modifier prix ni valider paiement.
    """
    from shop.models import ShopOrder
    from django.db.models import Q
    qs = ShopOrder.objects.select_related(
        "inscription__candidature",
        "inscription__candidature__programme",
    ).filter(
        Q(status=ShopOrder.STATUS_PENDING_PAYMENT) | Q(status=ShopOrder.STATUS_READY)
    ).exclude(
        status=ShopOrder.STATUS_DELIVERED
    ).order_by("status", "-created_at")
    if branch:
        qs = qs.filter(branch=branch)
    return qs[:limit]


def get_quick_actions():
    """
    Retourne la liste des 6 actions rapides pour la grille du dashboard.
    Chaque action est un dict avec label, url, icon, bg, color.
    """
    return [
        {
            "label": "Saisir registre",
            "url": reverse("secretary:registry_create"),
            "icon": "book-plus",
            "bg": "bg-sky-50 dark:bg-sky-950/50",
            "color": "text-sky-600 dark:text-sky-300",
        },
        {
            "label": "Créer tâche",
            "url": reverse("secretary:task_create"),
            "icon": "list-plus",
            "bg": "bg-rose-50 dark:bg-rose-950/50",
            "color": "text-rose-600 dark:text-rose-300",
        },
        {
            "label": "Programmer RDV",
            "url": reverse("secretary:appointment_create"),
            "icon": "calendar-plus",
            "bg": "bg-emerald-50 dark:bg-emerald-950/50",
            "color": "text-emerald-600 dark:text-emerald-300",
        },
        {
            "label": "Recevoir pièce",
            "url": reverse("secretary:document_receipt_create"),
            "icon": "file-plus",
            "bg": "bg-amber-50 dark:bg-amber-950/50",
            "color": "text-amber-600 dark:text-amber-300",
        },
        {
            "label": "Nouvelle visite",
            "url": reverse("secretary:visitor_create"),
            "icon": "user-plus",
            "bg": "bg-violet-50 dark:bg-violet-950/50",
            "color": "text-violet-600 dark:text-violet-300",
        },
        {
            "label": "Rechercher étudiant",
            "url": reverse("secretary:htmx_student_results"),
            "icon": "search",
            "bg": "bg-teal-50 dark:bg-teal-950/50",
            "color": "text-teal-600 dark:text-teal-300",
        },
    ]


def get_nav_links(pending_registry_count, pending_documents_count,
                  appointments_today, active_visits, pending_tasks):
    """
    Liens de navigation sidebar avec compteurs live.
    """
    return [
        {
            "label": "Registre",
            "url": reverse("secretary:registry_list"),
            "icon": "book-copy",
            "color": "text-sky-500",
            "count": pending_registry_count or None,
        },
        {
            "label": "Rendez-vous",
            "url": reverse("secretary:appointment_list"),
            "icon": "calendar-check-2",
            "color": "text-emerald-500",
            "count": appointments_today or None,
        },
        {
            "label": "Visites",
            "url": reverse("secretary:visitor_list"),
            "icon": "user-round-search",
            "color": "text-violet-500",
            "count": active_visits or None,
        },
        {
            "label": "Tâches",
            "url": reverse("secretary:task_list"),
            "icon": "check-square",
            "color": "text-rose-500",
            "count": pending_tasks or None,
        },
        {
            "label": "Documents",
            "url": reverse("secretary:document_receipt_list"),
            "icon": "file-signature",
            "color": "text-amber-500",
            "count": pending_documents_count or None,
        },
    ]


# ════════════════════════════════════════════════════════════════
#  Remplacer get_secretary_dashboard_data dans services.py
# ════════════════════════════════════════════════════════════════

def get_secretary_dashboard_data(user):
    """
    Version améliorée — intègre résultats, shop, actions rapides, nav.
    """
    from .selectors import (
        get_active_students,
        get_active_visits_queryset,
        get_documents_queryset,
        get_pending_tasks,
        get_recent_documents_queryset,
        get_recent_registry_entries,
        get_registry_queryset,
        get_secretary_notifications,
        get_today_appointments_queryset,
        get_today_visits_queryset,
        get_unread_messages_count,
    )
    from accounts.dashboards.helpers import get_user_branch

    branch = get_user_branch(user)

    # ── Querysets de base ──
    active_students   = get_active_students(user=user, branch=branch)
    today_appts       = get_today_appointments_queryset(user=user, branch=branch)
    today_visits      = get_today_visits_queryset(user=user, branch=branch)
    active_visits     = get_active_visits_queryset(user=user, branch=branch)
    pending_tasks_qs  = get_pending_tasks(user=user, branch=branch)

    pending_registry_qs = get_registry_queryset(
        {"status": "pending", "archived": False, "active_only": True},
        user=user, branch=branch,
    )
    pending_docs_qs = get_documents_queryset(
        {"status": "pending", "archived": False, "active_only": True},
        user=user, branch=branch,
    )

    # ── Compteurs (évaluation unique) ──
    pending_registry_count  = pending_registry_qs.count()
    pending_documents_count = pending_docs_qs.count()
    appointments_today      = today_appts.count()
    active_visits_count     = active_visits.count()
    pending_tasks_count     = pending_tasks_qs.count()

    # ── Nav + actions ──
    nav = get_nav_links(
        pending_registry_count, pending_documents_count,
        appointments_today, active_visits_count, pending_tasks_count,
    )

    return {
        # Méta
        "branch": branch,

        # Compteurs KPI
        "students_count":          active_students.count(),
        "appointments_today":      appointments_today,
        "visits_today":            today_visits.count(),
        "active_visits":           active_visits_count,
        "pending_tasks":           pending_tasks_count,
        "pending_registry_count":  pending_registry_count,
        "pending_documents_count": pending_documents_count,
        "messages_count":          get_unread_messages_count(user),

        # Rows ([:5] pour chaque flux)
        "pending_registry_rows":    pending_registry_qs[:5],
        "pending_documents_rows":   pending_docs_qs[:5],
        "today_appointments_rows":  today_appts[:5],
        "open_visits_rows":         active_visits[:5],
        "pending_tasks_rows":       pending_tasks_qs[:5],

        # Nouveaux blocs
        "academic_results":        get_academic_results(branch=branch),
        "pending_shop_orders":     get_pending_shop_orders(branch=branch),

        # UI helpers
        "quick_actions":           get_quick_actions(),
        "nav_links":               nav,
        "notifications":           get_secretary_notifications(user, limit=6),
    }
