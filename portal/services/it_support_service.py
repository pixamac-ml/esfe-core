from __future__ import annotations

import secrets
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Q, Sum
from django.utils import timezone

from academics.models import AcademicEnrollment, ECGrade, Semester
from accounts.access import get_user_annexe
from inscriptions.models import Inscription
from payments.models import Payment, PaymentAgent
from portal.models import AccountSupportState, SupportAuditLog, SupportTicket, SupportTicketComment
from students.models import Student


def get_scoped_staff_queryset(*, branch):
    user_model = get_user_model()
    queryset = user_model.objects.select_related("profile").filter(
        Q(is_staff=True) | Q(profile__user_type="staff")
    ).distinct()
    if branch:
        queryset = queryset.filter(
            Q(profile__branch=branch)
            | Q(payment_agent_profile__branch=branch)
            | Q(managed_branches=branch)
        ).distinct()
    return queryset.order_by("first_name", "last_name", "username")


def get_scoped_student_queryset(*, branch):
    queryset = Student.objects.select_related(
        "user",
        "inscription__candidature__branch",
        "inscription__candidature__programme",
    )
    if branch:
        queryset = queryset.filter(inscription__candidature__branch=branch)
    return queryset.order_by(
        "inscription__candidature__last_name",
        "inscription__candidature__first_name",
        "matricule",
    )


def search_support_entities(*, branch, query):
    query = (query or "").strip()
    if len(query) < 2:
        return {"query": query, "students": [], "staff": [], "inscriptions": []}

    students = list(
        get_scoped_student_queryset(branch=branch).filter(
            Q(matricule__icontains=query)
            | Q(inscription__candidature__first_name__icontains=query)
            | Q(inscription__candidature__last_name__icontains=query)
            | Q(user__username__icontains=query)
            | Q(inscription__candidature__email__icontains=query)
        )[:8]
    )
    staff = list(
        get_scoped_staff_queryset(branch=branch).filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
            | Q(profile__employee_code__icontains=query)
        )[:8]
    )
    inscription_qs = Inscription.objects.select_related("candidature__branch", "candidature__programme")
    if branch:
        inscription_qs = inscription_qs.filter(candidature__branch=branch)
    inscriptions = list(
        inscription_qs.filter(
            Q(public_token__icontains=query)
            | Q(candidature__first_name__icontains=query)
            | Q(candidature__last_name__icontains=query)
        )[:6]
    )
    return {"query": query, "students": students, "staff": staff, "inscriptions": inscriptions}


def build_diagnostic_payload(*, branch, kind, object_id):
    if kind == "student":
        return _build_student_diagnostic(branch=branch, student_id=object_id)
    if kind == "staff":
        return _build_staff_diagnostic(branch=branch, user_id=object_id)
    if kind == "inscription":
        return _build_inscription_diagnostic(branch=branch, inscription_id=object_id)
    return None


def create_temp_password():
    return secrets.token_urlsafe(8).replace("-", "A").replace("_", "B")


def log_support_action(*, actor, branch, action_type, target_user=None, target_label="", details=""):
    return SupportAuditLog.objects.create(
        actor=actor,
        branch=branch,
        target_user=target_user,
        target_label=target_label,
        action_type=action_type,
        details=details,
    )


def get_recent_support_logs(*, branch, limit=8):
    queryset = SupportAuditLog.objects.select_related("actor", "target_user", "branch")
    if branch:
        queryset = queryset.filter(branch=branch)
    return list(queryset.order_by("-created_at", "-id")[:limit])


def get_support_ticket_queryset(*, branch, status=""):
    queryset = SupportTicket.objects.select_related(
        "branch",
        "requester_user",
        "student__user",
        "student__inscription__candidature",
        "inscription__candidature",
        "assigned_to",
        "created_by",
    ).prefetch_related("comments")
    if branch:
        queryset = queryset.filter(branch=branch)
    if status:
        queryset = queryset.filter(status=status)
    return queryset.order_by("-created_at", "-id")


def get_support_ticket_metrics(*, branch):
    queryset = get_support_ticket_queryset(branch=branch)
    return {
        "open": queryset.filter(status=SupportTicket.STATUS_OPEN).count(),
        "in_progress": queryset.filter(status=SupportTicket.STATUS_IN_PROGRESS).count(),
        "resolved": queryset.filter(status=SupportTicket.STATUS_RESOLVED).count(),
        "critical": queryset.filter(priority=SupportTicket.PRIORITY_CRITICAL).exclude(
            status__in=[SupportTicket.STATUS_RESOLVED, SupportTicket.STATUS_REJECTED]
        ).count(),
    }


