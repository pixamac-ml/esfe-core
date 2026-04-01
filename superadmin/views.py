# superadmin/views.py
# FICHIER NETTOYÉ - SANS DOUBLONS - PRÊT POUR PRODUCTION

from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.decorators import user_passes_test
from django.http import HttpResponse, JsonResponse, FileResponse
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.db.models import Q, Count, Sum, F, Value, IntegerField, Exists, OuterRef, Min
from django.db.models.functions import Greatest
from django.utils.text import slugify
from django.utils import timezone
from datetime import timedelta
from io import BytesIO
import secrets
from urllib.parse import urlencode

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

# Imports des modèles
from formations.models import Programme, Cycle, Diploma, Fee, Filiere, ProgrammeYear, ProgrammeQuickFact, ProgrammeTab, ProgrammeSection, CompetenceBlock, CompetenceItem, RequiredDocument, ProgrammeRequiredDocument
from admissions.models import Candidature, CandidatureDocument
from blog.models import Article, Comment, Category as BlogCategory
from blog.forms import ArticleForm
from news.models import News, Event, EventType, MediaItem, ResultSession, Category as NewsCategory
from news.services import create_event_media_batch
from core.models import Institution, LegalPage, LegalSection, LegalSidebarBlock, Partner, ContactMessage, Testimonial, Notification
from inscriptions.models import Inscription, StatusHistory
from payments.models import Payment, PaymentAgent, CashPaymentSession
from students.models import Student
from branches.models import Branch
from accounts.models import Profile
from community.models import Category as CommunityCategory, Topic, Answer
from .models import SuperadminCockpitPreference
from students.services.email import send_payment_confirmation_email

User = get_user_model()

MANAGED_STAFF_GROUPS = (
    'admissions_managers',
    'finance_agents',
    'executive_director',
    'gestionnaire',
)


def _managed_groups_queryset():
    for group_name in MANAGED_STAFF_GROUPS:
        Group.objects.get_or_create(name=group_name)
    return Group.objects.filter(name__in=MANAGED_STAFF_GROUPS).order_by('name')


# ============================================
# DECORATOR - Superuser Required
# ============================================

def superuser_required(user):
    return bool(user.is_authenticated and user.is_superuser)


def _missing_superadmin_view(name):
    @user_passes_test(superuser_required, login_url='/accounts/login/')
    def _view(request, *args, **kwargs):
        if request.headers.get('HX-Request'):
            return HttpResponse(status=204)
        messages.warning(
            request,
            f"La fonctionnalite '{name}' est temporairement indisponible.",
        )
        return redirect('superadmin:dashboard')

    _view.__name__ = name
    return _view


# Keep URL imports stable even if some optional modules/views are not yet restored.
_MISSING_SUPERADMIN_VIEWS = [
    'branch_create', 'branch_delete', 'branch_edit', 'branch_list',
    'bulk_action',
    'community_answer_delete', 'community_answer_detail', 'community_answer_edit', 'community_answer_list',
    'community_category_create', 'community_category_delete', 'community_category_edit', 'community_category_list',
    'community_topic_delete', 'community_topic_detail', 'community_topic_edit', 'community_topic_list',
    'competence_block_create', 'competence_block_delete', 'competence_block_edit', 'competence_block_list',
    'competence_item_create', 'competence_item_delete', 'competence_item_edit', 'competence_item_list',
    'export_data',
    'message_delete', 'message_detail', 'message_list',
    'partner_create', 'partner_delete', 'partner_edit', 'partner_list',
    'programme_required_document_create', 'programme_required_document_delete', 'programme_required_document_list',
    'programme_section_create', 'programme_section_delete', 'programme_section_edit', 'programme_section_list',
    'programme_tab_create', 'programme_tab_delete', 'programme_tab_edit', 'programme_tab_list',
    'programme_year_create', 'programme_year_delete', 'programme_year_edit', 'programme_year_list',
    'quick_fact_create', 'quick_fact_delete', 'quick_fact_edit', 'quick_fact_list',
    'required_document_create', 'required_document_delete', 'required_document_edit', 'required_document_list',
    'search_global', 'settings',
    'testimonial_create', 'testimonial_delete', 'testimonial_edit', 'testimonial_list',
    'toggle_branch', 'toggle_community_answer', 'toggle_community_category', 'toggle_community_topic',
    'toggle_partner', 'toggle_testimonial',
    'update_message_status',
]

for _missing_name in _MISSING_SUPERADMIN_VIEWS:
    if _missing_name not in globals():
        globals()[_missing_name] = _missing_superadmin_view(_missing_name)


def _get_cockpit_pref(user):
    pref, _ = SuperadminCockpitPreference.objects.get_or_create(user=user)
    return pref


def _resolve_period_days(period_key):
    mapping = {
        SuperadminCockpitPreference.PERIOD_7D: 7,
        SuperadminCockpitPreference.PERIOD_30D: 30,
        SuperadminCockpitPreference.PERIOD_QUARTER: 90,
    }
    return mapping.get(period_key, 7)


def _period_bounds(today, period_key):
    days = _resolve_period_days(period_key)
    current_start = today - timedelta(days=days - 1)
    prev_end = current_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    return days, current_start, prev_start, prev_end


def _resolve_date_field(model, candidates):
    """Retourne le premier champ date/datetime disponible sur un modèle."""
    available = {f.name: f for f in model._meta.get_fields() if getattr(f, 'name', None)}
    for name in candidates:
        field = available.get(name)
        if field and field.get_internal_type() in ('DateField', 'DateTimeField'):
            return name, field.get_internal_type() == 'DateTimeField'
    return None, False


def _range_count(model, field_name, is_datetime, start_date, end_date):
    if not field_name:
        return 0
    lookup = f'{field_name}__date__range' if is_datetime else f'{field_name}__range'
    return model.objects.filter(**{lookup: (start_date, end_date)}).count()


def _daily_series(model, field_name, is_datetime, day_list):
    if not field_name:
        return [0 for _ in day_list]

    series = []
    lookup = f'{field_name}__date' if is_datetime else field_name
    for day in day_list:
        series.append(model.objects.filter(**{lookup: day}).count())
    return series


def _log_inscription_history(inscription, previous_status, new_status, comment=''):
    StatusHistory.objects.create(
        inscription=inscription,
        previous_status=previous_status,
        new_status=new_status,
        comment=comment,
    )


def _change_inscription_status(inscription, new_status, comment=''):
    previous_status = inscription.status
    inscription.status = new_status
    inscription.save(update_fields=['status'])
    _log_inscription_history(inscription, previous_status, new_status, comment)


def _safe_delete(request, instance, *, success_message, protected_message, hx_redirect=None):
    """Supprime un objet en gérant les contraintes ProtectedError."""
    try:
        instance.delete()
        messages.success(request, success_message)
    except ProtectedError:
        messages.error(request, protected_message)

    if request.headers.get('HX-Request') and hx_redirect:
        return HttpResponse(status=200, headers={'HX-Redirect': hx_redirect})
    return None


def _render_inscription_certificate(inscription):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    candidature = inscription.candidature
    programme = candidature.programme

    pdf.setFillColor(colors.HexColor('#1e4f6f'))
    pdf.rect(0, height - 40 * mm, width, 40 * mm, stroke=0, fill=1)

    pdf.setFillColor(colors.white)
    pdf.setFont('Helvetica-Bold', 22)
    pdf.drawString(20 * mm, height - 20 * mm, "ATTESTATION D'INSCRIPTION")

    pdf.setFillColor(colors.black)
    pdf.setFont('Helvetica', 12)
    pdf.drawString(20 * mm, height - 60 * mm, f"Référence inscription : {inscription.public_token}")
    pdf.drawString(20 * mm, height - 70 * mm, f"Candidat : {candidature.full_name}")
    pdf.drawString(20 * mm, height - 80 * mm, f"Programme : {programme.title}")
    pdf.drawString(20 * mm, height - 90 * mm, f"Cycle : {programme.cycle.name if programme.cycle else '-'}")
    pdf.drawString(20 * mm, height - 100 * mm, f"Campus : {candidature.branch.name if candidature.branch else '-'}")
    pdf.drawString(20 * mm, height - 110 * mm, f"Année académique : {candidature.academic_year}")
    pdf.drawString(20 * mm, height - 120 * mm, f"Statut : {inscription.get_status_display()}")
    pdf.drawString(20 * mm, height - 130 * mm, f"Montant dû : {inscription.amount_due} FCFA")
    pdf.drawString(20 * mm, height - 140 * mm, f"Montant payé : {inscription.amount_paid} FCFA")

    pdf.setFont('Helvetica-Oblique', 10)
    pdf.drawString(20 * mm, 25 * mm, f"Document généré le {timezone.localtime().strftime('%d/%m/%Y à %H:%M')}")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="attestation-inscription-{inscription.pk}.pdf"'
    return response