def create_support_ticket(
    *,
    actor,
    branch,
    title,
    description="",
    category=SupportTicket.CATEGORY_OTHER,
    priority=SupportTicket.PRIORITY_NORMAL,
    requester_user=None,
    student=None,
    inscription=None,
):
    title = (title or "").strip()
    if not title:
        raise ValueError("Le titre du ticket est obligatoire.")
    ticket = SupportTicket.objects.create(
        branch=branch,
        title=title[:180],
        description=(description or "").strip(),
        category=category if category in dict(SupportTicket.CATEGORY_CHOICES) else SupportTicket.CATEGORY_OTHER,
        priority=priority if priority in dict(SupportTicket.PRIORITY_CHOICES) else SupportTicket.PRIORITY_NORMAL,
        requester_user=requester_user,
        student=student,
        inscription=inscription,
        created_by=actor,
    )
    log_support_action(
        actor=actor,
        branch=branch,
        action_type="ticket_created",
        target_user=requester_user,
        target_label=f"Ticket #{ticket.id}",
        details=ticket.title,
    )
    return ticket


def assign_support_ticket(*, actor, branch, ticket):
    ticket.assigned_to = actor
    if ticket.status == SupportTicket.STATUS_OPEN:
        ticket.status = SupportTicket.STATUS_IN_PROGRESS
    ticket.save(update_fields=["assigned_to", "status", "updated_at"])
    log_support_action(
        actor=actor,
        branch=branch,
        action_type="ticket_assigned",
        target_user=ticket.requester_user,
        target_label=f"Ticket #{ticket.id}",
        details=ticket.title,
    )
    return ticket


def update_support_ticket_status(*, actor, branch, ticket, status, resolution=""):
    if status not in dict(SupportTicket.STATUS_CHOICES):
        raise ValueError("Statut ticket invalide.")
    ticket.status = status
    if status in {SupportTicket.STATUS_RESOLVED, SupportTicket.STATUS_REJECTED}:
        ticket.resolved_by = actor
        ticket.resolved_at = timezone.now()
        ticket.resolution = (resolution or ticket.resolution or "").strip()
        update_fields = ["status", "resolved_by", "resolved_at", "resolution", "updated_at"]
    else:
        ticket.resolved_by = None
        ticket.resolved_at = None
        update_fields = ["status", "resolved_by", "resolved_at", "updated_at"]
    ticket.save(update_fields=update_fields)
    log_support_action(
        actor=actor,
        branch=branch,
        action_type="ticket_status_changed",
        target_user=ticket.requester_user,
        target_label=f"Ticket #{ticket.id}",
        details=f"{ticket.get_status_display()} - {ticket.title}",
    )
    return ticket


def add_support_ticket_comment(*, actor, branch, ticket, body):
    body = (body or "").strip()
    if not body:
        raise ValueError("Le commentaire est obligatoire.")
    comment = SupportTicketComment.objects.create(ticket=ticket, author=actor, body=body)
    log_support_action(
        actor=actor,
        branch=branch,
        action_type="ticket_commented",
        target_user=ticket.requester_user,
        target_label=f"Ticket #{ticket.id}",
        details=body[:255],
    )
    return comment


def can_manage_user_in_branch(*, branch, target_user):
    if branch is None:
        return True
    student_profile = getattr(target_user, "student_profile", None)
    if student_profile is not None:
        return getattr(student_profile.inscription.candidature, "branch", None) == branch
    return get_user_annexe(target_user) == branch


def get_account_support_state(user):
    state, _created = AccountSupportState.objects.get_or_create(user=user)
    return state


def suspend_account(*, actor, branch, target_user, reason=""):
    state = get_account_support_state(target_user)
    state.is_suspended = True
    state.note = (reason or state.note or "").strip()
    state.updated_by = actor
    state.save(update_fields=["is_suspended", "note", "updated_by", "updated_at"])
    target_user.is_active = False
    target_user.save(update_fields=["is_active"])
    log_support_action(
        actor=actor,
        branch=branch,
        action_type=SupportAuditLog.ACTION_ACCOUNT_SUSPENDED,
        target_user=target_user,
        target_label=target_user.get_full_name() or target_user.username,
        details=state.note or "Suspension compte via dashboard IT.",
    )
    return state


def reactivate_account(*, actor, branch, target_user):
    state = get_account_support_state(target_user)
    state.is_suspended = False
    state.is_blocked = False
    state.blocked_until = None
    state.failed_login_count = 0
    state.updated_by = actor
    state.save(update_fields=["is_suspended", "is_blocked", "blocked_until", "failed_login_count", "updated_by", "updated_at"])
    target_user.is_active = True
    target_user.save(update_fields=["is_active"])
    log_support_action(
        actor=actor,
        branch=branch,
        action_type=SupportAuditLog.ACTION_ACCOUNT_REACTIVATED,
        target_user=target_user,
        target_label=target_user.get_full_name() or target_user.username,
        details="Reactivation compte via dashboard IT.",
    )
    return state


def unblock_account(*, actor, branch, target_user):
    state = get_account_support_state(target_user)
    state.is_blocked = False
    state.blocked_until = None
    state.failed_login_count = 0
    state.updated_by = actor
    state.save(update_fields=["is_blocked", "blocked_until", "failed_login_count", "updated_by", "updated_at"])
    if not state.is_suspended and not target_user.is_active:
        target_user.is_active = True
        target_user.save(update_fields=["is_active"])
    log_support_action(
        actor=actor,
        branch=branch,
        action_type=SupportAuditLog.ACTION_ACCOUNT_UNBLOCKED,
        target_user=target_user,
        target_label=target_user.get_full_name() or target_user.username,
        details="Deblocage compte via dashboard IT.",
    )
    return state


def update_account_email(*, actor, branch, target_user, email):
    previous_email = target_user.email or ""
    target_user.email = (email or "").strip().lower()
    target_user.save(update_fields=["email"])
    log_support_action(
        actor=actor,
        branch=branch,
        action_type=SupportAuditLog.ACTION_EMAIL_UPDATED,
        target_user=target_user,
        target_label=target_user.get_full_name() or target_user.username,
        details=f"{previous_email or '-'} -> {target_user.email or '-'}",
    )
    return target_user


def _build_student_diagnostic(*, branch, student_id):
    queryset = get_scoped_student_queryset(branch=branch)
    student = queryset.filter(pk=student_id).first()
    if not student:
        return None

    inscription = student.inscription
    candidature = inscription.candidature
    enrollment = (
        student.user.academic_enrollments.select_related("academic_class", "academic_year", "programme", "branch")
        .filter(is_active=True)
        .first()
    )
    payments = list(
        inscription.payments.select_related("agent__user").order_by("-paid_at", "-id")[:5]
    )
    grade_qs = ECGrade.objects.filter(enrollment__student=student.user)
    semester_qs = Semester.objects.filter(academic_class=enrollment.academic_class).order_by("number") if enrollment else Semester.objects.none()

    return {
        "kind": "student",
        "title": f"{student.full_name} ({student.matricule})",
        "subtitle": candidature.branch.name,
        "target_user_id": student.user_id,
        "account_active": student.user.is_active,
        "support_state": get_account_support_state(student.user),
        "sections": [
            {
                "title": "Identite et compte",
                "rows": [
                    ("Username", student.user.username),
                    ("Email", student.user.email or candidature.email or "-"),
                    ("Compte actif", "Oui" if student.user.is_active else "Non"),
                    ("Etudiant actif", "Oui" if student.is_active else "Non"),
                    ("Programme", candidature.programme.title),
                    ("Annexe", candidature.branch.name),
                ],
            },
            {
                "title": "Inscription et paiements",
                "rows": [
                    ("Statut inscription", inscription.get_status_display()),
                    ("Montant du", f"{inscription.amount_due} FCFA"),
                    ("Montant paye", f"{inscription.amount_paid} FCFA"),
                    ("Solde", f"{inscription.balance} FCFA"),
                    ("Paiements valides", str(inscription.payments.filter(status=Payment.STATUS_VALIDATED).count())),
                    ("Reference", str(inscription.reference)),
                ],
            },
            {
                "title": "Academique",
                "rows": [
                    ("Inscription academique active", "Oui" if enrollment else "Non"),
                    ("Classe", enrollment.academic_class.display_name if enrollment else "-"),
                    ("Annee", enrollment.academic_year.name if enrollment else "-"),
                    ("Notes saisies", str(grade_qs.count())),
                    ("Semestres", str(semester_qs.count())),
                    ("Dernier paiement", timezone.localtime(payments[0].paid_at).strftime("%d/%m/%Y %H:%M") if payments else "-"),
                ],
            },
        ],
        "recent_items": [
            f"{payment.amount} FCFA - {payment.get_status_display()} - {timezone.localtime(payment.paid_at).strftime('%d/%m/%Y')}"
            for payment in payments
        ],
        "issues": _collect_student_issues(student=student, enrollment=enrollment, grade_qs=grade_qs),
    }