# ============================================
# DASHBOARD
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def dashboard(request):
    """Dashboard principal avec statistiques"""
    pref = _get_cockpit_pref(request.user)
    period = request.GET.get('period') or pref.dashboard_period
    if period not in dict(SuperadminCockpitPreference.PERIOD_CHOICES):
        period = SuperadminCockpitPreference.PERIOD_7D

    if pref.dashboard_period != period:
        pref.dashboard_period = period
        pref.save(update_fields=['dashboard_period', 'updated_at'])

    today = timezone.localdate()
    period_days, current_start, previous_start, previous_end = _period_bounds(today, period)

    chart_days = [today - timedelta(days=offset) for offset in range((period_days * 2) - 1, -1, -1)]

    context = {
        'page_title': 'Tableau de bord',
        'active_menu': 'dashboard',
        'dashboard_period': period,
        'period_choices': SuperadminCockpitPreference.PERIOD_CHOICES,
        'cockpit_pref': pref,
        'formations_count': Programme.objects.count(),
        'formations_published': Programme.objects.filter(is_active=True).count(),
    }

    try:
        context['candidatures_count'] = Candidature.objects.count()
        context['candidatures_pending'] = Candidature.objects.filter(status='submitted').count()
        context['recent_candidatures'] = Candidature.objects.order_by('-submitted_at')[:5]
    except Exception:
        context['candidatures_count'] = 0
        context['candidatures_pending'] = 0
        context['recent_candidatures'] = []

    try:
        context['inscriptions_count'] = Inscription.objects.count()
        context['inscriptions_active'] = Inscription.objects.filter(status='active').count()
    except Exception:
        context['inscriptions_count'] = 0
        context['inscriptions_active'] = 0

    try:
        context['students_count'] = Student.objects.count()
    except Exception:
        context['students_count'] = 0

    try:
        validated_payment_exists = Payment.objects.filter(
            inscription_id=OuterRef('pk'),
            status=Payment.STATUS_VALIDATED,
        )
        missing_student_qs = (
            Inscription.objects.annotate(has_validated_payment=Exists(validated_payment_exists))
            .filter(
                status__in=[Inscription.STATUS_PARTIAL, Inscription.STATUS_ACTIVE],
                has_validated_payment=True,
                student__isnull=True,
            )
            .filter(
                Q(candidature__status='accepted')
                | Q(candidature__status='accepted_with_reserve')
            )
        )
        context['missing_student_accounts_count'] = missing_student_qs.count()
    except Exception:
        context['missing_student_accounts_count'] = 0

    try:
        context['payments_total'] = Payment.objects.filter(status='validated').aggregate(total=Sum('amount'))['total'] or 0
    except Exception:
        context['payments_total'] = 0

    try:
        context['messages_unread'] = ContactMessage.objects.filter(status='pending').count()
    except Exception:
        context['messages_unread'] = 0

    try:
        context['articles_count'] = Article.objects.count()
    except Exception:
        context['articles_count'] = 0

    try:
        context['community_categories_count'] = CommunityCategory.objects.count()
        context['community_topics_count'] = Topic.objects.count()
        context['community_answers_count'] = Answer.objects.count()
    except Exception:
        context['community_categories_count'] = 0
        context['community_topics_count'] = 0
        context['community_answers_count'] = 0

    # Tendances période courante vs période précédente + séries chart.
    cand_field, cand_is_dt = _resolve_date_field(Candidature, ('submitted_at', 'created_at', 'updated_at'))
    ins_field, ins_is_dt = _resolve_date_field(Inscription, ('created_at', 'submitted_at', 'updated_at', 'start_date'))
    pay_field, pay_is_dt = _resolve_date_field(Payment, ('paid_at', 'payment_date', 'created_at', 'updated_at', 'date'))

    cand_last = _range_count(Candidature, cand_field, cand_is_dt, current_start, today)
    cand_prev = _range_count(Candidature, cand_field, cand_is_dt, previous_start, previous_end)
    ins_last = _range_count(Inscription, ins_field, ins_is_dt, current_start, today)
    ins_prev = _range_count(Inscription, ins_field, ins_is_dt, previous_start, previous_end)
    pay_last = _range_count(Payment, pay_field, pay_is_dt, current_start, today)
    pay_prev = _range_count(Payment, pay_field, pay_is_dt, previous_start, previous_end)

    def trend_payload(current, previous):
        delta = current - previous
        pct = 100.0 if previous == 0 and current > 0 else (0.0 if previous == 0 else (delta / previous) * 100)
        return {
            'current': current,
            'previous': previous,
            'delta': delta,
            'pct': round(pct, 1),
            'up': delta >= 0,
        }

    context['trends'] = {
        'candidatures': trend_payload(cand_last, cand_prev),
        'inscriptions': trend_payload(ins_last, ins_prev),
        'payments': trend_payload(pay_last, pay_prev),
    }

    context['trend_labels'] = [d.strftime('%d/%m') for d in chart_days]
    context['trend_candidatures_series'] = _daily_series(Candidature, cand_field, cand_is_dt, chart_days)
    context['trend_inscriptions_series'] = _daily_series(Inscription, ins_field, ins_is_dt, chart_days)
    context['widget_autorefresh'] = pref.widget_autorefresh
    context['sidebar_collapsed'] = pref.sidebar_collapsed

    return render(request, 'superadmin/dashboard.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def cockpit_preferences_update(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Method not allowed'}, status=405)

    pref = _get_cockpit_pref(request.user)
    sidebar_collapsed = request.POST.get('sidebar_collapsed')
    dashboard_period = request.POST.get('dashboard_period')
    widget_autorefresh = request.POST.get('widget_autorefresh')

    fields = []
    if sidebar_collapsed is not None:
        pref.sidebar_collapsed = sidebar_collapsed in ('1', 'true', 'True', True)
        fields.append('sidebar_collapsed')

    if dashboard_period in dict(SuperadminCockpitPreference.PERIOD_CHOICES):
        pref.dashboard_period = dashboard_period
        fields.append('dashboard_period')

    if widget_autorefresh is not None:
        pref.widget_autorefresh = widget_autorefresh in ('1', 'true', 'True', True)
        fields.append('widget_autorefresh')

    if fields:
        fields.append('updated_at')
        pref.save(update_fields=fields)

    return JsonResponse({'ok': True})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def dashboard_widgets_fragment(request):
    today = timezone.localdate()
    week_ago = today - timedelta(days=6)

    validated_payment_exists = Payment.objects.filter(
        inscription_id=OuterRef('pk'),
        status=Payment.STATUS_VALIDATED,
    )
    context = {
        'candidatures_pending': Candidature.objects.filter(status='submitted').count(),
        'messages_unread': ContactMessage.objects.filter(status='pending').count(),
        'inscriptions_active': Inscription.objects.filter(status='active').count(),
        'missing_student_inscriptions': (
            Inscription.objects.select_related('candidature', 'candidature__programme')
            .annotate(has_validated_payment=Exists(validated_payment_exists))
            .filter(
                status__in=[Inscription.STATUS_PARTIAL, Inscription.STATUS_ACTIVE],
                has_validated_payment=True,
                student__isnull=True,
            )
            .filter(
                Q(candidature__status='accepted')
                | Q(candidature__status='accepted_with_reserve')
            )
            .order_by('-updated_at')[:5]
        ),
        'blog_drafts_count': Article.objects.filter(status='draft', is_deleted=False).count(),
        'blog_recent_published': (
            Article.objects.select_related('author', 'category')
            .filter(status='published', is_deleted=False)
            .order_by('-published_at', '-created_at')[:4]
        ),
        'blog_next_draft': (
            Article.objects.filter(status='draft', is_deleted=False)
            .order_by('created_at')
            .first()
        ),
        'blog_pending_comments_count': Comment.objects.filter(status=Comment.STATUS_PENDING).count(),
        'blog_flagged_comments_count': Comment.objects.filter(status=Comment.STATUS_PENDING, flagged=True).count(),
        'news_drafts_count': News.objects.filter(status=News.STATUS_DRAFT).count(),
        'news_recent_published': (
            News.objects.filter(status=News.STATUS_PUBLISHED)
            .order_by('-published_at', '-created_at')[:4]
        ),
        'news_next_draft': (
            News.objects.filter(status=News.STATUS_DRAFT)
            .order_by('created_at')
            .first()
        ),
        'events_unpublished_count': Event.objects.filter(is_published=False).count(),
        'events_upcoming': (
            Event.objects.filter(event_date__gte=today, is_published=True)
            .select_related('event_type')
            .order_by('event_date')[:4]
        ),
        'event_next_unpublished': (
            Event.objects.filter(is_published=False)
            .order_by('event_date')
            .first()
        ),
        'community_new_members_7d': User.objects.filter(
            is_superuser=False,
            date_joined__date__gte=week_ago,
        ).count(),
        'community_topics_to_moderate': Topic.objects.filter(
            Q(is_published=False) | Q(is_deleted=True)
        ).count(),
        'community_answers_deleted_count': Answer.objects.filter(is_deleted=True).count(),
        'community_unresolved_topics_count': Topic.objects.filter(
            is_deleted=False,
            is_published=True,
            accepted_answer__isnull=True,
        ).count(),
        'community_recent_topics': (
            Topic.objects.select_related('author', 'category')
            .filter(is_deleted=False)
            .order_by('-created_at')[:4]
        ),
        'branches_total_count': Branch.objects.count(),
        'branches_active_count': Branch.objects.filter(is_active=True).count(),
        'branches_inactive_count': Branch.objects.filter(is_active=False).count(),
        'branches_recent': Branch.objects.order_by('-created_at')[:4],
    }

    recent_cash_sessions = (
        CashPaymentSession.objects.select_related(
            'inscription__candidature',
            'agent__user',
        )
        .filter(
            is_used=False,
            expires_at__gt=timezone.now(),
        )
        .order_by('-created_at')[:5]
    )
    context['recent_cash_sessions'] = recent_cash_sessions
    pending_notifications_qs = Notification.objects.filter(email_sent=False)
    context['pending_notifications_count'] = pending_notifications_qs.count()
    raw_pending_types = (
        pending_notifications_qs
        .values('notification_type')
        .annotate(total=Count('id'), oldest_at=Min('created_at'))
        .order_by('-total')[:8]
    )
    notification_labels = dict(Notification.TYPE_CHOICES)
    context['pending_notification_types'] = [
        {
            **row,
            'label': notification_labels.get(row['notification_type'], row['notification_type']),
        }
        for row in raw_pending_types
    ]
    context['pending_notifications_oldest_at'] = (
        pending_notifications_qs
        .order_by('created_at')
        .values_list('created_at', flat=True)
        .first()
    )
    return render(request, 'superadmin/dashboard/_mini_widgets.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def dashboard_content_quick_action(request):
    if request.method != 'POST':
        return redirect('superadmin:dashboard')

    model_name = request.POST.get('model', '').strip()
    raw_pk = request.POST.get('pk', '').strip()

    try:
        pk = int(raw_pk)
    except (TypeError, ValueError):
        messages.error(request, "Action rapide invalide: identifiant manquant.")
        return redirect('superadmin:dashboard')

    if model_name == 'article':
        article = get_object_or_404(Article, pk=pk)
        article.status = 'published'
        if not article.published_at:
            article.published_at = timezone.now()
        article.save(update_fields=['status', 'published_at', 'updated_at'])
        messages.success(request, f"Article '{article.title}' publie.")
    elif model_name == 'news':
        news_item = get_object_or_404(News, pk=pk)
        news_item.status = News.STATUS_PUBLISHED
        if not news_item.published_at:
            news_item.published_at = timezone.now()
        news_item.save(update_fields=['status', 'published_at', 'updated_at'])
        messages.success(request, f"Actualite '{news_item.titre}' publiee.")
    elif model_name == 'event':
        event = get_object_or_404(Event, pk=pk)
        event.is_published = True
        event.save(update_fields=['is_published', 'updated_at'])
        messages.success(request, f"Evenement '{event.title}' publie.")
    else:
        messages.error(request, "Action rapide invalide: cible inconnue.")

    return redirect('superadmin:dashboard')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def dashboard_notifications_action(request):
    if request.method != 'POST':
        return redirect('superadmin:dashboard')

    action = request.POST.get('action')
    notification_type = request.POST.get('notification_type', '').strip()

    qs = Notification.objects.filter(email_sent=False)
    if notification_type:
        qs = qs.filter(notification_type=notification_type)

    updated = 0

    if action == 'mark_old_done':
        cutoff = timezone.now() - timedelta(days=7)
        updated = qs.filter(created_at__lt=cutoff).update(
            email_sent=True,
            sent_at=timezone.now(),
        )
        messages.success(request, f"{updated} notification(s) ancienne(s) marquee(s) comme traitee(s).")
    elif action == 'mark_type_done' and notification_type:
        updated = qs.update(
            email_sent=True,
            sent_at=timezone.now(),
        )
        messages.success(request, f"{updated} notification(s) du type '{notification_type}' marquee(s) comme traitee(s).")
    elif action == 'mark_all_done':
        updated = qs.update(
            email_sent=True,
            sent_at=timezone.now(),
        )
        messages.success(request, f"{updated} notification(s) marquee(s) comme traitee(s).")
    else:
        messages.error(request, "Action de notification invalide.")

    if request.headers.get('HX-Request'):
        return dashboard_widgets_fragment(request)

    return redirect('superadmin:dashboard')


# ============================================
# FORMATIONS - CRUD COMPLET
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def formation_list(request):
    formations = Programme.objects.select_related('cycle', 'filiere').all().order_by('-created_at')
    search = request.GET.get('search', '')
    status = request.GET.get('status', '')
    cycle = request.GET.get('cycle', '')

    if search:
        formations = formations.filter(Q(title__icontains=search) | Q(description__icontains=search))
    if status == 'active':
        formations = formations.filter(is_active=True)
    elif status == 'inactive':
        formations = formations.filter(is_active=False)
    if cycle:
        formations = formations.filter(cycle_id=cycle)

    paginator = Paginator(formations, 20)
    page = request.GET.get('page', 1)
    formations = paginator.get_page(page)

    context = {
        'page_title': 'Formations',
        'formations': formations,
        'cycles': Cycle.objects.all(),
        'filters': {'search': search, 'status': status, 'cycle': cycle},
    }

    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/formations/_list_table.html', context)
    return render(request, 'superadmin/formations/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def formation_create(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        if not title:
            messages.error(request, "Le titre est obligatoire.")
            return redirect('superadmin:formation_create')

        Programme.objects.create(
            title=title,
            short_description=request.POST.get('short_description', ''),
            description=request.POST.get('description', ''),
            cycle_id=request.POST.get('cycle') or None,
            filiere_id=request.POST.get('filiere') or None,
            diploma_awarded_id=request.POST.get('diploma_awarded') or None,
            duration_years=request.POST.get('duration_years', 3),
            learning_outcomes=request.POST.get('learning_outcomes', ''),
            career_opportunities=request.POST.get('career_opportunities', ''),
            program_structure=request.POST.get('program_structure', ''),
            is_active=request.POST.get('is_active') == 'on',
            is_featured=request.POST.get('is_featured') == 'on',
            illustration=request.FILES.get('illustration'),
        )
        messages.success(request, f"Formation '{title}' créée!")
        return redirect('superadmin:formation_list')

    context = {
        'page_title': 'Nouvelle Formation',
        'cycles': Cycle.objects.all(),
        'filieres': Filiere.objects.all(),
        'diplomas': Diploma.objects.all(),
    }
    return render(request, 'superadmin/formations/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def formation_detail(request, pk):
    formation = get_object_or_404(Programme, pk=pk)
    context = {'page_title': formation.title, 'programme': formation}
    return render(request, 'superadmin/formations/detail.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def formation_edit(request, pk):
    formation = get_object_or_404(Programme, pk=pk)

    if request.method == 'POST':
        formation.title = request.POST.get('title', formation.title)
        formation.short_description = request.POST.get('short_description', formation.short_description)
        formation.description = request.POST.get('description', formation.description)
        formation.cycle_id = request.POST.get('cycle') or None
        formation.filiere_id = request.POST.get('filiere') or None
        formation.diploma_awarded_id = request.POST.get('diploma_awarded') or None
        formation.duration_years = request.POST.get('duration_years', formation.duration_years)
        formation.learning_outcomes = request.POST.get('learning_outcomes', formation.learning_outcomes)
        formation.career_opportunities = request.POST.get('career_opportunities', formation.career_opportunities)
        formation.program_structure = request.POST.get('program_structure', formation.program_structure)
        formation.is_active = request.POST.get('is_active') == 'on'
        formation.is_featured = request.POST.get('is_featured') == 'on'
        
        # Handle file upload
        if request.FILES.get('illustration'):
            formation.illustration = request.FILES['illustration']
        
        formation.save()
        messages.success(request, f"Formation '{formation.title}' mise à jour!")
        return redirect('superadmin:formation_list')

    context = {
        'page_title': f'Modifier: {formation.title}',
        'programme': formation,
        'cycles': Cycle.objects.all(),
        'filieres': Filiere.objects.all(),
        'diplomas': Diploma.objects.all(),
    }
    return render(request, 'superadmin/formations/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def formation_delete(request, pk):
    if request.method == 'POST':
        formation = get_object_or_404(Programme, pk=pk)
        response = _safe_delete(
            request,
            formation,
            success_message=f"Formation '{formation.title}' supprimée!",
            protected_message="Suppression impossible: cette formation est liee a des candidatures, inscriptions ou contenus.",
            hx_redirect='/superadmin/formations/',
        )
        if response:
            return response
    return redirect('superadmin:formation_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_formation(request, pk):
    formation = get_object_or_404(Programme, pk=pk)
    formation.is_active = not formation.is_active
    formation.save()
    status = "activée" if formation.is_active else "désactivée"

    if request.headers.get('HX-Request'):
        return HttpResponse(
            f'<span class="badge badge-{"success" if formation.is_active else "secondary"}">{"Actif" if formation.is_active else "Inactif"}</span>',
            headers={'HX-Trigger': f'{{"showToast": "Formation {status}"}}'}
        )
    messages.success(request, f"Formation {status}!")
    return redirect('superadmin:formation_list')


# ============================================
# CYCLES - CRUD
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def cycle_list(request):
    cycles = Cycle.objects.annotate(formations_count=Count('programmes')).order_by('order', 'name')
    return render(request, 'superadmin/cycles/list.html', {'page_title': 'Cycles', 'cycles': cycles})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def cycle_create(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        if name:
            Cycle.objects.create(name=name, description=request.POST.get('description', ''), order=request.POST.get('order', 0))
            messages.success(request, f"Cycle '{name}' créé!")
            return redirect('superadmin:cycle_list')
        messages.error(request, "Le nom est obligatoire.")
    return render(request, 'superadmin/cycles/form.html', {'page_title': 'Nouveau Cycle'})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def cycle_edit(request, pk):
    cycle = get_object_or_404(Cycle, pk=pk)
    if request.method == 'POST':
        cycle.name = request.POST.get('name', cycle.name)
        cycle.description = request.POST.get('description', '')
        cycle.order = request.POST.get('order', 0)
        cycle.save()
        messages.success(request, f"Cycle '{cycle.name}' mis à jour!")
        return redirect('superadmin:cycle_list')
    return render(request, 'superadmin/cycles/form.html', {'page_title': f'Modifier: {cycle.name}', 'cycle': cycle})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def cycle_delete(request, pk):
    if request.method == 'POST':
        cycle = get_object_or_404(Cycle, pk=pk)
        response = _safe_delete(
            request,
            cycle,
            success_message="Cycle supprimé!",
            protected_message="Suppression impossible: ce cycle est encore utilise par une ou plusieurs formations.",
            hx_redirect='/superadmin/cycles/',
        )
        if response:
            return response
    return redirect('superadmin:cycle_list')


# ============================================
# FILIERES - CRUD
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def filiere_list(request):
    filieres = Filiere.objects.annotate(formations_count=Count('programmes')).order_by('name')
    return render(request, 'superadmin/filieres/list.html', {'page_title': 'Filières', 'filieres': filieres})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def filiere_create(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        if name:
            Filiere.objects.create(name=name, description=request.POST.get('description', ''))
            messages.success(request, f"Filière '{name}' créée!")
            return redirect('superadmin:filiere_list')
    return render(request, 'superadmin/filieres/form.html', {'page_title': 'Nouvelle Filière'})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def filiere_edit(request, pk):
    filiere = get_object_or_404(Filiere, pk=pk)
    if request.method == 'POST':
        filiere.name = request.POST.get('name', filiere.name)
        filiere.description = request.POST.get('description', '')
        filiere.save()
        messages.success(request, f"Filière '{filiere.name}' mise à jour!")
        return redirect('superadmin:filiere_list')
    return render(request, 'superadmin/filieres/form.html', {'page_title': f'Modifier: {filiere.name}', 'filiere': filiere})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def filiere_delete(request, pk):
    if request.method == 'POST':
        filiere = get_object_or_404(Filiere, pk=pk)
        response = _safe_delete(
            request,
            filiere,
            success_message="Filière supprimée!",
            protected_message="Suppression impossible: cette filiere est encore associee a des formations.",
            hx_redirect='/superadmin/filieres/',
        )
        if response:
            return response
    return redirect('superadmin:filiere_list')


# ============================================
# DIPLOMAS - CRUD
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def diploma_list(request):
    diplomas = Diploma.objects.all().order_by('name')
    return render(request, 'superadmin/diplomas/list.html', {'page_title': 'Diplômes', 'diplomas': diplomas})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def diploma_create(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        if name:
            Diploma.objects.create(name=name, abbreviation=request.POST.get('abbreviation', ''))
            messages.success(request, f"Diplôme '{name}' créé!")
            return redirect('superadmin:diploma_list')
    return render(request, 'superadmin/diplomas/form.html', {'page_title': 'Nouveau Diplôme'})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def diploma_edit(request, pk):
    diploma = get_object_or_404(Diploma, pk=pk)
    if request.method == 'POST':
        diploma.name = request.POST.get('name', diploma.name)
        diploma.abbreviation = request.POST.get('abbreviation', '')
        diploma.save()
        messages.success(request, f"Diplôme '{diploma.name}' mis à jour!")
        return redirect('superadmin:diploma_list')
    return render(request, 'superadmin/diplomas/form.html', {'page_title': f'Modifier: {diploma.name}', 'diploma': diploma})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def diploma_delete(request, pk):
    if request.method == 'POST':
        diploma = get_object_or_404(Diploma, pk=pk)
        response = _safe_delete(
            request,
            diploma,
            success_message="Diplôme supprimé!",
            protected_message="Suppression impossible: ce diplome est encore utilise par des programmes.",
            hx_redirect='/superadmin/diplomas/',
        )
        if response:
            return response
    return redirect('superadmin:diploma_list')


# ============================================
# CANDIDATURES
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def candidature_list(request):
    qs = (
        Candidature.objects.filter(is_deleted=False).select_related('programme__cycle', 'branch')
        .annotate(
            validated_docs=Count('documents', filter=Q(documents__is_valid=True), distinct=True),
            required_docs=Count('programme__required_documents', distinct=True),
        )
        .annotate(missing_docs=Greatest(Value(0), F('required_docs') - F('validated_docs'), output_field=IntegerField()))
        .order_by('-submitted_at')
    )

    search = request.GET.get('search', '').strip()
    status = request.GET.get('status', '').strip()
    programme = request.GET.get('programme', '').strip()
    branch = request.GET.get('branch', '').strip()
    academic_year = request.GET.get('academic_year', '').strip()

    if search:
        qs = qs.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(email__icontains=search)
            | Q(phone__icontains=search)
            | Q(programme__title__icontains=search)
        )
    if status:
        qs = qs.filter(status=status)
    if programme:
        qs = qs.filter(programme_id=programme)
    if branch:
        qs = qs.filter(branch_id=branch)
    if academic_year:
        qs = qs.filter(academic_year=academic_year)

    paginator = Paginator(qs, 20)
    candidatures = paginator.get_page(request.GET.get('page', 1))

    stats = Candidature.objects.aggregate(
        submitted=Count('id', filter=Q(status='submitted')),
        under_review=Count('id', filter=Q(status='under_review')),
        to_complete=Count('id', filter=Q(status='to_complete')),
        accepted=Count('id', filter=Q(status='accepted')),
        rejected=Count('id', filter=Q(status='rejected')),
    )

    context = {
        'page_title': 'Candidatures',
        'active_menu': 'candidatures',
        'candidatures': candidatures,
        'status_choices': Candidature.STATUS_CHOICES,
        'programmes': Programme.objects.only('id', 'title').order_by('title'),
        'branches': Branch.objects.only('id', 'name').order_by('name'),
        'academic_years': Candidature.objects.values_list('academic_year', flat=True).distinct().order_by('-academic_year'),
        'filters': {
            'search': search,
            'status': status,
            'programme': programme,
            'branch': branch,
            'academic_year': academic_year,
        },
        'stats': stats,
    }

    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/candidatures/_list_table.html', context)
    return render(request, 'superadmin/candidatures/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def candidature_create(request):
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        programme_id = request.POST.get('programme')
        branch_id = request.POST.get('branch')
        academic_year = request.POST.get('academic_year', '').strip()

        required_fields = [first_name, last_name, email, phone, programme_id, branch_id, academic_year]
        if not all(required_fields):
            messages.error(request, 'Veuillez remplir tous les champs obligatoires.')
            return redirect('superadmin:candidature_create')

        candidature = Candidature.objects.create(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            programme_id=programme_id,
            branch_id=branch_id,
            academic_year=academic_year,
            birth_date=request.POST.get('birth_date'),
            birth_place=request.POST.get('birth_place', ''),
            gender=request.POST.get('gender', 'male'),
            entry_year=request.POST.get('entry_year') or 1,
            address=request.POST.get('address', ''),
            city=request.POST.get('city', ''),
            country=request.POST.get('country', 'Mali'),
            status=request.POST.get('status', 'submitted'),
            admin_comment=request.POST.get('admin_comment', ''),
        )
        messages.success(request, f'Candidature #{candidature.pk} créée avec succès.')
        return redirect('superadmin:candidature_detail', pk=candidature.pk)

    context = {
        'page_title': 'Nouvelle candidature',
        'active_menu': 'candidatures',
        'programmes': Programme.objects.only('id', 'title').order_by('title'),
        'branches': Branch.objects.only('id', 'name').order_by('name'),
        'status_choices': Candidature.STATUS_CHOICES,
    }
    return render(request, 'superadmin/candidatures/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def candidature_detail(request, pk):
    candidature = get_object_or_404(
        Candidature.objects.select_related('programme__cycle', 'programme__filiere', 'programme__diploma_awarded', 'branch', 'reviewed_by'),
        pk=pk,
    )
    if request.method == 'POST':
        candidature.admin_comment = request.POST.get('admin_comment', candidature.admin_comment)
        candidature.save(update_fields=['admin_comment', 'updated_at'])
        messages.success(request, 'Commentaire interne mis à jour.')
        return redirect('superadmin:candidature_detail', pk=pk)

    documents = CandidatureDocument.objects.select_related('document_type', 'validated_by').filter(candidature=candidature).order_by('uploaded_at')

    timeline = [
        {'label': 'Candidature soumise', 'date': candidature.submitted_at, 'icon': 'fa-paper-plane', 'color': 'text-blue-600'},
        {'label': 'Dernière mise à jour', 'date': candidature.updated_at, 'icon': 'fa-pen', 'color': 'text-slate-600'},
    ]
    if candidature.reviewed_at:
        timeline.append({'label': 'Révision administrative', 'date': candidature.reviewed_at, 'icon': 'fa-user-check', 'color': 'text-emerald-600'})

    context = {
        'page_title': f'Candidature #{pk}',
        'active_menu': 'candidatures',
        'candidature': candidature,
        'documents': documents,
        'timeline': sorted(timeline, key=lambda item: item['date'] or timezone.now(), reverse=True),
        'status_choices': Candidature.STATUS_CHOICES,
        'required_document_types': candidature.programme.required_documents.all(),
        'linked_inscription': getattr(candidature, 'inscription', None),
    }
    return render(request, 'superadmin/candidatures/detail.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def candidature_status(request, pk):
    candidature = get_object_or_404(Candidature, pk=pk)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        valid_statuses = {choice[0] for choice in Candidature.STATUS_CHOICES}
        if new_status in valid_statuses:
            candidature.status = new_status
            candidature.reviewed_by = request.user
            candidature.reviewed_at = timezone.now()
            note = request.POST.get('admin_comment', '').strip()
            if note:
                candidature.admin_comment = note
            candidature.save()
            messages.success(request, f"Statut mis à jour: {new_status}. Notification email planifiée.")
        else:
            messages.error(request, "Statut invalide.")

    if request.headers.get('HX-Request'):
        return HttpResponse(status=200, headers={'HX-Redirect': f'/superadmin/candidatures/{pk}/'})
    return redirect('superadmin:candidature_detail', pk=pk)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def candidature_edit(request, pk):
    candidature = get_object_or_404(Candidature.objects.select_related('programme', 'branch'), pk=pk)
    if request.method == 'POST':
        candidature.first_name = request.POST.get('first_name', candidature.first_name)
        candidature.last_name = request.POST.get('last_name', candidature.last_name)
        candidature.email = request.POST.get('email', candidature.email)
        candidature.phone = request.POST.get('phone', candidature.phone)
        candidature.academic_year = request.POST.get('academic_year', candidature.academic_year)
        candidature.branch_id = request.POST.get('branch') or candidature.branch_id
        candidature.programme_id = request.POST.get('programme') or candidature.programme_id
        candidature.status = request.POST.get('status', candidature.status)
        candidature.admin_comment = request.POST.get('admin_comment', candidature.admin_comment)
        candidature.save()
        messages.success(request, f"Candidature #{candidature.pk} mise à jour!")
        return redirect('superadmin:candidature_detail', pk=candidature.pk)
    return render(request, 'superadmin/candidatures/form.html', {
        'page_title': f'Modifier Candidature #{pk}',
        'active_menu': 'candidatures',
        'candidature': candidature,
        'programmes': Programme.objects.only('id', 'title').order_by('title'),
        'branches': Branch.objects.only('id', 'name').order_by('name'),
        'status_choices': Candidature.STATUS_CHOICES,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def candidature_delete(request, pk):
    if request.method == 'POST':
        candidature = get_object_or_404(Candidature, pk=pk)
        if candidature.is_deleted:
            messages.info(request, "Cette candidature est deja supprimee logiquement.")
        else:
            candidature.is_deleted = True
            candidature.deleted_at = timezone.now()
            candidature.deleted_by = request.user
            candidature.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by', 'updated_at'])
            messages.success(request, "Candidature masquee (suppression logique).")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/candidatures/'})
    return redirect('superadmin:candidature_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def candidature_bulk_action(request):
    if request.method != 'POST':
        return redirect('superadmin:candidature_list')

    selected_ids = request.POST.getlist('selected')
    action = request.POST.get('action')
    if not selected_ids:
        messages.warning(request, 'Aucune candidature sélectionnée.')
        return redirect('superadmin:candidature_list')

    qs = Candidature.objects.filter(pk__in=selected_ids)
    valid_statuses = {choice[0] for choice in Candidature.STATUS_CHOICES}

    if action in valid_statuses:
        updated = 0
        for candidature in qs:
            candidature.status = action
            candidature.reviewed_by = request.user
            candidature.reviewed_at = timezone.now()
            candidature.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'updated_at'])
            updated += 1
        messages.success(request, f'{updated} candidature(s) mises à jour.')
        if updated:
            messages.info(request, "Les notifications email associees ont ete planifiees automatiquement.")
    elif action == 'delete':
        updated = qs.filter(is_deleted=False).update(
            is_deleted=True,
            deleted_at=timezone.now(),
            deleted_by=request.user,
            updated_at=timezone.now(),
        )
        messages.success(request, f'{updated} candidature(s) masquee(s) (suppression logique).')
    else:
        messages.error(request, 'Action groupée invalide.')

    return redirect('superadmin:candidature_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def candidature_document_add(request, pk):
    candidature = get_object_or_404(Candidature, pk=pk)
    if request.method == 'POST':
        document_type_id = request.POST.get('document_type')
        file = request.FILES.get('file')
        if document_type_id and file:
            CandidatureDocument.objects.create(
                candidature=candidature,
                document_type_id=document_type_id,
                file=file,
            )
            messages.success(request, "Document ajouté!")
        else:
            messages.error(request, "Type de document et fichier requis.")
    return redirect('superadmin:candidature_detail', pk=pk)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def candidature_document_delete(request, pk, doc_pk):
    document = get_object_or_404(CandidatureDocument, pk=doc_pk, candidature_id=pk)
    candidature_pk = document.candidature.pk
    if request.method == 'POST':
        _safe_delete(
            request,
            document,
            success_message="Document supprimé!",
            protected_message="Suppression impossible: ce document est protege par une contrainte de donnees.",
        )
    return redirect('superadmin:candidature_detail', pk=candidature_pk)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def candidature_document_validate(request, pk, doc_pk):
    document = get_object_or_404(CandidatureDocument, pk=doc_pk, candidature_id=pk)
    if request.method == 'POST':
        is_valid = request.POST.get('is_valid') == 'on'
        document.is_valid = is_valid
        document.is_validated = is_valid
        if is_valid:
            document.validated_at = timezone.now()
            document.validated_by = request.user
        else:
            document.validated_at = None
            document.validated_by = None
        document.admin_note = request.POST.get('admin_note', '')
        document.save()
        status = "validé" if is_valid else "invalidé"
        messages.success(request, f"Document {status}!")
    return redirect('superadmin:candidature_detail', pk=document.candidature.pk)


# ============================================
# INSCRIPTIONS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def inscription_list(request):
    validated_payment_exists = Payment.objects.filter(
        inscription_id=OuterRef('pk'),
        status=Payment.STATUS_VALIDATED,
    )
    inscriptions_qs = (
        Inscription.objects.filter(is_archived=False).select_related(
            'candidature__programme__cycle',
            'candidature__branch',
            'student__user',
        )
        .prefetch_related('payments')
        .annotate(
            student_pk=F('student__id'),
            student_matricule=F('student__matricule'),
            has_validated_payment=Exists(validated_payment_exists),
            payments_count=Count('payments', distinct=True),
            validated_total=Sum('payments__amount', filter=Q(payments__status=Payment.STATUS_VALIDATED)),
            pending_total=Sum('payments__amount', filter=Q(payments__status=Payment.STATUS_PENDING)),
        )
        .order_by('-created_at')
    )

    search = request.GET.get('search', '').strip()
    status = request.GET.get('status', '').strip()
    programme = request.GET.get('programme', '').strip()
    academic_year = request.GET.get('academic_year', '').strip()

    if search:
        inscriptions_qs = inscriptions_qs.filter(
            Q(public_token__icontains=search)
            | Q(reference__icontains=search)
            | Q(candidature__first_name__icontains=search)
            | Q(candidature__last_name__icontains=search)
            | Q(candidature__email__icontains=search)
            | Q(student__matricule__icontains=search)
        )
    if status:
        inscriptions_qs = inscriptions_qs.filter(status=status)
    if programme:
        inscriptions_qs = inscriptions_qs.filter(candidature__programme_id=programme)
    if academic_year:
        inscriptions_qs = inscriptions_qs.filter(candidature__academic_year=academic_year)

    paginator = Paginator(inscriptions_qs, 20)
    inscriptions = paginator.get_page(request.GET.get('page', 1))

    summary = inscriptions_qs.aggregate(
        total_due=Sum('amount_due'),
        total_paid=Sum('amount_paid'),
        total_count=Count('id'),
        awaiting_payment=Count('id', filter=Q(status=Inscription.STATUS_AWAITING_PAYMENT)),
        partial_paid=Count('id', filter=Q(status=Inscription.STATUS_PARTIAL)),
        active=Count('id', filter=Q(status=Inscription.STATUS_ACTIVE)),
        missing_student_accounts=Count('id', filter=Q(student__isnull=True) & Q(has_validated_payment=True) & Q(status__in=[Inscription.STATUS_PARTIAL, Inscription.STATUS_ACTIVE])),
    )
    total_due = summary.get('total_due') or 0
    total_paid = summary.get('total_paid') or 0
    summary['recovery_rate'] = round((total_paid / total_due) * 100, 1) if total_due else 0

    context = {
        'page_title': 'Inscriptions',
        'active_menu': 'inscriptions',
        'inscriptions': inscriptions,
        'summary': summary,
        'status_choices': Inscription.STATUS_CHOICES,
        'programmes': Programme.objects.only('id', 'title').order_by('title'),
        'academic_years': Candidature.objects.values_list('academic_year', flat=True).distinct().order_by('-academic_year'),
        'filters': {
            'search': search,
            'status': status,
            'programme': programme,
            'academic_year': academic_year,
        },
    }

    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/inscriptions/_list_table.html', context)
    return render(request, 'superadmin/inscriptions/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def inscription_create(request):
    """Créer une inscription depuis une candidature acceptée."""
    if request.method == 'POST':
        candidature_id = request.POST.get('candidature')
        amount_due = request.POST.get('amount_due')
        status = request.POST.get('status', Inscription.STATUS_CREATED)

        if not candidature_id:
            messages.error(request, "Candidature requise.")
            return redirect('superadmin:candidature_list')

        candidature = get_object_or_404(Candidature, pk=candidature_id)

        # Vérifier si inscription existe déjà
        if hasattr(candidature, "inscription"):
            messages.error(request, "Une inscription existe déjà pour cette candidature.")
            return redirect('superadmin:candidature_detail', pk=candidature_id)

        # Vérifier que la candidature est acceptée
        if candidature.status not in ["accepted", "accepted_with_reserve"]:
            messages.error(request, "La candidature doit être acceptée pour créer une inscription.")
            return redirect('superadmin:candidature_detail', pk=candidature_id)

        # Utiliser le montant fourni ou calculer
        if not amount_due:
            amount_due = candidature.programme.get_inscription_amount_for_year(candidature.entry_year)
            if amount_due == 0:
                amount_due = 500000  # Montant par défaut

        inscription = Inscription.objects.create(
            candidature=candidature,
            amount_due=int(amount_due),
            status=status
        )

        messages.success(request, f"Inscription créée avec succès ! Référence : {inscription.public_token}")
        return redirect('superadmin:inscription_detail', pk=inscription.pk)

    # GET request - show form
    candidature_id = request.GET.get('candidature')
    if candidature_id:
        candidature = get_object_or_404(Candidature, pk=candidature_id)
        # Calculer le montant suggéré
        amount_due = candidature.programme.get_inscription_amount_for_year(candidature.entry_year)
        if amount_due == 0:
            amount_due = 500000

        context = {
            'page_title': 'Créer une inscription',
            'active_menu': 'inscriptions',
            'candidature': candidature,
            'amount_due': amount_due,
            'status_choices': Inscription.STATUS_CHOICES,
        }
        return render(request, 'superadmin/inscriptions/create.html', context)
    else:
        context = {
            'page_title': 'Créer une inscription',
            'active_menu': 'inscriptions',
            'candidature': None,
            'status_choices': Inscription.STATUS_CHOICES,
        }
        return render(request, 'superadmin/inscriptions/create.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def inscription_detail(request, pk):
    inscription = get_object_or_404(
        Inscription.objects.select_related(
            'candidature__programme__cycle',
            'candidature__programme__filiere',
            'candidature__branch',
            'student__user',
        ).prefetch_related('payments__agent', 'history'),
        pk=pk,
    )

    payments = inscription.payments.all().order_by('-paid_at')
    history_entries = inscription.history.all()
    next_transitions = Inscription.VALID_TRANSITIONS.get(inscription.status, [])
    latest_cash_session = (
        CashPaymentSession.objects.select_related('agent__user')
        .filter(inscription=inscription)
        .order_by('-created_at')
        .first()
    )
    active_cash_sessions = (
        CashPaymentSession.objects.select_related('agent__user')
        .filter(inscription=inscription, is_used=False, expires_at__gt=timezone.now())
        .order_by('-created_at')[:5]
    )
    has_validated_payment = inscription.payments.filter(status=Payment.STATUS_VALIDATED).exists()

    context = {
        'page_title': f'Inscription #{pk}',
        'active_menu': 'inscriptions',
        'inscription': inscription,
        'payments': payments,
        'history_entries': history_entries,
        'next_transitions': next_transitions,
        'linked_student': getattr(inscription, 'student', None),
        'latest_cash_session': latest_cash_session,
        'active_cash_sessions': active_cash_sessions,
        'has_validated_payment': has_validated_payment,
        'show_missing_student_alert': has_validated_payment and not getattr(inscription, 'student_id', None),
    }
    return render(request, 'superadmin/inscriptions/detail.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def inscription_status(request, pk):
    inscription = get_object_or_404(Inscription, pk=pk)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        comment = request.POST.get('comment', '').strip()
        valid_statuses = {value for value, _ in Inscription.STATUS_CHOICES}
        if new_status in valid_statuses:
            _change_inscription_status(inscription, new_status, comment or 'Mise à jour depuis le superadmin')
            messages.success(request, f'Statut mis à jour : {inscription.get_status_display()}')
        else:
            messages.error(request, 'Statut invalide.')

    if request.headers.get('HX-Request'):
        return HttpResponse(status=200, headers={'HX-Redirect': f'/superadmin/inscriptions/{pk}/'})
    return redirect('superadmin:inscription_detail', pk=pk)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def inscription_bulk_action(request):
    if request.method != 'POST':
        return redirect('superadmin:inscription_list')

    action = request.POST.get('action')
    selected_ids = request.POST.getlist('selected')
    if not selected_ids:
        messages.warning(request, 'Aucune inscription sélectionnée.')
        return redirect('superadmin:inscription_list')

    inscriptions = list(Inscription.objects.filter(pk__in=selected_ids))
    updated = 0
    if action in {value for value, _ in Inscription.STATUS_CHOICES}:
        for inscription in inscriptions:
            _change_inscription_status(inscription, action, 'Action groupée superadmin')
            updated += 1
        messages.success(request, f'{updated} inscription(s) mises à jour.')
    elif action == 'relance':
        for inscription in inscriptions:
            _log_inscription_history(inscription, inscription.status, inscription.status, 'Relance administrative envoyée')
            updated += 1
        messages.success(request, f'{updated} relance(s) enregistrée(s).')
    elif action == 'archive':
        updated = Inscription.objects.filter(pk__in=selected_ids).update(is_archived=True, archived_at=timezone.now())
        messages.success(request, f'{updated} inscription(s) archivée(s).')
    elif action == 'restore':
        updated = Inscription.objects.filter(pk__in=selected_ids).update(is_archived=False, archived_at=None)
        messages.success(request, f'{updated} inscription(s) restaurée(s).')
    elif action == 'regenerate_access_code':
        for inscription in inscriptions:
            inscription.access_code = secrets.token_urlsafe(6)
            inscription.save(update_fields=['access_code'])
            updated += 1
        messages.success(request, f'{updated} code(s) d\'accès régénéré(s).')
    else:
        messages.error(request, 'Action groupée invalide.')

    return redirect('superadmin:inscription_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def inscription_certificate(request, pk):
    inscription = get_object_or_404(
        Inscription.objects.select_related('candidature__programme__cycle', 'candidature__branch'),
        pk=pk,
    )
    return _render_inscription_certificate(inscription)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def inscription_confirm_payment(request, pk):
    if request.method != 'POST':
        return redirect('superadmin:inscription_detail', pk=pk)

    inscription = get_object_or_404(Inscription.objects.prefetch_related('payments'), pk=pk)
    pending_payment = inscription.payments.filter(status=Payment.STATUS_PENDING).order_by('-paid_at').first()

    if not pending_payment:
        messages.warning(request, 'Aucun paiement en attente à confirmer.')
        return redirect('superadmin:inscription_detail', pk=pk)

    previous_status = inscription.status
    pending_payment.status = Payment.STATUS_VALIDATED
    pending_payment.save()
    inscription.refresh_from_db()
    _log_inscription_history(inscription, previous_status, inscription.status, f'Paiement {pending_payment.reference or pending_payment.pk} confirmé')
    messages.success(request, 'Paiement confirmé avec succès.')
    return redirect('superadmin:inscription_detail', pk=pk)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def inscription_relance(request, pk):
    if request.method != 'POST':
        return redirect('superadmin:inscription_detail', pk=pk)

    inscription = get_object_or_404(Inscription, pk=pk)
    _log_inscription_history(inscription, inscription.status, inscription.status, 'Relance envoyée au candidat/étudiant')
    messages.success(request, 'Relance enregistrée.')
    return redirect('superadmin:inscription_detail', pk=pk)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def inscription_regenerate_access_code(request, pk):
    if request.method != 'POST':
        return redirect('superadmin:inscription_detail', pk=pk)

    inscription = get_object_or_404(Inscription, pk=pk)
    inscription.access_code = secrets.token_urlsafe(6)
    inscription.save(update_fields=['access_code'])
    _log_inscription_history(inscription, inscription.status, inscription.status, 'Code d\'accès régénéré par un admin')
    messages.success(request, 'Code d\'accès régénéré avec succès.')
    return redirect('superadmin:inscription_detail', pk=pk)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def inscription_archive_toggle(request, pk):
    if request.method != 'POST':
        return redirect('superadmin:inscription_detail', pk=pk)

    inscription = get_object_or_404(Inscription, pk=pk)
    inscription.is_archived = not inscription.is_archived
    inscription.archived_at = timezone.now() if inscription.is_archived else None
    inscription.save(update_fields=['is_archived', 'archived_at'])
    state = 'archivée' if inscription.is_archived else 'restaurée'
    _log_inscription_history(inscription, inscription.status, inscription.status, f'Inscription {state} depuis le superadmin')
    messages.success(request, f'Inscription {state}.')
    return redirect('superadmin:inscription_detail', pk=pk)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def inscription_edit(request, pk):
    inscription = get_object_or_404(Inscription.objects.select_related('candidature__programme', 'candidature__branch'), pk=pk)
    if request.method == 'POST':
        inscription.status = request.POST.get('status', inscription.status)
        amount_due = request.POST.get('amount_due', inscription.amount_due) or inscription.amount_due
        inscription.amount_due = int(amount_due)
        inscription.is_archived = request.POST.get('is_archived') == 'on'
        inscription.save()
        messages.success(request, f"Inscription #{inscription.pk} mise à jour!")
        return redirect('superadmin:inscription_detail', pk=pk)
    return render(request, 'superadmin/inscriptions/form.html', {
        'page_title': f'Modifier Inscription #{pk}',
        'active_menu': 'inscriptions',
        'inscription': inscription,
        'status_choices': Inscription.STATUS_CHOICES,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def inscription_delete(request, pk):
    if request.method == 'POST':
        inscription = get_object_or_404(Inscription, pk=pk)
        if inscription.is_archived:
            messages.info(request, "Cette inscription est deja archivee.")
        else:
            inscription.is_archived = True
            inscription.archived_at = timezone.now()
            inscription.save(update_fields=['is_archived', 'archived_at'])
            _log_inscription_history(inscription, inscription.status, inscription.status, 'Inscription archivee (suppression logique) depuis superadmin')
            messages.success(request, "Inscription archivee (suppression logique).")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/inscriptions/'})
    return redirect('superadmin:inscription_list')


# ============================================
# STUDENTS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def student_list(request):
    students = (
        Student.objects
        .select_related(
            'user',
            'inscription__candidature__programme',
            'inscription__candidature__branch',
        )
        .annotate(
            validated_amount=Sum(
                'inscription__payments__amount',
                filter=Q(inscription__payments__status=Payment.STATUS_VALIDATED),
            ),
            payment_count=Count('inscription__payments', distinct=True),
        )
        .order_by('-created_at')
    )

    search = request.GET.get('search', '')
    status = request.GET.get('status', '')
    programme = request.GET.get('programme', '')

    try:
        programme_id = int(programme) if programme else None
    except (TypeError, ValueError):
        programme_id = None

    if search:
        students = students.filter(
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search) |
            Q(user__email__icontains=search) |
            Q(matricule__icontains=search)
        )

    if status == 'active':
        students = students.filter(is_active=True)
    elif status == 'inactive':
        students = students.filter(is_active=False)

    if programme_id:
        students = students.filter(inscription__candidature__programme_id=programme_id)

    paginator = Paginator(students, 20)
    page = request.GET.get('page', 1)
    students = paginator.get_page(page)

    context = {
        'page_title': 'Étudiants',
        'active_menu': 'students',
        'students': students,
        'programmes': Programme.objects.only('id', 'title').order_by('title'),
        'filters': {
            'search': search,
            'status': status,
            'programme': programme,
            'programme_id': programme_id,
        },
    }

    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/students/_student_table.html', context)

    return render(request, 'superadmin/students/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def student_detail(request, pk):
    student = get_object_or_404(
        Student.objects.select_related(
            'user',
            'inscription__candidature__programme',
            'inscription__candidature__branch',
        ),
        pk=pk,
    )
    inscription = student.inscription
    candidature = inscription.candidature

    payments = (
        inscription.payments
        .select_related('agent__user')
        .order_by('-paid_at')
    )

    status_history = inscription.history.all().order_by('-created_at')[:20]
    documents = candidature.documents.select_related('document_type').order_by('-uploaded_at')

    payment_summary = payments.aggregate(
        total_validated=Sum('amount', filter=Q(status=Payment.STATUS_VALIDATED)),
        total_pending=Sum('amount', filter=Q(status=Payment.STATUS_PENDING)),
        total_count=Count('id'),
    )

    amount_paid = payment_summary.get('total_validated') or 0
    amount_due = inscription.amount_due or 0
    balance = max(amount_due - amount_paid, 0)

    context = {
        'page_title': f'Étudiant: {student.user.get_full_name()}',
        'active_menu': 'students',
        'student': student,
        'inscription': inscription,
        'candidature': candidature,
        'payments': payments,
        'status_history': status_history,
        'documents': documents,
        'payment_summary': payment_summary,
        'amount_paid': amount_paid,
        'amount_due': amount_due,
        'balance': balance,
    }
    return render(request, 'superadmin/students/detail.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def student_edit(request, pk):
    student = get_object_or_404(Student.objects.select_related('user', 'inscription'), pk=pk)
    if request.method == 'POST':
        user = student.user
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.email = request.POST.get('email', user.email)
        user.save()
        messages.success(request, f"Étudiant '{user.get_full_name()}' mis à jour!")
        return redirect('superadmin:student_detail', pk=pk)
    return render(request, 'superadmin/students/form.html', {'page_title': f'Modifier: {student.user.get_full_name()}', 'student': student})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def student_delete(request, pk):
    if request.method == 'POST':
        student = get_object_or_404(Student, pk=pk)
        response = _safe_delete(
            request,
            student,
            success_message="Étudiant supprimé!",
            protected_message="Suppression impossible: cet etudiant est protege par son inscription de reference.",
            hx_redirect='/superadmin/students/',
        )
        if response:
            return response
    return redirect('superadmin:student_list')


# ============================================
# PAYMENTS
# ============================================

def _ensure_payment_receipt(payment):
    """Vérifie la disponibilité d'un reçu pour un paiement validé, sans régénération."""
    if payment.status != Payment.STATUS_VALIDATED:
        raise ValueError("Le reçu PDF n'est disponible que pour un paiement validé.")

    if not payment.receipt_pdf:
        raise ValueError(
            "Ce paiement est validé mais son reçu PDF est indisponible. "
            "La régénération manuelle est verrouillée par le workflow métier."
        )

    return payment


def _is_manual_payment_method(method):
    return method in {Payment.METHOD_CASH, Payment.METHOD_BANK}


def _get_or_create_superadmin_agent(user, inscription):
    """Retourne un agent superadmin compatible avec l'annexe, sans réaffectation forcée."""
    if not user.is_authenticated or not user.is_staff:
        return None

    branch = getattr(inscription.candidature, 'branch', None)
    if not branch:
        return None

    agent, _ = PaymentAgent.objects.get_or_create(
        user=user,
        defaults={
            'branch': branch,
            'is_active': True,
        },
    )

    # Ne jamais modifier silencieusement l'annexe de l'agent existant.
    if agent.branch_id != branch.id:
        return None

    if not agent.is_active:
        agent.is_active = True
        agent.save(update_fields=['is_active'])

    return agent


def _build_payment_access_context(payment):
    """Construit les infos de code d'accès/code cash à afficher en superadmin."""
    is_manual = _is_manual_payment_method(payment.method)
    context = {
        'is_manual_method': is_manual,
        'inscription_access_code': payment.inscription.access_code if is_manual else None,
        'cash_code': None,
        'cash_code_expires_at': None,
        'cash_code_is_used': None,
    }

    if payment.method != Payment.METHOD_CASH or not payment.agent_id:
        return context

    cash_session = payment.cash_session
    if cash_session:
        context.update({
            'cash_code': cash_session.verification_code,
            'cash_code_expires_at': cash_session.expires_at,
            'cash_code_is_used': cash_session.is_used,
        })
        return context

    cash_session = (
        CashPaymentSession.objects
        .filter(
            inscription_id=payment.inscription_id,
            agent_id=payment.agent_id,
            created_at__lte=payment.created_at,
        )
        .order_by('-created_at')
        .first()
    )

    if not cash_session:
        return context

    context.update({
        'cash_code': cash_session.verification_code,
        'cash_code_expires_at': cash_session.expires_at,
        'cash_code_is_used': cash_session.is_used,
    })
    return context

@user_passes_test(superuser_required, login_url='/accounts/login/')
def payment_list(request):
    payments_qs = (
        Payment.objects.select_related(
            'inscription__student__user',
            'inscription__candidature__programme',
            'inscription__candidature__branch',
            'agent__user',
            'cash_session',
        )
        .annotate(student_matricule=F('inscription__student__matricule'))
        .order_by('-paid_at')
    )

    search = request.GET.get('search', '')
    status = request.GET.get('status', '')
    method = request.GET.get('method', '')
    programme = request.GET.get('programme', '')
    academic_year = request.GET.get('academic_year', '')
    branch = request.GET.get('branch', '')
    agent = request.GET.get('agent', '')
    try:
        programme_id = int(programme) if programme else None
    except (TypeError, ValueError):
        programme_id = None
    try:
        branch_id = int(branch) if branch else None
    except (TypeError, ValueError):
        branch_id = None
    try:
        agent_id = int(agent) if agent else None
    except (TypeError, ValueError):
        agent_id = None

    if search:
        payments_qs = payments_qs.filter(
            Q(inscription__student__user__first_name__icontains=search) |
            Q(inscription__student__user__last_name__icontains=search) |
            Q(inscription__student__matricule__icontains=search) |
            Q(inscription__candidature__first_name__icontains=search) |
            Q(inscription__candidature__last_name__icontains=search) |
            Q(reference__icontains=search) |
            Q(receipt_number__icontains=search)
        )
    if status:
        payments_qs = payments_qs.filter(status=status)
    else:
        payments_qs = payments_qs.exclude(status=Payment.STATUS_CANCELLED)
    if method:
        payments_qs = payments_qs.filter(method=method)
    if programme_id:
        payments_qs = payments_qs.filter(inscription__candidature__programme_id=programme_id)
    if academic_year:
        payments_qs = payments_qs.filter(inscription__candidature__academic_year=academic_year)
    if branch_id:
        payments_qs = payments_qs.filter(inscription__candidature__branch_id=branch_id)
    if agent_id:
        payments_qs = payments_qs.filter(agent_id=agent_id)

    summary = payments_qs.aggregate(
        total_validated=Sum('amount', filter=Q(status=Payment.STATUS_VALIDATED)),
        total_pending=Sum('amount', filter=Q(status=Payment.STATUS_PENDING)),
        total_count=Count('id'),
    )
    total_validated = summary.get('total_validated') or 0
    total_pending = summary.get('total_pending') or 0

    inscription_ids = payments_qs.values_list('inscription_id', flat=True).distinct()
    due_total = Inscription.objects.filter(pk__in=inscription_ids).aggregate(total=Sum('amount_due'))['total'] or 0
    summary['recovery_rate'] = round((total_validated / due_total) * 100, 1) if due_total else 0
    summary['total_due'] = due_total

    paginator = Paginator(payments_qs, 20)
    page = request.GET.get('page', 1)
    payments = paginator.get_page(page)

    context = {
        'page_title': 'Paiements',
        'active_menu': 'payments',
        'payments': payments,
        'summary': summary,
        'status_choices': Payment.STATUS_CHOICES,
        'method_choices': Payment.METHOD_CHOICES,
        'programmes': Programme.objects.order_by('title').only('id', 'title'),
        'branches': Branch.objects.filter(is_active=True).order_by('name').only('id', 'name'),
        'payment_agents': PaymentAgent.objects.select_related('user').filter(is_active=True).order_by('user__first_name', 'user__last_name'),
        'academic_years': (
            Candidature.objects
            .exclude(academic_year__isnull=True)
            .exclude(academic_year='')
            .values_list('academic_year', flat=True)
            .distinct()
            .order_by('-academic_year')
        ),
        'filters': {
            'search': search,
            'status': status,
            'method': method,
            'programme': programme,
            'programme_id': programme_id,
            'academic_year': academic_year,
            'branch': branch,
            'branch_id': branch_id,
            'agent': agent,
            'agent_id': agent_id,
        },
    }

    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/payments/_payment_table.html', context)
    return render(request, 'superadmin/payments/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def payment_detail(request, pk):
    payment = get_object_or_404(
        Payment.objects.select_related(
            'inscription__student__user',
            'inscription__candidature__programme',
            'inscription__candidature__branch',
            'agent__user',
            'cash_session',
        ),
        pk=pk,
    )

    history = [
        {
            'label': 'Paiement créé',
            'date': payment.created_at,
            'meta': f"Statut initial: {payment.get_status_display()}"
        },
        {
            'label': 'Date de paiement',
            'date': payment.paid_at,
            'meta': f"Méthode: {payment.get_method_display()}"
        },
    ]
    if payment.receipt_number:
        history.append({
            'label': 'Reçu généré',
            'date': payment.created_at,
            'meta': f"N° {payment.receipt_number}"
        })

    context = {
        'page_title': f'Paiement {payment.reference or payment.pk}',
        'active_menu': 'payments',
        'payment': payment,
        'history': history,
    }
    context.update(_build_payment_access_context(payment))
    return render(request, 'superadmin/payments/detail.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def payment_edit(request, pk):
    payment = get_object_or_404(
        Payment.objects.select_related('inscription__candidature__programme', 'inscription__student__user', 'agent__user'),
        pk=pk,
    )

    if payment.status == Payment.STATUS_VALIDATED:
        messages.warning(request, 'Un paiement validé est verrouillé et ne peut plus être édité.')
        return redirect('superadmin:payment_detail', pk=payment.pk)

    if request.method == 'POST':
        payment.reference = request.POST.get('reference', payment.reference)
        payment.method = request.POST.get('method', payment.method)
        raw_amount = request.POST.get('amount')
        try:
            payment.amount = int(raw_amount) if raw_amount else payment.amount
        except (TypeError, ValueError):
            messages.error(request, 'Montant invalide.')
            return redirect('superadmin:payment_edit', pk=payment.pk)

        requested_status = request.POST.get('status', payment.status)
        if requested_status in {value for value, _ in Payment.STATUS_CHOICES}:
            payment.status = requested_status

        try:
            payment.save()
        except (ValueError, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect('superadmin:payment_detail', pk=payment.pk)

        messages.success(request, f"Paiement '{payment.reference}' mis à jour!")
        return redirect('superadmin:payment_detail', pk=payment.pk)

    context = {
        'page_title': f'Modifier: {payment.reference or payment.pk}',
        'active_menu': 'payments',
        'payment': payment,
        'status_choices': Payment.STATUS_CHOICES,
        'method_choices': Payment.METHOD_CHOICES,
    }
    return render(request, 'superadmin/payments/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def payment_delete(request, pk):
    if request.method == 'POST':
        payment = get_object_or_404(Payment, pk=pk)
        if payment.status == Payment.STATUS_VALIDATED:
            messages.error(request, "Suppression impossible: un paiement valide est verrouille. Utilisez l'annulation metier si necessaire.")
        elif payment.status == Payment.STATUS_CANCELLED:
            messages.info(request, "Ce paiement est deja annule.")
        else:
            payment.status = Payment.STATUS_CANCELLED
            payment.save(update_fields=['status'])
            messages.success(request, f"Paiement '{payment.reference}' annule (suppression logique).")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/payments/'})
    return redirect('superadmin:payment_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def payment_validate(request, pk):
    if request.method != 'POST':
        return redirect('superadmin:payment_detail', pk=pk)

    payment = get_object_or_404(Payment.objects.select_related('inscription'), pk=pk)
    if payment.status != Payment.STATUS_PENDING:
        messages.warning(request, 'Seuls les paiements en attente peuvent être validés.')
        return redirect('superadmin:payment_detail', pk=pk)

    if _is_manual_payment_method(payment.method):
        if not payment.agent_id:
            payment.agent = _get_or_create_superadmin_agent(request.user, payment.inscription)
        inscription_branch = getattr(payment.inscription.candidature, 'branch', None)
        if not payment.agent_id or (inscription_branch and payment.agent.branch_id != inscription_branch.id):
            messages.error(
                request,
                "Validation bloquée: configurez un agent actif rattaché à l'annexe du dossier dans 'Agents paiement'."
            )
            return redirect('superadmin:payment_detail', pk=pk)

    payment.status = Payment.STATUS_VALIDATED
    update_fields = ['status']
    if payment.agent_id:
        update_fields.append('agent')
    try:
        payment.save(update_fields=update_fields)
    except (ValueError, ValidationError) as exc:
        messages.error(request, str(exc))
        return redirect('superadmin:payment_detail', pk=pk)

    if _is_manual_payment_method(payment.method):
        messages.success(request, f"Paiement validé avec succès. Code d'accès à transmettre: {payment.inscription.access_code}")
    else:
        messages.success(request, 'Paiement validé avec succès.')
    return redirect('superadmin:payment_detail', pk=pk)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def payment_receipt_pdf(request, pk):
    payment = get_object_or_404(Payment.objects.select_related('inscription__candidature__programme__cycle', 'inscription__candidature__branch'), pk=pk)

    try:
        _ensure_payment_receipt(payment)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('superadmin:payment_detail', pk=pk)

    if not payment.receipt_pdf:
        messages.error(request, "Impossible de générer le reçu PDF pour ce paiement.")
        return redirect('superadmin:payment_detail', pk=pk)

    return FileResponse(
        payment.receipt_pdf.open('rb'),
        as_attachment=True,
        filename=f"recu-{payment.receipt_number or payment.pk}.pdf",
    )


@user_passes_test(superuser_required, login_url='/accounts/login/')
def payment_notify_student(request, pk):
    if request.method != 'POST':
        return redirect('superadmin:payment_detail', pk=pk)

    payment = get_object_or_404(Payment.objects.select_related('inscription__candidature'), pk=pk)
    if payment.status != Payment.STATUS_VALIDATED:
        messages.warning(request, 'La notification est réservée aux paiements validés.')
        return redirect('superadmin:payment_detail', pk=pk)

    try:
        send_payment_confirmation_email(payment=payment)
    except Exception:
        messages.error(request, 'Échec lors de l\'envoi de notification. Vérifiez la configuration email.')
        return redirect('superadmin:payment_detail', pk=pk)

    messages.success(request, 'Notification envoyée à l\'étudiant/candidat.')
    return redirect('superadmin:payment_detail', pk=pk)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def payment_cash_session_list(request):
    search = request.GET.get('search', '').strip()
    branch = request.GET.get('branch', '').strip()
    agent = request.GET.get('agent', '').strip()
    status = request.GET.get('status', '').strip()

    sessions_qs = CashPaymentSession.objects.select_related(
        'inscription__candidature',
        'agent__user',
        'agent__branch',
    ).order_by('-created_at')

    if search:
        sessions_qs = sessions_qs.filter(
            Q(inscription__public_token__icontains=search)
            | Q(inscription__candidature__first_name__icontains=search)
            | Q(inscription__candidature__last_name__icontains=search)
            | Q(verification_code__icontains=search)
        )
    if branch:
        sessions_qs = sessions_qs.filter(agent__branch_id=branch)
    if agent:
        sessions_qs = sessions_qs.filter(agent_id=agent)

    now = timezone.now()
    if status == 'active':
        sessions_qs = sessions_qs.filter(is_used=False, expires_at__gt=now)
    elif status == 'used':
        sessions_qs = sessions_qs.filter(is_used=True)
    elif status == 'expired':
        sessions_qs = sessions_qs.filter(is_used=False, expires_at__lte=now)

    paginator = Paginator(sessions_qs, 20)
    sessions = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'superadmin/payments/cash_sessions_list.html', {
        'page_title': 'Sessions cash',
        'active_menu': 'payment_cash_sessions',
        'sessions': sessions,
        'branches': Branch.objects.filter(is_active=True).order_by('name').only('id', 'name'),
        'payment_agents': PaymentAgent.objects.select_related('user').filter(is_active=True).order_by('user__first_name', 'user__last_name'),
        'filters': {'search': search, 'branch': branch, 'agent': agent, 'status': status},
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def payment_cash_session_mark_used(request, pk):
    if request.method != 'POST':
        return redirect('superadmin:payment_cash_session_list')

    session = get_object_or_404(CashPaymentSession, pk=pk)
    if session.is_used:
        messages.info(request, 'Cette session est déjà marquée utilisée.')
    else:
        session.is_used = True
        session.save(update_fields=['is_used'])
        messages.success(request, 'Session cash marquée utilisée.')

    return redirect('superadmin:payment_cash_session_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def payment_agent_list(request):
    search = request.GET.get('search', '').strip()
    branch = request.GET.get('branch', '').strip()
    status = request.GET.get('status', '').strip()

    agents_qs = PaymentAgent.objects.select_related('user', 'branch').order_by('user__first_name', 'user__last_name')

    if search:
        agents_qs = agents_qs.filter(
            Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
            | Q(user__email__icontains=search)
            | Q(agent_code__icontains=search)
        )

    if branch:
        agents_qs = agents_qs.filter(branch_id=branch)

    if status == 'active':
        agents_qs = agents_qs.filter(is_active=True)
    elif status == 'inactive':
        agents_qs = agents_qs.filter(is_active=False)

    paginator = Paginator(agents_qs, 20)
    agents = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'superadmin/payments/agents_list.html', {
        'page_title': 'Agents de paiement',
        'active_menu': 'payment_agents',
        'agents': agents,
        'branches': Branch.objects.filter(is_active=True).order_by('name').only('id', 'name'),
        'filters': {'search': search, 'branch': branch, 'status': status},
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def payment_agent_create(request):
    staff_users = User.objects.filter(is_staff=True, is_active=True, payment_agent_profile__isnull=True).order_by('first_name', 'last_name', 'username')
    branches = Branch.objects.filter(is_active=True).order_by('name')

    if request.method == 'POST':
        user_id = request.POST.get('user', '').strip()
        branch_id = request.POST.get('branch', '').strip()

        if not user_id or not branch_id:
            messages.error(request, 'Utilisateur et annexe sont obligatoires.')
        elif PaymentAgent.objects.filter(user_id=user_id).exists():
            messages.error(request, 'Cet utilisateur possède déjà un profil agent.')
        else:
            PaymentAgent.objects.create(
                user_id=user_id,
                branch_id=branch_id,
                is_active=request.POST.get('is_active') == 'on',
            )
            messages.success(request, 'Agent de paiement créé avec succès.')
            return redirect('superadmin:payment_agent_list')

    return render(request, 'superadmin/payments/agents_form.html', {
        'page_title': 'Nouvel agent de paiement',
        'active_menu': 'payment_agents',
        'agent': None,
        'staff_users': staff_users,
        'branches': branches,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def payment_agent_edit(request, pk):
    agent = get_object_or_404(PaymentAgent, pk=pk)
    staff_users = User.objects.filter(
        Q(is_staff=True, is_active=True, payment_agent_profile__isnull=True) | Q(pk=agent.user_id)
    ).order_by('first_name', 'last_name', 'username').distinct()
    branches = Branch.objects.filter(is_active=True).order_by('name')

    if request.method == 'POST':
        user_id = request.POST.get('user', '').strip()
        branch_id = request.POST.get('branch', '').strip()

        if not user_id or not branch_id:
            messages.error(request, 'Utilisateur et annexe sont obligatoires.')
        elif PaymentAgent.objects.filter(user_id=user_id).exclude(pk=agent.pk).exists():
            messages.error(request, 'Cet utilisateur possède déjà un profil agent.')
        else:
            agent.user_id = user_id
            agent.branch_id = branch_id
            agent.is_active = request.POST.get('is_active') == 'on'
            agent.save(update_fields=['user', 'branch', 'is_active'])
            messages.success(request, 'Agent de paiement mis à jour.')
            return redirect('superadmin:payment_agent_list')

    return render(request, 'superadmin/payments/agents_form.html', {
        'page_title': f"Modifier agent {agent.agent_code}",
        'active_menu': 'payment_agents',
        'agent': agent,
        'staff_users': staff_users,
        'branches': branches,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def payment_agent_toggle(request, pk):
    if request.method != 'POST':
        return redirect('superadmin:payment_agent_list')

    agent = get_object_or_404(PaymentAgent, pk=pk)
    agent.is_active = not agent.is_active
    agent.save(update_fields=['is_active'])
    messages.success(request, 'Statut agent mis à jour.')
    return redirect('superadmin:payment_agent_list')


# ============================================
# USER MANAGEMENT
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def user_list(request):
    search = request.GET.get('search', '').strip()
    role = request.GET.get('role', '').strip()
    group = request.GET.get('group', '').strip()
    status = request.GET.get('status', '').strip()

    users_qs = (
        User.objects
        .select_related('profile', 'profile__branch')
        .prefetch_related('groups')
        .order_by('-date_joined')
    )

    if search:
        users_qs = users_qs.filter(
            Q(username__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(email__icontains=search)
        )

    if role:
        users_qs = users_qs.filter(profile__role=role)

    if group:
        users_qs = users_qs.filter(groups__id=group)

    if status == 'active':
        users_qs = users_qs.filter(is_active=True)
    elif status == 'inactive':
        users_qs = users_qs.filter(is_active=False)

    users_qs = users_qs.distinct()
    paginator = Paginator(users_qs, 20)
    users_page = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'superadmin/users/list.html', {
        'page_title': 'Utilisateurs staff',
        'active_menu': 'users',
        'users': users_page,
        'groups': _managed_groups_queryset(),
        'role_choices': Profile.ROLE_CHOICES,
        'filters': {
            'search': search,
            'role': role,
            'group': group,
            'status': status,
        },
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def user_create(request):
    groups = _managed_groups_queryset()
    branches = Branch.objects.filter(is_active=True).order_by('name')
    form_data = {
        'username': '',
        'email': '',
        'first_name': '',
        'last_name': '',
        'role': '',
        'branch': '',
        'is_staff': True,
        'is_active': True,
    }
    selected_group_ids = []

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        password = request.POST.get('password', '').strip()
        role = request.POST.get('role', '').strip()
        branch_id = request.POST.get('branch', '').strip()
        selected_groups = request.POST.getlist('groups')
        is_staff = request.POST.get('is_staff') == 'on'
        is_active = request.POST.get('is_active') == 'on'

        form_data = {
            'username': username,
            'email': email,
            'first_name': first_name,
            'last_name': last_name,
            'role': role,
            'branch': branch_id,
            'is_staff': is_staff,
            'is_active': is_active,
        }
        selected_group_ids = [str(group_id) for group_id in selected_groups]

        if not username or not password:
            messages.error(request, 'Nom utilisateur et mot de passe sont obligatoires.')
        elif User.objects.filter(username=username).exists():
            messages.error(request, 'Ce nom utilisateur existe deja.')
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                is_staff=is_staff,
                is_active=is_active,
            )

            profile, _ = Profile.objects.get_or_create(user=user)
            profile.role = role
            profile.branch_id = branch_id or None
            profile.save(update_fields=['role', 'branch'])

            user.groups.set(groups.filter(id__in=selected_groups))
            messages.success(request, 'Utilisateur cree avec succes.')
            return redirect('superadmin:user_list')

    return render(request, 'superadmin/users/form.html', {
        'page_title': 'Nouvel utilisateur',
        'active_menu': 'users',
        'target_user': None,
        'groups': groups,
        'role_choices': Profile.ROLE_CHOICES,
        'branches': branches,
        'form_data': form_data,
        'selected_group_ids': selected_group_ids,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def user_edit(request, pk):
    target_user = get_object_or_404(
        User.objects.select_related('profile', 'profile__branch').prefetch_related('groups'),
        pk=pk,
    )
    groups = _managed_groups_queryset()
    branches = Branch.objects.filter(is_active=True).order_by('name')
    profile, _ = Profile.objects.get_or_create(user=target_user)
    form_data = {
        'username': target_user.username,
        'email': target_user.email,
        'first_name': target_user.first_name,
        'last_name': target_user.last_name,
        'role': profile.role or '',
        'branch': str(profile.branch_id) if profile.branch_id else '',
        'is_staff': target_user.is_staff,
        'is_active': target_user.is_active,
    }
    selected_group_ids = [str(group.id) for group in target_user.groups.all()]

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        role = request.POST.get('role', '').strip()
        branch_id = request.POST.get('branch', '').strip()
        selected_groups = request.POST.getlist('groups')
        is_staff = request.POST.get('is_staff') == 'on'
        is_active = request.POST.get('is_active') == 'on'

        form_data = {
            'username': username,
            'email': email,
            'first_name': first_name,
            'last_name': last_name,
            'role': role,
            'branch': branch_id,
            'is_staff': is_staff,
            'is_active': is_active,
        }
        selected_group_ids = [str(group_id) for group_id in selected_groups]

        if not username:
            messages.error(request, 'Le nom utilisateur est obligatoire.')
        elif User.objects.filter(username=username).exclude(pk=target_user.pk).exists():
            messages.error(request, 'Ce nom utilisateur existe deja.')
        else:
            target_user.username = username
            target_user.email = email
            target_user.first_name = first_name
            target_user.last_name = last_name
            target_user.is_staff = is_staff
            target_user.is_active = is_active

            new_password = request.POST.get('password', '').strip()
            if new_password:
                target_user.set_password(new_password)

            target_user.save()

            profile.role = role
            profile.branch_id = branch_id or None
            profile.save(update_fields=['role', 'branch'])

            target_user.groups.set(groups.filter(id__in=selected_groups))

            messages.success(request, 'Utilisateur mis a jour avec succes.')
            return redirect('superadmin:user_list')

    return render(request, 'superadmin/users/form.html', {
        'page_title': f"Modifier utilisateur {target_user.username}",
        'active_menu': 'users',
        'target_user': target_user,
        'groups': groups,
        'role_choices': Profile.ROLE_CHOICES,
        'branches': branches,
        'form_data': form_data,
        'selected_group_ids': selected_group_ids,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def user_toggle_active(request, pk):
    if request.method != 'POST':
        return redirect('superadmin:user_list')

    target_user = get_object_or_404(User, pk=pk)
    if target_user.pk == request.user.pk and target_user.is_superuser and target_user.is_active:
        messages.error(request, 'Vous ne pouvez pas desactiver votre propre compte superadmin.')
        return redirect('superadmin:user_list')

    target_user.is_active = not target_user.is_active
    target_user.save(update_fields=['is_active'])
    messages.success(request, 'Statut utilisateur mis a jour.')
    return redirect('superadmin:user_list')


# ============================================
# FEES
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def fee_list(request):
    fees = Fee.objects.select_related('programme_year__programme').order_by('-programme_year__programme__title')
    programme = request.GET.get('programme', '')

    if programme:
        fees = fees.filter(programme_year__programme_id=programme)

    paginator = Paginator(fees, 20)
    page = request.GET.get('page', 1)
    fees = paginator.get_page(page)

    context = {
        'page_title': 'Frais',
        'active_menu': 'fees',
        'fees': fees,
        'programmes': Programme.objects.all(),
        'filters': {'programme': programme},
    }

    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/fees/_fee_table.html', context)
    return render(request, 'superadmin/fees/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def fee_create(request):
    if request.method == 'POST':
        programme_year_id = request.POST.get('programme_year')
        if not programme_year_id:
            messages.error(request, "Année du programme obligatoire.")
            return redirect('superadmin:fee_create')

        Fee.objects.create(
            programme_year_id=programme_year_id,
            label=request.POST.get('label'),
            amount=request.POST.get('amount'),
            due_month=request.POST.get('due_month'),
        )
        messages.success(request, "Frais créé!")
        return redirect('superadmin:fee_list')

    context = {
        'page_title': 'Nouveau Frais',
        'active_menu': 'fees',
        'programme_years': ProgrammeYear.objects.select_related('programme').all(),
    }
    return render(request, 'superadmin/fees/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def fee_edit(request, pk):
    fee = get_object_or_404(Fee, pk=pk)

    if request.method == 'POST':
        fee.label = request.POST.get('label', fee.label)
        fee.amount = request.POST.get('amount', fee.amount)
        fee.due_month = request.POST.get('due_month', fee.due_month)
        fee.save()
        messages.success(request, f"Frais '{fee.label}' mis à jour!")
        return redirect('superadmin:fee_list')

    context = {
        'page_title': f'Modifier: {fee.label}',
        'active_menu': 'fees',
        'fee': fee,
        'programme_years': ProgrammeYear.objects.select_related('programme').all(),
    }
    return render(request, 'superadmin/fees/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def fee_delete(request, pk):
    if request.method == 'POST':
        fee = get_object_or_404(Fee, pk=pk)
        response = _safe_delete(
            request,
            fee,
            success_message=f"Frais '{fee.label}' supprimé!",
            protected_message="Suppression impossible: ce frais est deja utilise par des donnees d'inscription.",
            hx_redirect='/superadmin/fees/',
        )
        if response:
            return response
    return redirect('superadmin:fee_list')


# ============================================
# ARTICLES
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def article_list(request):
    base_articles_qs = Article.objects.filter(is_deleted=False)
    articles_qs = (
        base_articles_qs.select_related('author', 'category')
        .order_by('-published_at', '-created_at')
    )

    search = request.GET.get('search', '').strip()
    status = request.GET.get('status', '').strip()
    category = request.GET.get('category', '').strip()

    if search:
        articles_qs = articles_qs.filter(
            Q(title__icontains=search)
            | Q(excerpt__icontains=search)
            | Q(content__icontains=search)
        )
    if status:
        articles_qs = articles_qs.filter(status=status)
    if category:
        articles_qs = articles_qs.filter(category_id=category)

    paginator = Paginator(articles_qs, 20)
    articles = paginator.get_page(request.GET.get('page', 1))

    context = {
        'page_title': 'Articles Blog',
        'active_menu': 'articles',
        'articles': articles,
        'categories': BlogCategory.objects.filter(is_active=True).order_by('name'),
        'status_choices': Article.STATUS_CHOICES,
        'filters': {'search': search, 'status': status, 'category': category},
        'articles_total_count': base_articles_qs.count(),
        'articles_published_count': base_articles_qs.filter(status='published').count(),
        'articles_draft_count': base_articles_qs.filter(status='draft').count(),
        'articles_archived_count': base_articles_qs.filter(status='archived').count(),
        'comments_pending_count': Comment.objects.filter(status=Comment.STATUS_PENDING).count(),
        'comments_flagged_count': Comment.objects.filter(status=Comment.STATUS_PENDING, flagged=True).count(),
    }

    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/articles/_list_table.html', context)

    return render(request, 'superadmin/articles/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def article_create(request):
    form = ArticleForm(request.POST or None)

    if request.method == 'POST':
        if form.is_valid():
            article = form.save(commit=False)
            article.author = request.user
            article.is_deleted = False
            article.save()
            form.save_m2m()
            messages.success(request, f"Article '{article.title}' créé!")
            return redirect('superadmin:article_list')

        messages.error(request, "Veuillez corriger les champs du formulaire article.")

    return render(request, 'superadmin/articles/form.html', {
        'page_title': 'Nouvel Article',
        'active_menu': 'articles',
        'form': form,
        'article': None,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def article_detail(request, pk):
    article = get_object_or_404(Article.objects.select_related('author', 'category'), pk=pk, is_deleted=False)
    return render(request, 'superadmin/articles/detail.html', {
        'page_title': article.title,
        'active_menu': 'articles',
        'article': article,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def article_edit(request, pk):
    article = get_object_or_404(Article, pk=pk, is_deleted=False)
    form = ArticleForm(request.POST or None, instance=article)

    if request.method == 'POST':
        if form.is_valid():
            article = form.save()
            messages.success(request, f"Article '{article.title}' mis à jour!")
            return redirect('superadmin:article_list')

        messages.error(request, "Veuillez corriger les champs du formulaire article.")

    return render(request, 'superadmin/articles/form.html', {
        'page_title': f'Modifier: {article.title}',
        'active_menu': 'articles',
        'article': article,
        'form': form,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def article_delete(request, pk):
    if request.method == 'POST':
        article = get_object_or_404(Article, pk=pk)
        article.is_deleted = True
        article.save(update_fields=['is_deleted', 'updated_at'])
        messages.success(request, "Article supprimé!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/articles/'})
    return redirect('superadmin:article_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_article(request, pk):
    if request.method != 'POST':
        messages.error(request, "Action invalide: utilisez le bouton de publication.")
        return redirect('superadmin:article_list')

    article = get_object_or_404(Article, pk=pk, is_deleted=False)
    article.status = 'draft' if article.status == 'published' else 'published'
    if article.status == 'published' and not article.published_at:
        article.published_at = timezone.now()
    article.save(update_fields=['status', 'published_at', 'updated_at'])
    if request.headers.get('HX-Request'):
        badge_css = 'badge-status badge-success' if article.status == 'published' else 'badge-status badge-draft'
        badge_label = 'Publié' if article.status == 'published' else 'Brouillon'
        return HttpResponse(
            f'<span class="{badge_css}">{badge_label}</span>',
            headers={'HX-Trigger': '{"showToast": "Statut mis à jour"}'},
        )
    messages.success(request, "Statut mis à jour!")
    return redirect('superadmin:article_list')


# ============================================
# CATEGORIES
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def category_list(request):
    categories = BlogCategory.objects.annotate(articles_count=Count('articles')).order_by('name')
    return render(request, 'superadmin/categories/list.html', {'page_title': 'Catégories Blog', 'categories': categories, 'active_menu': 'categories'})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def category_create(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        if name:
            BlogCategory.objects.create(name=name, slug=slugify(name), description=request.POST.get('description', ''))
            messages.success(request, 'Catégorie créée!')
            return redirect('superadmin:category_list')
    return render(request, 'superadmin/categories/form.html', {'page_title': 'Nouvelle catégorie', 'active_menu': 'categories'})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def category_edit(request, pk):
    category = get_object_or_404(BlogCategory, pk=pk)
    if request.method == 'POST':
        category.name = request.POST.get('name', '').strip()
        category.slug = slugify(category.name)
        category.description = request.POST.get('description', '').strip()
        category.save()
        messages.success(request, 'Catégorie mise à jour!')
        return redirect('superadmin:category_list')
    return render(request, 'superadmin/categories/form.html', {'page_title': f'Modifier: {category.name}', 'category': category, 'active_menu': 'categories'})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def category_delete(request, pk):
    if request.method == 'POST':
        category = get_object_or_404(BlogCategory, pk=pk)
        category.delete()
        messages.success(request, 'Catégorie supprimée!')
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/categories/'})
    return redirect('superadmin:category_list')


# ============================================
# NEWS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def news_list(request):
    news_qs = News.objects.select_related('categorie', 'auteur').order_by('-published_at', '-created_at')

    search = request.GET.get('search', '').strip()
    status = request.GET.get('status', '').strip()
    category = request.GET.get('category', '').strip()
    urgent = request.GET.get('urgent', '').strip()

    if search:
        news_qs = news_qs.filter(
            Q(titre__icontains=search)
            | Q(resume__icontains=search)
            | Q(contenu__icontains=search)
        )
    if status:
        news_qs = news_qs.filter(status=status)
    if category:
        news_qs = news_qs.filter(categorie_id=category)
    if urgent == '1':
        news_qs = news_qs.filter(is_urgent=True)

    paginator = Paginator(news_qs, 20)
    news_page = paginator.get_page(request.GET.get('page', 1))

    context = {
        'page_title': 'Actualités',
        'active_menu': 'news',
        'news_list': news_page,
        'status_choices': News.STATUS_CHOICES,
        'categories': NewsCategory.objects.filter(is_active=True).order_by('nom'),
        'filters': {
            'search': search,
            'status': status,
            'category': category,
            'urgent': urgent,
        },
        'news_total_count': News.objects.count(),
        'news_published_count': News.objects.filter(status=News.STATUS_PUBLISHED).count(),
        'news_draft_count': News.objects.filter(status=News.STATUS_DRAFT).count(),
        'news_archived_count': News.objects.filter(status=News.STATUS_ARCHIVED).count(),
        'news_urgent_count': News.objects.filter(status=News.STATUS_PUBLISHED, is_urgent=True).count(),
    }

    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/news/_list_table.html', context)

    return render(request, 'superadmin/news/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def news_create(request):
    categories = NewsCategory.objects.filter(is_active=True).order_by('ordre', 'nom')

    if request.method == 'POST':
        titre = request.POST.get('titre', '').strip()
        categorie_id = request.POST.get('categorie')
        contenu = request.POST.get('contenu', '').strip()

        if not titre or not categorie_id or not contenu:
            messages.error(request, 'Titre, catégorie et contenu sont obligatoires.')
        else:
            news_item = News.objects.create(
                titre=titre,
                resume=request.POST.get('resume', '').strip(),
                contenu=contenu,
                categorie_id=request.POST.get('categorie'),
                status=request.POST.get('status', News.STATUS_DRAFT),
                is_important=request.POST.get('is_important') == 'on',
                is_urgent=request.POST.get('is_urgent') == 'on',
                auteur=request.user,
            )
            status_label = dict(News.STATUS_CHOICES).get(news_item.status, "Brouillon")
            messages.success(request, f"Actualité '{news_item.titre}' enregistrée ({status_label}).")
            return redirect('superadmin:news_list')

    return render(request, 'superadmin/news/form.html', {
        'page_title': 'Nouvelle actualité',
        'active_menu': 'news',
        'news_item': None,
        'categories': categories,
        'status_choices': News.STATUS_CHOICES,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def news_detail(request, pk):
    news_item = get_object_or_404(News, pk=pk)
    return render(request, 'superadmin/news/detail.html', {
        'page_title': news_item.titre,
        'active_menu': 'news',
        'news_item': news_item,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def news_edit(request, pk):
    news_item = get_object_or_404(News, pk=pk)
    categories = NewsCategory.objects.filter(is_active=True).order_by('ordre', 'nom')

    if request.method == 'POST':
        news_item.titre = request.POST.get('titre', '').strip() or news_item.titre
        news_item.resume = request.POST.get('resume', '').strip()
        news_item.contenu = request.POST.get('contenu', '').strip()
        news_item.categorie_id = request.POST.get('categorie') or news_item.categorie_id
        news_item.status = request.POST.get('status', news_item.status)
        news_item.is_important = request.POST.get('is_important') == 'on'
        news_item.is_urgent = request.POST.get('is_urgent') == 'on'
        news_item.auteur = request.user
        news_item.save()
        status_label = dict(News.STATUS_CHOICES).get(news_item.status, "Brouillon")
        messages.success(request, f"Actualité '{news_item.titre}' mise à jour ({status_label}).")
        return redirect('superadmin:news_list')

    return render(request, 'superadmin/news/form.html', {
        'page_title': f'Modifier: {news_item.titre}',
        'active_menu': 'news',
        'news_item': news_item,
        'categories': categories,
        'status_choices': News.STATUS_CHOICES,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def news_delete(request, pk):
    if request.method == 'POST':
        news_item = get_object_or_404(News, pk=pk)
        news_item.status = News.STATUS_ARCHIVED
        news_item.save(update_fields=['status', 'updated_at'])
        messages.success(request, "Actualité archivée.")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/news/'})
    return redirect('superadmin:news_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_news(request, pk):
    news_item = get_object_or_404(News, pk=pk)
    news_item.status = News.STATUS_DRAFT if news_item.status == News.STATUS_PUBLISHED else News.STATUS_PUBLISHED
    if news_item.status == News.STATUS_PUBLISHED and not news_item.published_at:
        news_item.published_at = timezone.now()
    news_item.save(update_fields=['status', 'published_at', 'updated_at'])

    if request.headers.get('HX-Request'):
        badge_css = 'badge-status badge-success' if news_item.status == News.STATUS_PUBLISHED else 'badge-status badge-draft'
        badge_label = 'Publié' if news_item.status == News.STATUS_PUBLISHED else 'Brouillon'
        return HttpResponse(
            f'<span class="{badge_css}">{badge_label}</span>',
            headers={'HX-Trigger': '{"showToast": "Statut mis à jour"}'},
        )

    messages.success(request, "Statut de publication mis à jour.")
    return redirect('superadmin:news_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def result_list(request):
    results_qs = ResultSession.objects.order_by('-annee_academique', '-created_at')

    search = request.GET.get('search', '').strip()
    type_value = request.GET.get('type', '').strip()
    annee = request.GET.get('annee', '').strip()
    published = request.GET.get('published', '').strip()

    if search:
        results_qs = results_qs.filter(
            Q(titre__icontains=search)
            | Q(classe__icontains=search)
            | Q(filiere__icontains=search)
            | Q(annexe__icontains=search)
        )
    if type_value:
        results_qs = results_qs.filter(type=type_value)
    if annee:
        results_qs = results_qs.filter(annee_academique=annee)
    if published == '1':
        results_qs = results_qs.filter(is_published=True)
    elif published == '0':
        results_qs = results_qs.filter(is_published=False)

    paginator = Paginator(results_qs, 20)
    results_page = paginator.get_page(request.GET.get('page', 1))

    context = {
        'page_title': 'Résultats académiques',
        'active_menu': 'results',
        'results_list': results_page,
        'result_type_choices': ResultSession.TYPE_CHOICES,
        'years': (
            ResultSession.objects
            .values_list('annee_academique', flat=True)
            .distinct()
            .order_by('-annee_academique')
        ),
        'filters': {
            'search': search,
            'type': type_value,
            'annee': annee,
            'published': published,
        },
        'results_total_count': ResultSession.objects.count(),
        'results_published_count': ResultSession.objects.filter(is_published=True).count(),
        'results_draft_count': ResultSession.objects.filter(is_published=False).count(),
    }

    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/results/_list_table.html', context)

    return render(request, 'superadmin/results/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def result_create(request):
    if request.method == 'POST':
        titre = request.POST.get('titre', '').strip()
        type_value = request.POST.get('type', '').strip()
        annee = request.POST.get('annee_academique', '').strip()
        annexe = request.POST.get('annexe', '').strip()
        filiere = request.POST.get('filiere', '').strip()
        classe = request.POST.get('classe', '').strip()
        fichier_pdf = request.FILES.get('fichier_pdf')

        if not all([titre, type_value, annee, annexe, filiere, classe, fichier_pdf]):
            messages.error(request, 'Tous les champs et le PDF sont obligatoires.')
        else:
            result = ResultSession.objects.create(
                titre=titre,
                type=type_value,
                annee_academique=annee,
                annexe=annexe,
                filiere=filiere,
                classe=classe,
                fichier_pdf=fichier_pdf,
                is_published=request.POST.get('is_published') == 'on',
            )
            messages.success(request, f"Résultat '{result.titre}' importé.")
            return redirect('superadmin:result_list')

    return render(request, 'superadmin/results/form.html', {
        'page_title': 'Importer un résultat',
        'active_menu': 'results',
        'result_item': None,
        'result_type_choices': ResultSession.TYPE_CHOICES,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def result_edit(request, pk):
    result_item = get_object_or_404(ResultSession, pk=pk)

    if request.method == 'POST':
        result_item.titre = request.POST.get('titre', '').strip() or result_item.titre
        result_item.type = request.POST.get('type', '').strip() or result_item.type
        result_item.annee_academique = request.POST.get('annee_academique', '').strip() or result_item.annee_academique
        result_item.annexe = request.POST.get('annexe', '').strip() or result_item.annexe
        result_item.filiere = request.POST.get('filiere', '').strip() or result_item.filiere
        result_item.classe = request.POST.get('classe', '').strip() or result_item.classe
        result_item.is_published = request.POST.get('is_published') == 'on'
        if request.FILES.get('fichier_pdf'):
            result_item.fichier_pdf = request.FILES['fichier_pdf']
        result_item.save()

        state = 'publié' if result_item.is_published else 'brouillon'
        messages.success(request, f"Résultat '{result_item.titre}' mis à jour ({state}).")
        return redirect('superadmin:result_list')

    return render(request, 'superadmin/results/form.html', {
        'page_title': f"Modifier: {result_item.titre}",
        'active_menu': 'results',
        'result_item': result_item,
        'result_type_choices': ResultSession.TYPE_CHOICES,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def result_delete(request, pk):
    if request.method == 'POST':
        result_item = get_object_or_404(ResultSession, pk=pk)
        result_title = result_item.titre
        result_item.delete()
        messages.success(request, f"Résultat '{result_title}' supprimé.")
    return redirect('superadmin:result_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_result(request, pk):
    result_item = get_object_or_404(ResultSession, pk=pk)
    result_item.is_published = not result_item.is_published
    result_item.save(update_fields=['is_published'])

    label = 'publié' if result_item.is_published else 'brouillon'
    messages.success(request, f"Résultat '{result_item.titre}' basculé en {label}.")
    return redirect('superadmin:result_list')


# ============================================
# EVENTS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def event_list(request):
    search = request.GET.get('search', '').strip()
    type_id = request.GET.get('type', '').strip()
    publication = request.GET.get('publication', '').strip()

    events_qs = Event.objects.select_related('event_type').annotate(total_media=Count('media_items'))

    if search:
        events_qs = events_qs.filter(Q(title__icontains=search) | Q(description__icontains=search))
    if type_id:
        events_qs = events_qs.filter(event_type_id=type_id)
    if publication == 'published':
        events_qs = events_qs.filter(is_published=True)
    elif publication == 'draft':
        events_qs = events_qs.filter(is_published=False)

    events = events_qs.order_by('-event_date', '-created_at')

    return render(request, 'superadmin/events/list.html', {
        'page_title': 'Événements',
        'active_menu': 'events',
        'events': events,
        'event_types': EventType.objects.filter(is_active=True).order_by('name'),
        'filters': {'search': search, 'type': type_id, 'publication': publication},
        'events_total_count': Event.objects.count(),
        'events_published_count': Event.objects.filter(is_published=True).count(),
        'events_draft_count': Event.objects.filter(is_published=False).count(),
        'events_media_count': MediaItem.objects.count(),
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def event_create(request):
    event_types = EventType.objects.filter(is_active=True).order_by('name')

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        event_type_id = request.POST.get('event_type', '').strip()
        event_date = request.POST.get('event_date', '').strip()

        if not title or not event_type_id or not event_date:
            messages.error(request, 'Titre, type et date sont obligatoires.')
        else:
            event = Event.objects.create(
                title=title,
                event_type_id=event_type_id,
                event_date=event_date,
                description=request.POST.get('description', '').strip(),
                is_published=request.POST.get('is_published') == 'on',
                cover_image=request.FILES.get('cover_image'),
            )
            messages.success(request, f"Événement '{event.title}' créé.")
            return redirect('superadmin:event_list')

    return render(request, 'superadmin/events/form.html', {
        'page_title': 'Nouvel événement',
        'active_menu': 'events',
        'event': None,
        'event_types': event_types,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def event_detail(request, pk):
    event = get_object_or_404(Event.objects.select_related('event_type'), pk=pk)
    media_items = event.media_items.order_by('-created_at')
    return render(request, 'superadmin/events/detail.html', {
        'page_title': event.title,
        'active_menu': 'events',
        'event': event,
        'media_items': media_items,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk)
    event_types = EventType.objects.filter(is_active=True).order_by('name')

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        event_type_id = request.POST.get('event_type', '').strip()
        event_date = request.POST.get('event_date', '').strip()

        if not title or not event_type_id or not event_date:
            messages.error(request, 'Titre, type et date sont obligatoires.')
        else:
            event.title = title
            event.event_type_id = event_type_id
            event.event_date = event_date
            event.description = request.POST.get('description', '').strip()
            event.is_published = request.POST.get('is_published') == 'on'
            if request.FILES.get('cover_image'):
                event.cover_image = request.FILES['cover_image']
            event.save()
            messages.success(request, f"Événement '{event.title}' mis à jour.")
            return redirect('superadmin:event_list')

    return render(request, 'superadmin/events/form.html', {
        'page_title': f'Modifier: {event.title}',
        'active_menu': 'events',
        'event': event,
        'event_types': event_types,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def event_delete(request, pk):
    if request.method == 'POST':
        event = get_object_or_404(Event, pk=pk)
        event.delete()
        messages.success(request, 'Événement supprimé.')
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/events/'})
    return redirect('superadmin:event_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_event(request, pk):
    event = get_object_or_404(Event, pk=pk)
    event.is_published = not event.is_published
    event.save(update_fields=['is_published', 'updated_at'])
    messages.success(request, 'Statut de publication mis à jour.')
    return redirect('superadmin:event_list')


# ============================================
# GALERIE (Media des événements)
# ============================================

def _gallery_redirect_url(request):
    params = {
        'event': request.POST.get('event', '').strip(),
        'type': request.POST.get('type', '').strip(),
        'featured': request.POST.get('featured', '').strip(),
    }
    params = {k: v for k, v in params.items() if v}
    base_url = reverse('superadmin:gallery_list')
    return f"{base_url}?{urlencode(params)}" if params else base_url

@user_passes_test(superuser_required, login_url='/accounts/login/')
def gallery_list(request):
    event_id = request.GET.get('event', '').strip()
    media_type = request.GET.get('type', '').strip()
    featured = request.GET.get('featured', '').strip()

    media_qs = MediaItem.objects.select_related('event')
    if event_id:
        media_qs = media_qs.filter(event_id=event_id)
    if media_type in {MediaItem.IMAGE, MediaItem.VIDEO}:
        media_qs = media_qs.filter(media_type=media_type)
    if featured == '1':
        media_qs = media_qs.filter(is_featured=True)

    return render(request, 'superadmin/gallery/list.html', {
        'page_title': 'Galerie',
        'active_menu': 'gallery',
        'media_items': media_qs.order_by('-created_at'),
        'events': Event.objects.order_by('-event_date', 'title'),
        'filters': {'event': event_id, 'type': media_type, 'featured': featured},
        'media_total_count': MediaItem.objects.count(),
        'media_image_count': MediaItem.objects.filter(media_type=MediaItem.IMAGE).count(),
        'media_video_count': MediaItem.objects.filter(media_type=MediaItem.VIDEO).count(),
        'media_featured_count': MediaItem.objects.filter(is_featured=True).count(),
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def gallery_bulk_upload(request):
    events = Event.objects.order_by('-event_date', 'title')
    selected_event_id = request.GET.get('event', '').strip()

    if request.method == 'POST':
        selected_event_id = request.POST.get('event', '').strip()
        event = None
        if selected_event_id:
            event = Event.objects.filter(pk=selected_event_id).first()

        media_files = request.FILES.getlist('media_files')
        is_featured = request.POST.get('is_featured') == 'on'
        use_filename_caption = request.POST.get('use_filename_caption') == 'on'

        if not event:
            messages.error(request, 'Veuillez choisir un événement.')
        elif not media_files:
            messages.error(request, 'Veuillez sélectionner au moins un fichier média.')
        else:
            result = create_event_media_batch(
                event,
                media_files,
                is_featured=is_featured,
                use_filename_caption=use_filename_caption,
                max_files=50,
            )
            created_count = len(result['created'])
            errors = result['errors']

            if created_count:
                messages.success(request, f'{created_count} média(s) importé(s) avec succès.')
            if errors:
                messages.warning(request, f'{len(errors)} fichier(s) ignoré(s).')
                for err in errors[:5]:
                    messages.warning(request, err)

            return redirect(f"{reverse('superadmin:gallery_list')}?event={event.pk}")

    return render(request, 'superadmin/gallery/bulk_form.html', {
        'page_title': 'Upload en lot',
        'active_menu': 'gallery',
        'events': events,
        'selected_event_id': selected_event_id,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def gallery_bulk_action(request):
    if request.method != 'POST':
        return redirect('superadmin:gallery_list')

    action = request.POST.get('action', '').strip()
    selected_ids = request.POST.getlist('media_ids')
    redirect_url = _gallery_redirect_url(request)

    if not selected_ids:
        messages.error(request, 'Sélectionnez au moins un média.')
        return redirect(redirect_url)

    queryset = MediaItem.objects.filter(pk__in=selected_ids)
    total = queryset.count()

    if not total:
        messages.error(request, 'Aucun média valide sélectionné.')
        return redirect(redirect_url)

    if action == 'feature_on':
        updated = queryset.update(is_featured=True)
        messages.success(request, f'{updated} média(s) mis en avant.')
    elif action == 'feature_off':
        updated = queryset.update(is_featured=False)
        messages.success(request, f'{updated} média(s) retiré(s) de la mise en avant.')
    elif action == 'delete':
        deleted_count, _ = queryset.delete()
        messages.success(request, f'{deleted_count} média(s) supprimé(s).')
    else:
        messages.error(request, 'Action groupée invalide.')

    return redirect(redirect_url)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def gallery_create(request):
    events = Event.objects.order_by('-event_date', 'title')
    selected_event_id = request.GET.get('event', '').strip()

    if request.method == 'POST':
        event_id = request.POST.get('event', '').strip()
        media_type = request.POST.get('media_type', '').strip()
        image = request.FILES.get('image')
        video_file = request.FILES.get('video_file')
        video_url = request.POST.get('video_url', '').strip()

        if not event_id or media_type not in {MediaItem.IMAGE, MediaItem.VIDEO}:
            messages.error(request, 'Événement et type de média sont obligatoires.')
        elif media_type == MediaItem.IMAGE and not image:
            messages.error(request, 'Ajoutez une image pour un média de type image.')
        elif media_type == MediaItem.VIDEO and not (video_file or video_url):
            messages.error(request, 'Ajoutez un fichier vidéo ou une URL vidéo.')
        else:
            media = MediaItem.objects.create(
                event_id=event_id,
                media_type=media_type,
                image=image if media_type == MediaItem.IMAGE else None,
                video_file=video_file if media_type == MediaItem.VIDEO else None,
                video_url=(video_url or None) if media_type == MediaItem.VIDEO else None,
                caption=request.POST.get('caption', '').strip(),
                is_featured=request.POST.get('is_featured') == 'on',
            )
            messages.success(request, f"Média ajouté pour '{media.event.title}'.")
            return redirect('superadmin:gallery_list')

    return render(request, 'superadmin/gallery/form.html', {
        'page_title': 'Nouveau média',
        'active_menu': 'gallery',
        'media_item': None,
        'events': events,
        'media_types': MediaItem.TYPE_CHOICES,
        'selected_event_id': selected_event_id,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def gallery_edit(request, pk):
    media_item = get_object_or_404(MediaItem, pk=pk)
    events = Event.objects.order_by('-event_date', 'title')

    if request.method == 'POST':
        event_id = request.POST.get('event', '').strip()
        media_type = request.POST.get('media_type', '').strip()

        if not event_id or media_type not in {MediaItem.IMAGE, MediaItem.VIDEO}:
            messages.error(request, 'Événement et type de média sont obligatoires.')
        else:
            incoming_image = request.FILES.get('image')
            incoming_video_file = request.FILES.get('video_file')
            video_url = request.POST.get('video_url', '').strip()

            has_image = bool(incoming_image or media_item.image)
            has_video = bool(incoming_video_file or video_url or media_item.video_file or media_item.video_url)

            if media_type == MediaItem.IMAGE and not has_image:
                messages.error(request, 'Ajoutez une image pour un média de type image.')
            elif media_type == MediaItem.VIDEO and not has_video:
                messages.error(request, 'Ajoutez un fichier vidéo ou une URL vidéo.')
            else:
                media_item.event_id = event_id
                media_item.media_type = media_type
                media_item.caption = request.POST.get('caption', '').strip()
                media_item.is_featured = request.POST.get('is_featured') == 'on'

                if media_type == MediaItem.IMAGE:
                    if incoming_image:
                        media_item.image = incoming_image
                    media_item.video_file = None
                    media_item.video_url = None
                else:
                    media_item.image = None
                    if incoming_video_file:
                        media_item.video_file = incoming_video_file
                    media_item.video_url = video_url or None

                media_item.save()
                messages.success(request, 'Média mis à jour.')
                return redirect('superadmin:gallery_list')

    return render(request, 'superadmin/gallery/form.html', {
        'page_title': 'Modifier média',
        'active_menu': 'gallery',
        'media_item': media_item,
        'events': events,
        'media_types': MediaItem.TYPE_CHOICES,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def gallery_delete(request, pk):
    if request.method == 'POST':
        media_item = get_object_or_404(MediaItem, pk=pk)
        media_item.delete()
        messages.success(request, 'Média supprimé.')
    return redirect('superadmin:gallery_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def gallery_toggle_featured(request, pk):
    if request.method != 'POST':
        messages.error(request, 'Action invalide.')
        return redirect('superadmin:gallery_list')

    media_item = get_object_or_404(MediaItem, pk=pk)
    media_item.is_featured = not media_item.is_featured
    media_item.save(update_fields=['is_featured'])
    messages.success(request, 'Mise en avant mise à jour.')
    return redirect('superadmin:gallery_list')


# ============================================
# PAGES
# ============================================

def _legal_public_url(page_type):
    mapping = {
        "legal": "/mentions-legales/",
        "privacy": "/confidentialite/",
        "terms": "/conditions-utilisation/",
    }
    return mapping.get(page_type, "#")


def _sync_legal_page_blocks(page, request):
    section_ids = request.POST.getlist("section_id[]")
    section_titles = request.POST.getlist("section_title[]")
    section_contents = request.POST.getlist("section_content[]")
    section_orders = request.POST.getlist("section_order[]")
    section_active = set(request.POST.getlist("section_is_active[]"))

    keep_section_ids = []
    for idx, title in enumerate(section_titles):
        title = (title or "").strip()
        content = section_contents[idx] if idx < len(section_contents) else ""
        if not title and not (content or "").strip():
            continue

        raw_id = section_ids[idx] if idx < len(section_ids) else ""
        order = int(section_orders[idx]) if idx < len(section_orders) and str(section_orders[idx]).isdigit() else (idx + 1)
        is_active = str(idx) in section_active

        if raw_id:
            section = page.sections.filter(pk=raw_id).first()
            if section:
                section.title = title or f"Section {idx + 1}"
                section.content = content
                section.order = order
                section.is_active = is_active
                section.save()
                keep_section_ids.append(section.pk)
                continue

        created = LegalSection.objects.create(
            page=page,
            title=title or f"Section {idx + 1}",
            content=content,
            order=order,
            is_active=is_active,
        )
        keep_section_ids.append(created.pk)

    page.sections.exclude(pk__in=keep_section_ids).delete()

    sidebar_ids = request.POST.getlist("sidebar_id[]")
    sidebar_titles = request.POST.getlist("sidebar_title[]")
    sidebar_contents = request.POST.getlist("sidebar_content[]")
    sidebar_orders = request.POST.getlist("sidebar_order[]")
    sidebar_active = set(request.POST.getlist("sidebar_is_active[]"))

    keep_sidebar_ids = []
    for idx, title in enumerate(sidebar_titles):
        title = (title or "").strip()
        content = sidebar_contents[idx] if idx < len(sidebar_contents) else ""
        if not title and not (content or "").strip():
            continue

        raw_id = sidebar_ids[idx] if idx < len(sidebar_ids) else ""
        order = int(sidebar_orders[idx]) if idx < len(sidebar_orders) and str(sidebar_orders[idx]).isdigit() else (idx + 1)
        is_active = str(idx) in sidebar_active

        if raw_id:
            block = page.sidebar_blocks.filter(pk=raw_id).first()
            if block:
                block.title = title or f"Bloc {idx + 1}"
                block.content = content
                block.order = order
                block.is_active = is_active
                block.save()
                keep_sidebar_ids.append(block.pk)
                continue

        created = LegalSidebarBlock.objects.create(
            page=page,
            title=title or f"Bloc {idx + 1}",
            content=content,
            order=order,
            is_active=is_active,
        )
        keep_sidebar_ids.append(created.pk)

    page.sidebar_blocks.exclude(pk__in=keep_sidebar_ids).delete()


@user_passes_test(superuser_required, login_url='/accounts/login/')
def page_list(request):
    pages = LegalPage.objects.order_by('page_type')
    existing_types = set(pages.values_list('page_type', flat=True))
    missing_page_types = [pt for pt in LegalPage.PAGE_TYPES if pt[0] not in existing_types]
    return render(request, 'superadmin/pages/list.html', {
        'page_title': 'Pages légales',
        'active_menu': 'pages',
        'pages': pages,
        'missing_page_types': missing_page_types,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def page_create(request):
    initial_page_type = request.GET.get('page_type', '').strip()

    if request.method == 'POST':
        page_type = request.POST.get('page_type', '').strip()
        title = request.POST.get('title', '').strip()
        if not page_type or not title:
            messages.error(request, 'Le type et le titre sont obligatoires.')
        elif LegalPage.objects.filter(page_type=page_type).exists():
            messages.error(request, 'Une page existe deja pour ce type.')
        else:
            page = LegalPage.objects.create(
                page_type=page_type,
                title=title,
                introduction=request.POST.get('introduction', ''),
                version=request.POST.get('version', '1.0') or '1.0',
                status=request.POST.get('status', 'draft') or 'draft',
            )
            _sync_legal_page_blocks(page, request)
            messages.success(request, f"Page '{title}' creee.")
            return redirect('superadmin:page_edit', pk=page.pk)

    return render(request, 'superadmin/pages/form.html', {
        'page_title': 'Nouvelle page legale',
        'active_menu': 'pages',
        'page_types': LegalPage.PAGE_TYPES,
        'status_choices': LegalPage.STATUS_CHOICES,
        'initial_page_type': initial_page_type,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def page_detail(request, pk):
    page = get_object_or_404(LegalPage, pk=pk)
    return render(request, 'superadmin/pages/detail.html', {
        'page_title': page.title,
        'active_menu': 'pages',
        'page': page,
        'sections': page.sections.all(),
        'sidebar_blocks': page.sidebar_blocks.all(),
        'public_url': _legal_public_url(page.page_type),
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def page_edit(request, pk):
    page = get_object_or_404(LegalPage, pk=pk)
    if request.method == 'POST':
        page.title = request.POST.get('title', page.title).strip() or page.title
        page.introduction = request.POST.get('introduction', '')
        page.version = request.POST.get('version', page.version).strip() or page.version
        page.status = request.POST.get('status', page.status) or page.status
        page.save()
        _sync_legal_page_blocks(page, request)
        messages.success(request, f"Page '{page.title}' mise a jour.")
        return redirect('superadmin:page_list')
    return render(request, 'superadmin/pages/form.html', {
        'page_title': f"Modifier: {page.title}",
        'active_menu': 'pages',
        'page_obj': page,
        'sections': page.sections.all(),
        'sidebar_blocks': page.sidebar_blocks.all(),
        'page_types': LegalPage.PAGE_TYPES,
        'status_choices': LegalPage.STATUS_CHOICES,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def page_delete(request, pk):
    if request.method == 'POST':
        page = get_object_or_404(LegalPage, pk=pk)
        page.delete()
        messages.success(request, "Page supprimee.")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/pages/'})
    return redirect('superadmin:page_list')


# ============================================
# RESTORED SUPERADMIN VIEWS (PREVIOUSLY FALLBACK)
# ============================================

def _redirect_back(request, default='superadmin:dashboard'):
    return redirect(request.POST.get('next') or request.GET.get('next') or request.META.get('HTTP_REFERER') or default)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def message_list(request):
    qs = ContactMessage.objects.order_by('-created_at')

    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    subject = request.GET.get('subject', '').strip()
    priority = request.GET.get('priority', '').strip()

    if q:
        qs = qs.filter(
            Q(full_name__icontains=q)
            | Q(email__icontains=q)
            | Q(phone__icontains=q)
            | Q(message__icontains=q)
        )
    if status:
        qs = qs.filter(status=status)
    if subject:
        qs = qs.filter(subject=subject)
    if priority:
        qs = qs.filter(priority=priority)

    contact_messages = Paginator(qs, 20).get_page(request.GET.get('page', 1))

    context = {
        'page_title': 'Messages',
        'active_menu': 'messages',
        'contact_messages': contact_messages,
        'status_choices': ContactMessage.STATUS_CHOICES,
        'subject_choices': ContactMessage.SUBJECT_CHOICES,
        'priority_choices': ContactMessage.PRIORITY_CHOICES,
        'filters': {'q': q, 'status': status, 'subject': subject, 'priority': priority},
        'messages_total_count': ContactMessage.objects.count(),
        'messages_new_count': ContactMessage.objects.filter(status='new').count(),
        'messages_in_progress_count': ContactMessage.objects.filter(status='in_progress').count(),
        'messages_answered_count': ContactMessage.objects.filter(status='answered').count(),
        'messages_closed_count': ContactMessage.objects.filter(status='closed').count(),
    }
    return render(request, 'superadmin/messages/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def message_detail(request, pk):
    message_obj = get_object_or_404(ContactMessage, pk=pk)
    return render(request, 'superadmin/messages/detail.html', {
        'page_title': f"Message de {message_obj.full_name}",
        'active_menu': 'messages',
        'message': message_obj,
        'status_choices': ContactMessage.STATUS_CHOICES,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def update_message_status(request, pk):
    if request.method != 'POST':
        return redirect('superadmin:message_list')

    message_obj = get_object_or_404(ContactMessage, pk=pk)
    new_status = (request.POST.get('status') or '').strip()
    reply = request.POST.get('reply')

    if new_status in dict(ContactMessage.STATUS_CHOICES):
        message_obj.status = new_status

    if reply is not None:
        message_obj.reply = reply

    if message_obj.status == 'answered':
        message_obj.answered_at = timezone.now()

    message_obj.save()
    messages.success(request, 'Statut du message mis a jour.')

    if request.headers.get('HX-Request'):
        return HttpResponse(status=200, headers={'HX-Refresh': 'true'})
    return _redirect_back(request, default='superadmin:message_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def message_delete(request, pk):
    if request.method == 'POST':
        message_obj = get_object_or_404(ContactMessage, pk=pk)
        message_obj.delete()
        messages.success(request, 'Message supprime.')
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/messages/'})
    return redirect('superadmin:message_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def settings(request):
    institution = Institution.objects.first()

    if request.method == 'POST':
        if not institution:
            institution = Institution()

        institution.name = request.POST.get('name', institution.name or '').strip() or 'Institution'
        institution.short_name = request.POST.get('short_name', institution.short_name or '').strip()
        institution.email = request.POST.get('email', institution.email or '').strip() or 'contact@example.com'
        institution.phone = request.POST.get('phone', institution.phone or '').strip() or '+000000000'
        institution.address = request.POST.get('address', institution.address or '').strip() or '-'
        institution.city = request.POST.get('city', institution.city or '').strip() or 'Bamako'
        institution.country = request.POST.get('country', institution.country or '').strip() or 'Mali'
        institution.legal_status = request.POST.get('legal_status', institution.legal_status or '').strip()
        institution.approval_number = request.POST.get('approval_number', institution.approval_number or '').strip()
        institution.director_title = request.POST.get('director_title', institution.director_title or '').strip() or 'Direction Generale'
        institution.save()
        messages.success(request, 'Parametres institutionnels enregistres.')
        return redirect('superadmin:settings')

    return render(request, 'superadmin/settings/index.html', {
        'page_title': 'Parametres institutionnels',
        'active_menu': 'settings',
        'institution': institution,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def search_global(request):
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return HttpResponse('<div class="p-3 text-sm text-slate-500">Tapez au moins 2 caracteres...</div>')

    results = []
    for p in Programme.objects.filter(Q(title__icontains=query) | Q(description__icontains=query)).order_by('title')[:5]:
        results.append(('Formation', p.title, f'/superadmin/formations/{p.pk}/edit/'))
    for a in Article.objects.filter(Q(title__icontains=query) | Q(content__icontains=query)).order_by('-created_at')[:5]:
        results.append(('Article', a.title, f'/superadmin/articles/{a.pk}/edit/'))
    for s in Student.objects.select_related('user').filter(
        Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query) | Q(matricule__icontains=query)
    )[:5]:
        results.append(('Etudiant', s.user.get_full_name() or s.user.username, f'/superadmin/students/{s.pk}/'))

    if not results:
        return HttpResponse(f'<div class="p-3 text-sm text-slate-500">Aucun resultat pour "{query}"</div>')

    html = ['<div class="divide-y divide-slate-100">']
    for kind, title, url in results:
        html.append(
            f'<a href="{url}" class="block px-3 py-2 hover:bg-slate-50">'
            f'<span class="text-xs text-slate-500">{kind}</span><br>'
            f'<span class="text-sm text-slate-800">{title}</span></a>'
        )
    html.append('</div>')
    return HttpResponse(''.join(html))


@user_passes_test(superuser_required, login_url='/accounts/login/')
def bulk_action(request):
    if request.method != 'POST':
        return redirect('superadmin:dashboard')

    action = request.POST.get('action', '').strip()
    model_type = request.POST.get('model_type', '').strip()
    selected_ids = request.POST.getlist('selected_ids')

    if not selected_ids:
        messages.warning(request, 'Aucun element selectionne.')
        return _redirect_back(request)

    if model_type == 'message':
        qs = ContactMessage.objects.filter(pk__in=selected_ids)
        map_status = {
            'mark_new': 'new',
            'mark_in_progress': 'in_progress',
            'mark_answered': 'answered',
            'mark_closed': 'closed',
        }
        if action in map_status:
            updated = qs.update(status=map_status[action])
            messages.success(request, f'{updated} message(s) mis a jour.')
        elif action == 'delete':
            deleted = qs.count()
            qs.delete()
            messages.success(request, f'{deleted} message(s) supprime(s).')
        else:
            messages.warning(request, 'Action non supportee pour les messages.')
        return _redirect_back(request, default='superadmin:message_list')

    messages.warning(request, 'Action groupee non configuree pour ce module.')
    return _redirect_back(request)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def export_data(request, model_type):
    import csv

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{model_type}_export.csv"'
    response.write('\ufeff'.encode('utf-8'))

    writer = csv.writer(response, delimiter=';')
    if model_type == 'formations':
        writer.writerow(['ID', 'Titre', 'Cycle', 'Actif'])
        for p in Programme.objects.select_related('cycle').all():
            writer.writerow([p.pk, p.title, p.cycle.name if p.cycle else '-', 'Oui' if p.is_active else 'Non'])
    elif model_type == 'students':
        writer.writerow(['ID', 'Matricule', 'Nom', 'Email'])
        for s in Student.objects.select_related('user').all():
            writer.writerow([s.pk, s.matricule, s.user.get_full_name(), s.user.email])
    elif model_type == 'messages':
        writer.writerow(['ID', 'Nom', 'Email', 'Sujet', 'Statut', 'Date'])
        for m in ContactMessage.objects.all():
            writer.writerow([m.pk, m.full_name, m.email, m.get_subject_display(), m.get_status_display(), m.created_at.strftime('%d/%m/%Y %H:%M')])
    else:
        writer.writerow(['Info'])
        writer.writerow(['Type export non supporte'])
    return response


@user_passes_test(superuser_required, login_url='/accounts/login/')
def partner_list(request):
    partners = Partner.objects.order_by('order', 'name')
    return render(request, 'superadmin/partners/list.html', {
        'page_title': 'Partenaires',
        'active_menu': 'partners',
        'partners': partners,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def partner_create(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        logo = request.FILES.get('logo')
        if not name or not logo:
            messages.error(request, 'Le nom et le logo sont obligatoires.')
        else:
            Partner.objects.create(
                name=name,
                logo=logo,
                website=request.POST.get('website', '').strip(),
                description=request.POST.get('description', '').strip(),
                partner_type=request.POST.get('partner_type', 'autre') or 'autre',
                is_active=request.POST.get('is_active') == 'on',
                order=int(request.POST.get('order', '0') or 0),
            )
            messages.success(request, f"Partenaire '{name}' cree.")
            return redirect('superadmin:partner_list')

    return render(request, 'superadmin/partners/form.html', {
        'page_title': 'Nouveau partenaire',
        'active_menu': 'partners',
        'partner_types': Partner.PARTNER_TYPES,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def partner_edit(request, pk):
    partner = get_object_or_404(Partner, pk=pk)
    if request.method == 'POST':
        partner.name = request.POST.get('name', partner.name).strip() or partner.name
        partner.website = request.POST.get('website', '').strip()
        partner.description = request.POST.get('description', '').strip()
        partner.partner_type = request.POST.get('partner_type', partner.partner_type) or partner.partner_type
        partner.is_active = request.POST.get('is_active') == 'on'
        partner.order = int(request.POST.get('order', str(partner.order)) or partner.order)
        if request.FILES.get('logo'):
            partner.logo = request.FILES['logo']
        partner.save()
        messages.success(request, f"Partenaire '{partner.name}' mis a jour.")
        return redirect('superadmin:partner_list')

    return render(request, 'superadmin/partners/form.html', {
        'page_title': f'Modifier: {partner.name}',
        'active_menu': 'partners',
        'partner': partner,
        'partner_types': Partner.PARTNER_TYPES,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def partner_delete(request, pk):
    if request.method == 'POST':
        partner = get_object_or_404(Partner, pk=pk)
        response = _safe_delete(
            request,
            partner,
            success_message='Partenaire supprime.',
            protected_message='Suppression impossible: partenaire utilise ailleurs.',
            hx_redirect='/superadmin/partners/',
        )
        if response:
            return response
    return redirect('superadmin:partner_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_partner(request, pk):
    partner = get_object_or_404(Partner, pk=pk)
    partner.is_active = not partner.is_active
    partner.save(update_fields=['is_active'])
    messages.success(request, 'Statut partenaire mis a jour.')
    return redirect('superadmin:partner_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def testimonial_list(request):
    testimonials = Testimonial.objects.select_related('programme').order_by('-is_featured', 'order', '-pk')
    return render(request, 'superadmin/testimonials/list.html', {
        'page_title': 'Temoignages',
        'active_menu': 'testimonials',
        'testimonials': testimonials,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def testimonial_create(request):
    if request.method == 'POST':
        author_name = request.POST.get('author_name', '').strip()
        quote = request.POST.get('quote', '').strip()
        if not author_name or not quote:
            messages.error(request, 'Le nom auteur et le temoignage sont obligatoires.')
        else:
            Testimonial.objects.create(
                author_name=author_name,
                quote=quote,
                author_role=request.POST.get('author_role', '').strip(),
                is_active=request.POST.get('is_active') == 'on',
                is_featured=request.POST.get('is_featured') == 'on',
                order=int(request.POST.get('order', '0') or 0),
            )
            messages.success(request, 'Temoignage cree.')
            return redirect('superadmin:testimonial_list')

    return render(request, 'superadmin/testimonials/form.html', {
        'page_title': 'Nouveau temoignage',
        'active_menu': 'testimonials',
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def testimonial_edit(request, pk):
    testimonial = get_object_or_404(Testimonial, pk=pk)
    if request.method == 'POST':
        testimonial.author_name = request.POST.get('author_name', testimonial.author_name).strip() or testimonial.author_name
        testimonial.author_role = request.POST.get('author_role', '').strip()
        testimonial.quote = request.POST.get('quote', testimonial.quote).strip() or testimonial.quote
        testimonial.is_active = request.POST.get('is_active') == 'on'
        testimonial.is_featured = request.POST.get('is_featured') == 'on'
        testimonial.order = int(request.POST.get('order', str(testimonial.order)) or testimonial.order)
        testimonial.save()
        messages.success(request, 'Temoignage mis a jour.')
        return redirect('superadmin:testimonial_list')

    return render(request, 'superadmin/testimonials/form.html', {
        'page_title': 'Modifier temoignage',
        'active_menu': 'testimonials',
        'testimonial': testimonial,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def testimonial_delete(request, pk):
    if request.method == 'POST':
        testimonial = get_object_or_404(Testimonial, pk=pk)
        testimonial.delete()
        messages.success(request, 'Temoignage supprime.')
    return redirect('superadmin:testimonial_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_testimonial(request, pk):
    testimonial = get_object_or_404(Testimonial, pk=pk)
    testimonial.is_active = not testimonial.is_active
    testimonial.save(update_fields=['is_active'])
    messages.success(request, 'Statut temoignage mis a jour.')
    return redirect('superadmin:testimonial_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def branch_list(request):
    qs = Branch.objects.select_related('manager').order_by('name')
    search = request.GET.get('search', '').strip()
    status = request.GET.get('status', '').strip()
    city = request.GET.get('city', '').strip()

    if search:
        qs = qs.filter(
            Q(name__icontains=search)
            | Q(code__icontains=search)
            | Q(email__icontains=search)
            | Q(phone__icontains=search)
        )
    if status == 'active':
        qs = qs.filter(is_active=True)
    elif status == 'inactive':
        qs = qs.filter(is_active=False)
    if city:
        qs = qs.filter(city=city)

    branches = Paginator(qs, 20).get_page(request.GET.get('page', 1))

    context = {
        'page_title': 'Campus',
        'active_menu': 'branches',
        'branches': branches,
        'branches_total': Branch.objects.count(),
        'branches_active': Branch.objects.filter(is_active=True).count(),
        'cities': Branch.objects.order_by('city').values_list('city', flat=True).distinct(),
        'filters': {'search': search, 'status': status, 'city': city},
    }
    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/branches/_list_table.html', context)
    return render(request, 'superadmin/branches/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def branch_create(request):
    managers = User.objects.filter(is_active=True).order_by('first_name', 'last_name', 'username')
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper() or slugify(name)[:8].upper()
        slug = request.POST.get('slug', '').strip() or slugify(name)
        if not name:
            messages.error(request, 'Le nom du campus est obligatoire.')
        else:
            Branch.objects.create(
                name=name,
                code=code,
                slug=slug,
                address=request.POST.get('address', '').strip(),
                city=request.POST.get('city', 'Bamako').strip() or 'Bamako',
                phone=request.POST.get('phone', '').strip(),
                email=request.POST.get('email', '').strip(),
                manager_id=request.POST.get('manager') or None,
                is_active=request.POST.get('is_active') == 'on',
                accepts_online_registration=request.POST.get('accepts_online_registration') == 'on',
                image=request.FILES.get('image'),
            )
            messages.success(request, f"Campus '{name}' cree.")
            return redirect('superadmin:branch_list')

    return render(request, 'superadmin/branches/form.html', {
        'page_title': 'Nouveau campus',
        'active_menu': 'branches',
        'managers': managers,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def branch_edit(request, pk):
    branch = get_object_or_404(Branch, pk=pk)
    managers = User.objects.filter(is_active=True).order_by('first_name', 'last_name', 'username')
    if request.method == 'POST':
        branch.name = request.POST.get('name', branch.name).strip() or branch.name
        branch.code = request.POST.get('code', branch.code).strip().upper() or branch.code
        branch.slug = request.POST.get('slug', branch.slug).strip() or branch.slug
        branch.address = request.POST.get('address', '').strip()
        branch.city = request.POST.get('city', branch.city).strip() or branch.city
        branch.phone = request.POST.get('phone', '').strip()
        branch.email = request.POST.get('email', '').strip()
        branch.manager_id = request.POST.get('manager') or None
        branch.is_active = request.POST.get('is_active') == 'on'
        branch.accepts_online_registration = request.POST.get('accepts_online_registration') == 'on'
        if request.FILES.get('image'):
            branch.image = request.FILES['image']
        branch.save()
        messages.success(request, f"Campus '{branch.name}' mis a jour.")
        return redirect('superadmin:branch_list')

    return render(request, 'superadmin/branches/form.html', {
        'page_title': f'Modifier: {branch.name}',
        'active_menu': 'branches',
        'branch': branch,
        'managers': managers,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def branch_delete(request, pk):
    if request.method == 'POST':
        branch = get_object_or_404(Branch, pk=pk)
        response = _safe_delete(
            request,
            branch,
            success_message='Campus supprime.',
            protected_message='Suppression impossible: campus lie a des donnees.',
            hx_redirect='/superadmin/branches/',
        )
        if response:
            return response
    return redirect('superadmin:branch_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_branch(request, pk):
    branch = get_object_or_404(Branch, pk=pk)
    branch.is_active = not branch.is_active
    branch.save(update_fields=['is_active'])
    messages.success(request, 'Statut campus mis a jour.')
    return redirect('superadmin:branch_list')


def _programme_filter(qs, programme_id):
    if programme_id:
        return qs.filter(programme_id=programme_id)
    return qs


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_year_list(request):
    programme = request.GET.get('programme', '').strip()
    qs = ProgrammeYear.objects.select_related('programme').order_by('programme__title', 'year_number')
    if programme:
        qs = qs.filter(programme_id=programme)
    context = {
        'page_title': 'Annees de programme',
        'active_menu': 'formations',
        'programme_years': qs,
        'programmes': Programme.objects.order_by('title'),
        'filters': {'programme': programme},
    }
    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/programme_years/_programme_year_table.html', context)
    return render(request, 'superadmin/programme_years/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_year_create(request):
    if request.method == 'POST':
        try:
            ProgrammeYear.objects.create(
                programme_id=request.POST.get('programme') or None,
                year_number=int(request.POST.get('year_number') or 0),
            )
            messages.success(request, 'Annee de programme creee.')
            return redirect('superadmin:programme_year_list')
        except Exception as exc:
            messages.error(request, f'Creation impossible: {exc}')

    return render(request, 'superadmin/programme_years/form.html', {
        'page_title': 'Nouvelle annee',
        'active_menu': 'formations',
        'programmes': Programme.objects.order_by('title'),
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_year_edit(request, pk):
    programme_year = get_object_or_404(ProgrammeYear, pk=pk)
    if request.method == 'POST':
        try:
            programme_year.programme_id = request.POST.get('programme') or programme_year.programme_id
            programme_year.year_number = int(request.POST.get('year_number') or programme_year.year_number)
            programme_year.save()
            messages.success(request, 'Annee de programme mise a jour.')
            return redirect('superadmin:programme_year_list')
        except Exception as exc:
            messages.error(request, f'Mise a jour impossible: {exc}')

    return render(request, 'superadmin/programme_years/form.html', {
        'page_title': 'Modifier annee de programme',
        'active_menu': 'formations',
        'programme_year': programme_year,
        'programmes': Programme.objects.order_by('title'),
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_year_delete(request, pk):
    if request.method == 'POST':
        programme_year = get_object_or_404(ProgrammeYear, pk=pk)
        programme_year.delete()
        messages.success(request, 'Annee de programme supprimee.')
    return redirect('superadmin:programme_year_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def quick_fact_list(request):
    programme = request.GET.get('programme', '').strip()
    qs = ProgrammeQuickFact.objects.select_related('programme').order_by('programme__title', 'order', 'id')
    if programme:
        qs = qs.filter(programme_id=programme)
    context = {
        'page_title': 'Quick facts',
        'active_menu': 'formations',
        'quick_facts': qs,
        'programmes': Programme.objects.order_by('title'),
        'filters': {'programme': programme},
    }
    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/quick_facts/_quick_fact_table.html', context)
    return render(request, 'superadmin/quick_facts/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def quick_fact_create(request):
    if request.method == 'POST':
        try:
            ProgrammeQuickFact.objects.create(
                programme_id=request.POST.get('programme') or None,
                icon=request.POST.get('icon', 'academic_cap') or 'academic_cap',
                label=request.POST.get('label', '').strip(),
                value=request.POST.get('value', '').strip(),
                order=int(request.POST.get('order') or 0),
            )
            messages.success(request, 'Quick fact cree.')
            return redirect('superadmin:quick_fact_list')
        except Exception as exc:
            messages.error(request, f'Creation impossible: {exc}')
    return render(request, 'superadmin/quick_facts/form.html', {
        'page_title': 'Nouveau quick fact',
        'active_menu': 'formations',
        'programmes': Programme.objects.order_by('title'),
        'icon_choices': ProgrammeQuickFact.ICON_CHOICES,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def quick_fact_edit(request, pk):
    quick_fact = get_object_or_404(ProgrammeQuickFact, pk=pk)
    if request.method == 'POST':
        try:
            quick_fact.programme_id = request.POST.get('programme') or quick_fact.programme_id
            quick_fact.icon = request.POST.get('icon', quick_fact.icon) or quick_fact.icon
            quick_fact.label = request.POST.get('label', quick_fact.label).strip() or quick_fact.label
            quick_fact.value = request.POST.get('value', quick_fact.value).strip() or quick_fact.value
            quick_fact.order = int(request.POST.get('order') or quick_fact.order)
            quick_fact.save()
            messages.success(request, 'Quick fact mis a jour.')
            return redirect('superadmin:quick_fact_list')
        except Exception as exc:
            messages.error(request, f'Mise a jour impossible: {exc}')
    return render(request, 'superadmin/quick_facts/form.html', {
        'page_title': 'Modifier quick fact',
        'active_menu': 'formations',
        'quick_fact': quick_fact,
        'programmes': Programme.objects.order_by('title'),
        'icon_choices': ProgrammeQuickFact.ICON_CHOICES,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def quick_fact_delete(request, pk):
    if request.method == 'POST':
        quick_fact = get_object_or_404(ProgrammeQuickFact, pk=pk)
        quick_fact.delete()
        messages.success(request, 'Quick fact supprime.')
    return redirect('superadmin:quick_fact_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_tab_list(request):
    programme = request.GET.get('programme', '').strip()
    qs = ProgrammeTab.objects.select_related('programme').order_by('programme__title', 'order', 'id')
    if programme:
        qs = qs.filter(programme_id=programme)
    context = {
        'page_title': 'Onglets programme',
        'active_menu': 'formations',
        'tabs': qs,
        'programmes': Programme.objects.order_by('title'),
        'filters': {'programme': programme},
    }
    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/programme_tabs/_tab_table.html', context)
    return render(request, 'superadmin/programme_tabs/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_tab_create(request):
    if request.method == 'POST':
        try:
            ProgrammeTab.objects.create(
                programme_id=request.POST.get('programme') or None,
                tab_type=request.POST.get('tab_type', 'custom') or 'custom',
                title=request.POST.get('title', '').strip(),
                slug=request.POST.get('slug', '').strip(),
                order=int(request.POST.get('order') or 0),
                is_active=request.POST.get('is_active') == 'on',
            )
            messages.success(request, 'Onglet cree.')
            return redirect('superadmin:programme_tab_list')
        except Exception as exc:
            messages.error(request, f'Creation impossible: {exc}')
    return render(request, 'superadmin/programme_tabs/form.html', {
        'page_title': 'Nouvel onglet',
        'active_menu': 'formations',
        'programmes': Programme.objects.order_by('title'),
        'tab_type_choices': ProgrammeTab.TAB_TYPE_CHOICES,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_tab_edit(request, pk):
    tab = get_object_or_404(ProgrammeTab, pk=pk)
    if request.method == 'POST':
        try:
            tab.programme_id = request.POST.get('programme') or tab.programme_id
            tab.tab_type = request.POST.get('tab_type', tab.tab_type) or tab.tab_type
            tab.title = request.POST.get('title', tab.title).strip() or tab.title
            tab.slug = request.POST.get('slug', tab.slug).strip() or tab.slug
            tab.order = int(request.POST.get('order') or tab.order)
            tab.is_active = request.POST.get('is_active') == 'on'
            tab.save()
            messages.success(request, 'Onglet mis a jour.')
            return redirect('superadmin:programme_tab_list')
        except Exception as exc:
            messages.error(request, f'Mise a jour impossible: {exc}')
    return render(request, 'superadmin/programme_tabs/form.html', {
        'page_title': 'Modifier onglet',
        'active_menu': 'formations',
        'tab': tab,
        'programmes': Programme.objects.order_by('title'),
        'tab_type_choices': ProgrammeTab.TAB_TYPE_CHOICES,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_tab_delete(request, pk):
    if request.method == 'POST':
        tab = get_object_or_404(ProgrammeTab, pk=pk)
        tab.delete()
        messages.success(request, 'Onglet supprime.')
    return redirect('superadmin:programme_tab_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_section_list(request):
    programme = request.GET.get('programme', '').strip()
    qs = ProgrammeSection.objects.select_related('tab', 'tab__programme').order_by('tab__programme__title', 'tab__order', 'order', 'id')
    if programme:
        qs = qs.filter(tab__programme_id=programme)
    context = {
        'page_title': 'Sections programme',
        'active_menu': 'formations',
        'sections': qs,
        'programmes': Programme.objects.order_by('title'),
        'filters': {'programme': programme},
    }
    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/programme_sections/_section_table.html', context)
    return render(request, 'superadmin/programme_sections/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_section_create(request):
    tabs = ProgrammeTab.objects.select_related('programme').order_by('programme__title', 'order')
    if request.method == 'POST':
        try:
            ProgrammeSection.objects.create(
                tab_id=request.POST.get('tab') or None,
                section_type=request.POST.get('section_type', 'text') or 'text',
                title=request.POST.get('title', '').strip(),
                content=request.POST.get('content', ''),
                order=int(request.POST.get('order') or 0),
            )
            messages.success(request, 'Section creee.')
            return redirect('superadmin:programme_section_list')
        except Exception as exc:
            messages.error(request, f'Creation impossible: {exc}')
    return render(request, 'superadmin/programme_sections/form.html', {
        'page_title': 'Nouvelle section',
        'active_menu': 'formations',
        'tabs': tabs,
        'section_type_choices': ProgrammeSection.SECTION_TYPE_CHOICES,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_section_edit(request, pk):
    section = get_object_or_404(ProgrammeSection, pk=pk)
    tabs = ProgrammeTab.objects.select_related('programme').order_by('programme__title', 'order')
    if request.method == 'POST':
        try:
            section.tab_id = request.POST.get('tab') or section.tab_id
            section.section_type = request.POST.get('section_type', section.section_type) or section.section_type
            section.title = request.POST.get('title', '').strip()
            section.content = request.POST.get('content', '')
            section.order = int(request.POST.get('order') or section.order)
            section.save()
            messages.success(request, 'Section mise a jour.')
            return redirect('superadmin:programme_section_list')
        except Exception as exc:
            messages.error(request, f'Mise a jour impossible: {exc}')
    return render(request, 'superadmin/programme_sections/form.html', {
        'page_title': 'Modifier section',
        'active_menu': 'formations',
        'section': section,
        'tabs': tabs,
        'section_type_choices': ProgrammeSection.SECTION_TYPE_CHOICES,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_section_delete(request, pk):
    if request.method == 'POST':
        section = get_object_or_404(ProgrammeSection, pk=pk)
        section.delete()
        messages.success(request, 'Section supprimee.')
    return redirect('superadmin:programme_section_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def competence_block_list(request):
    programme = request.GET.get('programme', '').strip()
    qs = CompetenceBlock.objects.select_related('programme').order_by('programme__title', 'order', 'id')
    if programme:
        qs = qs.filter(programme_id=programme)
    context = {
        'page_title': 'Blocs de competences',
        'active_menu': 'formations',
        'blocks': qs,
        'programmes': Programme.objects.order_by('title'),
        'filters': {'programme': programme},
    }
    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/competence_blocks/_block_table.html', context)
    return render(request, 'superadmin/competence_blocks/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def competence_block_create(request):
    if request.method == 'POST':
        try:
            CompetenceBlock.objects.create(
                programme_id=request.POST.get('programme') or None,
                title=request.POST.get('title', '').strip(),
                description=request.POST.get('description', '').strip(),
                order=int(request.POST.get('order') or 0),
            )
            messages.success(request, 'Bloc de competences cree.')
            return redirect('superadmin:competence_block_list')
        except Exception as exc:
            messages.error(request, f'Creation impossible: {exc}')
    return render(request, 'superadmin/competence_blocks/form.html', {
        'page_title': 'Nouveau bloc',
        'active_menu': 'formations',
        'programmes': Programme.objects.order_by('title'),
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def competence_block_edit(request, pk):
    block = get_object_or_404(CompetenceBlock, pk=pk)
    if request.method == 'POST':
        try:
            block.programme_id = request.POST.get('programme') or block.programme_id
            block.title = request.POST.get('title', block.title).strip() or block.title
            block.description = request.POST.get('description', '').strip()
            block.order = int(request.POST.get('order') or block.order)
            block.save()
            messages.success(request, 'Bloc mis a jour.')
            return redirect('superadmin:competence_block_list')
        except Exception as exc:
            messages.error(request, f'Mise a jour impossible: {exc}')
    return render(request, 'superadmin/competence_blocks/form.html', {
        'page_title': 'Modifier bloc',
        'active_menu': 'formations',
        'block': block,
        'programmes': Programme.objects.order_by('title'),
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def competence_block_delete(request, pk):
    if request.method == 'POST':
        block = get_object_or_404(CompetenceBlock, pk=pk)
        block.delete()
        messages.success(request, 'Bloc supprime.')
    return redirect('superadmin:competence_block_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def competence_item_list(request):
    programme = request.GET.get('programme', '').strip()
    qs = CompetenceItem.objects.select_related('block', 'block__programme').order_by('block__programme__title', 'block__order', 'order', 'id')
    if programme:
        qs = qs.filter(block__programme_id=programme)
    context = {
        'page_title': 'Items de competences',
        'active_menu': 'formations',
        'items': qs,
        'programmes': Programme.objects.order_by('title'),
        'filters': {'programme': programme},
    }
    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/competence_items/_item_table.html', context)
    return render(request, 'superadmin/competence_items/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def competence_item_create(request):
    blocks = CompetenceBlock.objects.select_related('programme').order_by('programme__title', 'order')
    if request.method == 'POST':
        try:
            CompetenceItem.objects.create(
                block_id=request.POST.get('block') or None,
                title=request.POST.get('title', '').strip(),
                description=request.POST.get('description', '').strip(),
                order=int(request.POST.get('order') or 0),
            )
            messages.success(request, 'Item de competences cree.')
            return redirect('superadmin:competence_item_list')
        except Exception as exc:
            messages.error(request, f'Creation impossible: {exc}')
    return render(request, 'superadmin/competence_items/form.html', {
        'page_title': 'Nouvel item',
        'active_menu': 'formations',
        'blocks': blocks,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def competence_item_edit(request, pk):
    item = get_object_or_404(CompetenceItem, pk=pk)
    blocks = CompetenceBlock.objects.select_related('programme').order_by('programme__title', 'order')
    if request.method == 'POST':
        try:
            item.block_id = request.POST.get('block') or item.block_id
            item.title = request.POST.get('title', item.title).strip() or item.title
            item.description = request.POST.get('description', '').strip()
            item.order = int(request.POST.get('order') or item.order)
            item.save()
            messages.success(request, 'Item mis a jour.')
            return redirect('superadmin:competence_item_list')
        except Exception as exc:
            messages.error(request, f'Mise a jour impossible: {exc}')
    return render(request, 'superadmin/competence_items/form.html', {
        'page_title': 'Modifier item',
        'active_menu': 'formations',
        'item': item,
        'blocks': blocks,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def competence_item_delete(request, pk):
    if request.method == 'POST':
        item = get_object_or_404(CompetenceItem, pk=pk)
        item.delete()
        messages.success(request, 'Item supprime.')
    return redirect('superadmin:competence_item_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def required_document_list(request):
    documents = RequiredDocument.objects.order_by('name')
    return render(request, 'superadmin/required_documents/list.html', {
        'page_title': 'Documents requis',
        'active_menu': 'formations',
        'documents': documents,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def required_document_create(request):
    if request.method == 'POST':
        try:
            RequiredDocument.objects.create(
                name=request.POST.get('name', '').strip(),
                description=request.POST.get('description', '').strip(),
                is_mandatory=request.POST.get('is_mandatory') == 'on',
            )
            messages.success(request, 'Document requis cree.')
            return redirect('superadmin:required_document_list')
        except Exception as exc:
            messages.error(request, f'Creation impossible: {exc}')
    return render(request, 'superadmin/required_documents/form.html', {
        'page_title': 'Nouveau document requis',
        'active_menu': 'formations',
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def required_document_edit(request, pk):
    document = get_object_or_404(RequiredDocument, pk=pk)
    if request.method == 'POST':
        try:
            document.name = request.POST.get('name', document.name).strip() or document.name
            document.description = request.POST.get('description', '').strip()
            document.is_mandatory = request.POST.get('is_mandatory') == 'on'
            document.save()
            messages.success(request, 'Document requis mis a jour.')
            return redirect('superadmin:required_document_list')
        except Exception as exc:
            messages.error(request, f'Mise a jour impossible: {exc}')
    return render(request, 'superadmin/required_documents/form.html', {
        'page_title': 'Modifier document requis',
        'active_menu': 'formations',
        'document': document,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def required_document_delete(request, pk):
    if request.method == 'POST':
        document = get_object_or_404(RequiredDocument, pk=pk)
        document.delete()
        messages.success(request, 'Document requis supprime.')
    return redirect('superadmin:required_document_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_required_document_list(request):
    programme = request.GET.get('programme', '').strip()
    qs = ProgrammeRequiredDocument.objects.select_related('programme', 'document').order_by('programme__title', 'document__name')
    if programme:
        qs = qs.filter(programme_id=programme)
    context = {
        'page_title': 'Documents par programme',
        'active_menu': 'formations',
        'programme_documents': qs,
        'programmes': Programme.objects.order_by('title'),
        'filters': {'programme': programme},
    }
    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/programme_required_documents/_programme_document_table.html', context)
    return render(request, 'superadmin/programme_required_documents/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_required_document_create(request):
    if request.method == 'POST':
        try:
            ProgrammeRequiredDocument.objects.create(
                programme_id=request.POST.get('programme') or None,
                document_id=request.POST.get('document') or None,
            )
            messages.success(request, 'Association creee.')
            return redirect('superadmin:programme_required_document_list')
        except Exception as exc:
            messages.error(request, f'Creation impossible: {exc}')
    return render(request, 'superadmin/programme_required_documents/form.html', {
        'page_title': 'Nouvelle association',
        'active_menu': 'formations',
        'programmes': Programme.objects.order_by('title'),
        'documents': RequiredDocument.objects.order_by('name'),
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_required_document_delete(request, pk):
    if request.method == 'POST':
        obj = get_object_or_404(ProgrammeRequiredDocument, pk=pk)
        obj.delete()
        messages.success(request, 'Association supprimee.')
    return redirect('superadmin:programme_required_document_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def community_category_list(request):
    categories = CommunityCategory.objects.annotate(
        topics_count=Count('topics', distinct=True),
        subscribers_count=Count('subscribers', distinct=True),
    ).order_by('order', 'name')
    return render(request, 'superadmin/community/categories/list.html', {
        'page_title': 'Categories Communaute',
        'active_menu': 'community',
        'categories': categories,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def community_category_create(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'Le nom est obligatoire.')
        else:
            CommunityCategory.objects.create(
                name=name,
                description=request.POST.get('description', '').strip(),
                is_active=request.POST.get('is_active') == 'on',
            )
            messages.success(request, 'Categorie creee.')
            return redirect('superadmin:community_category_list')
    return render(request, 'superadmin/community/categories/form.html', {
        'page_title': 'Nouvelle categorie communaute',
        'active_menu': 'community',
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def community_category_edit(request, pk):
    category = get_object_or_404(CommunityCategory, pk=pk)
    if request.method == 'POST':
        category.name = request.POST.get('name', category.name).strip() or category.name
        category.description = request.POST.get('description', '').strip()
        category.is_active = request.POST.get('is_active') == 'on'
        category.save()
        messages.success(request, 'Categorie mise a jour.')
        return redirect('superadmin:community_category_list')
    return render(request, 'superadmin/community/categories/form.html', {
        'page_title': 'Modifier categorie communaute',
        'active_menu': 'community',
        'category': category,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def community_category_delete(request, pk):
    if request.method == 'POST':
        category = get_object_or_404(CommunityCategory, pk=pk)
        response = _safe_delete(
            request,
            category,
            success_message='Categorie supprimee.',
            protected_message='Suppression impossible: categorie encore utilisee.',
            hx_redirect='/superadmin/community/categories/',
        )
        if response:
            return response
    return redirect('superadmin:community_category_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_community_category(request, pk):
    category = get_object_or_404(CommunityCategory, pk=pk)
    category.is_active = not category.is_active
    category.save(update_fields=['is_active'])
    messages.success(request, 'Statut categorie mis a jour.')
    return redirect('superadmin:community_category_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def community_topic_list(request):
    search = request.GET.get('search', '').strip()
    category = request.GET.get('category', '').strip()
    status = request.GET.get('status', '').strip()

    qs = Topic.objects.select_related('author', 'category', 'accepted_answer').order_by('-last_activity_at')
    if search:
        qs = qs.filter(Q(title__icontains=search) | Q(content__icontains=search))
    if category:
        qs = qs.filter(category_id=category)
    if status == 'published':
        qs = qs.filter(is_published=True, is_deleted=False)
    elif status == 'deleted':
        qs = qs.filter(is_deleted=True)

    topics = Paginator(qs, 20).get_page(request.GET.get('page', 1))
    context = {
        'page_title': 'Sujets Communaute',
        'active_menu': 'community',
        'topics': topics,
        'categories': CommunityCategory.objects.order_by('name'),
        'filters': {'search': search, 'category': category, 'status': status},
    }
    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/community/topics/_topic_table.html', context)
    return render(request, 'superadmin/community/topics/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def community_topic_detail(request, pk):
    topic = get_object_or_404(Topic.objects.select_related('author', 'category', 'accepted_answer'), pk=pk)
    answers = topic.answers.select_related('author').order_by('-upvotes', 'created_at')[:8]
    return render(request, 'superadmin/community/topics/detail.html', {
        'page_title': topic.title,
        'active_menu': 'community',
        'topic': topic,
        'answers': answers,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def community_topic_edit(request, pk):
    topic = get_object_or_404(Topic, pk=pk)
    if request.method == 'POST':
        topic.title = request.POST.get('title', topic.title).strip() or topic.title
        topic.category_id = request.POST.get('category') or topic.category_id
        topic.is_published = request.POST.get('is_published') == 'on'
        topic.is_locked = request.POST.get('is_locked') == 'on'
        topic.is_pinned = request.POST.get('is_pinned') == 'on'
        topic.save()
        messages.success(request, 'Sujet mis a jour.')
        return redirect('superadmin:community_topic_detail', pk=topic.pk)
    return render(request, 'superadmin/community/topics/form.html', {
        'page_title': 'Modifier sujet',
        'active_menu': 'community',
        'topic': topic,
        'categories': CommunityCategory.objects.order_by('name'),
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def community_topic_delete(request, pk):
    if request.method == 'POST':
        topic = get_object_or_404(Topic, pk=pk)
        topic.is_deleted = True
        topic.is_published = False
        topic.save(update_fields=['is_deleted', 'is_published'])
        messages.success(request, 'Sujet masque (suppression logique).')
    return redirect('superadmin:community_topic_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_community_topic(request, pk):
    topic = get_object_or_404(Topic, pk=pk)
    action = request.GET.get('action', '').strip()
    if action == 'publish':
        topic.is_published = not topic.is_published
        if topic.is_published:
            topic.is_deleted = False
        topic.save(update_fields=['is_published', 'is_deleted'])
        messages.success(request, 'Etat de publication mis a jour.')
    elif action == 'lock':
        topic.is_locked = not topic.is_locked
        topic.save(update_fields=['is_locked'])
        messages.success(request, 'Verrouillage du sujet mis a jour.')
    else:
        topic.is_pinned = not topic.is_pinned
        topic.save(update_fields=['is_pinned'])
        messages.success(request, 'Epinglage du sujet mis a jour.')
    return _redirect_back(request, default='superadmin:community_topic_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def community_answer_list(request):
    search = request.GET.get('search', '').strip()
    topic_id = request.GET.get('topic', '').strip()

    qs = Answer.objects.select_related('author', 'topic', 'topic__accepted_answer').order_by('-created_at')
    if search:
        qs = qs.filter(content__icontains=search)
    if topic_id:
        qs = qs.filter(topic_id=topic_id)

    answers = Paginator(qs, 20).get_page(request.GET.get('page', 1))
    context = {
        'page_title': 'Reponses Communaute',
        'active_menu': 'community',
        'answers': answers,
        'topics': Topic.objects.order_by('-last_activity_at')[:200],
        'filters': {'search': search, 'topic': topic_id},
    }
    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/community/answers/_answer_table.html', context)
    return render(request, 'superadmin/community/answers/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def community_answer_detail(request, pk):
    answer = get_object_or_404(Answer.objects.select_related('author', 'topic', 'topic__category'), pk=pk)
    return render(request, 'superadmin/community/answers/detail.html', {
        'page_title': f'Reponse #{answer.pk}',
        'active_menu': 'community',
        'answer': answer,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def community_answer_edit(request, pk):
    answer = get_object_or_404(Answer, pk=pk)
    if request.method == 'POST':
        answer.content = request.POST.get('content', answer.content)
        answer.save(update_fields=['content'])
        messages.success(request, 'Reponse mise a jour.')
        return redirect('superadmin:community_answer_detail', pk=answer.pk)
    return render(request, 'superadmin/community/answers/form.html', {
        'page_title': 'Modifier reponse',
        'active_menu': 'community',
        'answer': answer,
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def community_answer_delete(request, pk):
    if request.method == 'POST':
        answer = get_object_or_404(Answer, pk=pk)
        answer.is_deleted = True
        answer.save(update_fields=['is_deleted'])
        messages.success(request, 'Reponse masquee.')
    return _redirect_back(request, default='superadmin:community_answer_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_community_answer(request, pk):
    answer = get_object_or_404(Answer.objects.select_related('topic'), pk=pk)
    action = request.GET.get('action', '').strip()
    if action == 'accept':
        topic = answer.topic
        topic.accepted_answer = answer if topic.accepted_answer_id != answer.pk else None
        topic.save(update_fields=['accepted_answer'])
        messages.success(request, 'Reponse acceptee mise a jour.')
    else:
        answer.is_deleted = not answer.is_deleted
        answer.save(update_fields=['is_deleted'])
        messages.success(request, 'Statut de reponse mis a jour.')
    return _redirect_back(request, default='superadmin:community_answer_list')