def _build_staff_diagnostic(*, branch, user_id):
    user_model = get_user_model()
    user = get_scoped_staff_queryset(branch=branch).filter(pk=user_id).first()
    if not user:
        return None

    profile = user.profile
    payment_agent = PaymentAgent.objects.select_related("branch").filter(user=user).first()
    branch_label = getattr(get_user_annexe(user), "name", "-")
    return {
        "kind": "staff",
        "title": user.get_full_name() or user.username,
        "subtitle": branch_label,
        "target_user_id": user.id,
        "account_active": user.is_active,
        "support_state": get_account_support_state(user),
        "sections": [
            {
                "title": "Compte et acces",
                "rows": [
                    ("Username", user.username),
                    ("Email", user.email or "-"),
                    ("Compte actif", "Oui" if user.is_active else "Non"),
                    ("Role profil", profile.get_role_display() or "-"),
                    ("Position", profile.get_position_display() or "-"),
                    ("Code employe", profile.employee_code or "-"),
                ],
            },
            {
                "title": "Affectation",
                "rows": [
                    ("Annexe", branch_label),
                    ("Type utilisateur", profile.get_user_type_display() or "-"),
                    ("Statut emploi", profile.get_employment_status_display() or "-"),
                    ("Agent de paiement", "Oui" if payment_agent else "Non"),
                    ("Annexe agent paiement", payment_agent.branch.name if payment_agent else "-"),
                    ("Groupes", ", ".join(user.groups.values_list("name", flat=True)) or "-"),
                ],
            },
        ],
        "recent_items": [],
        "issues": _collect_staff_issues(user=user, payment_agent=payment_agent),
    }


def _build_inscription_diagnostic(*, branch, inscription_id):
    queryset = Inscription.objects.select_related("candidature__branch", "candidature__programme")
    if branch:
        queryset = queryset.filter(candidature__branch=branch)
    inscription = queryset.filter(pk=inscription_id).first()
    if not inscription:
        return None

    student = getattr(inscription, "student", None)
    enrollment = getattr(inscription, "academic_enrollment", None)
    validated_total = inscription.payments.filter(status=Payment.STATUS_VALIDATED).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return {
        "kind": "inscription",
        "title": f"{inscription.candidature.first_name} {inscription.candidature.last_name}",
        "subtitle": inscription.candidature.branch.name,
        "target_user_id": student.user_id if student else None,
        "account_active": student.user.is_active if student else False,
        "support_state": get_account_support_state(student.user) if student else None,
        "sections": [
            {
                "title": "Dossier administratif",
                "rows": [
                    ("Reference", str(inscription.reference)),
                    ("Token public", inscription.public_token),
                    ("Statut", inscription.get_status_display()),
                    ("Programme", inscription.candidature.programme.title),
                    ("Annexe", inscription.candidature.branch.name),
                    ("Etudiant cree", "Oui" if student else "Non"),
                ],
            },
            {
                "title": "Flux financiers et academiques",
                "rows": [
                    ("Montant du", f"{inscription.amount_due} FCFA"),
                    ("Montant valide", f"{validated_total} FCFA"),
                    ("Solde", f"{inscription.balance} FCFA"),
                    ("Inscription academique", "Oui" if enrollment else "Non"),
                    ("Classe", enrollment.academic_class.display_name if enrollment else "-"),
                    ("Annee", enrollment.academic_year.name if enrollment else "-"),
                ],
            },
        ],
        "recent_items": [],
        "issues": _collect_inscription_issues(inscription=inscription, student=student, enrollment=enrollment),
    }


def _collect_student_issues(*, student, enrollment, grade_qs):
    issues = []
    if not student.user.is_active:
        issues.append("Le compte utilisateur est desactive.")
    if not student.is_active:
        issues.append("Le profil etudiant est desactive.")
    if not enrollment:
        issues.append("Aucune inscription academique active n'est rattachee.")
    if enrollment and grade_qs.count() == 0:
        issues.append("Aucune note n'est encore saisie pour cet etudiant.")
    if student.inscription.balance > 0 and student.inscription.status == Inscription.STATUS_ACTIVE:
        issues.append("L'inscription est active alors qu'un solde reste a regler.")
    return issues or ["Aucune incoherence critique detectee."]


def _collect_staff_issues(*, user, payment_agent):
    issues = []
    profile = user.profile
    if not profile.position:
        issues.append("La position metier n'est pas renseignee.")
    if not profile.branch and not payment_agent:
        issues.append("Aucune annexe n'est rattachee a ce compte staff.")
    if not profile.employee_code:
        issues.append("Le code employe est manquant.")
    return issues or ["Aucune incoherence critique detectee."]


def _collect_inscription_issues(*, inscription, student, enrollment):
    issues = []
    if not student:
        issues.append("Aucun compte etudiant n'a encore ete cree.")
    if student and not enrollment:
        issues.append("Le compte etudiant existe sans affectation academique.")
    if inscription.amount_paid == 0:
        issues.append("Aucun paiement valide n'est enregistre.")
    return issues or ["Aucune incoherence critique detectee."]
