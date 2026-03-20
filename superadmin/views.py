# superadmin/views.py

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import user_passes_test
from django.http import HttpResponse
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum
from django.utils import timezone
from django.utils.text import slugify

# Imports des modèles
from formations.models import Programme, Cycle, Filiere, Diploma, Fee
from admissions.models import Candidature, CandidatureDocument
from blog.models import Article, Category as BlogCategory, Comment
from news.models import News, Event, Category as NewsCategory
from core.models import (
    Institution, LegalPage, LegalSection, Partner,
    ContactMessage,
)
from inscriptions.models import Inscription
from payments.models import Payment
from students.models import Student
from branches.models import Branch


# ============================================
# DECORATOR - Superuser Required
# ============================================

def superuser_required(user):
    return user.is_authenticated and user.is_superuser


# ============================================
# DASHBOARD
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def dashboard(request):
    """Dashboard principal avec statistiques"""

    # Stats de base
    context = {
        'page_title': 'Tableau de bord',
        'formations_count': Programme.objects.count(),
        'formations_published': Programme.objects.filter(is_active=True).count(),
    }

    # Candidatures (avec gestion d'erreur)
    try:
        context['candidatures_count'] = Candidature.objects.count()
        context['candidatures_pending'] = Candidature.objects.filter(status='submitted').count()
        context['recent_candidatures'] = Candidature.objects.order_by('-submitted_at')[:5]
    except Exception:
        context['candidatures_count'] = 0
        context['candidatures_pending'] = 0
        context['recent_candidatures'] = []

    # Inscriptions
    try:
        context['inscriptions_count'] = Inscription.objects.count()
        context['inscriptions_active'] = Inscription.objects.filter(status='active').count()
    except Exception:
        context['inscriptions_count'] = 0
        context['inscriptions_active'] = 0

    # Étudiants
    try:
        context['students_count'] = Student.objects.count()
    except Exception:
        context['students_count'] = 0

    # Paiements
    try:
        context['payments_total'] = Payment.objects.filter(status='completed').aggregate(
            total=Sum('amount')
        )['total'] or 0
    except Exception:
        context['payments_total'] = 0

    # Messages
    try:
        context['messages_unread'] = ContactMessage.objects.filter(status='pending').count()
    except Exception:
        context['messages_unread'] = 0

    # Articles
    try:
        from blog.models import Article
        context['articles_count'] = Article.objects.count()
    except Exception:
        context['articles_count'] = 0

    return render(request, 'superadmin/dashboard.html', context)

# ============================================
# FORMATIONS - CRUD COMPLET
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def formation_list(request):
    """Liste des formations avec filtres et pagination"""
    formations = Programme.objects.all().order_by('-created_at')

    # Filtres
    search = request.GET.get('search', '')
    status = request.GET.get('status', '')
    cycle = request.GET.get('cycle', '')

    if search:
        formations = formations.filter(
            Q(title__icontains=search) |
            Q(description__icontains=search)
        )

    if status:
        if status == 'active':
            formations = formations.filter(is_active=True)
        elif status == 'inactive':
            formations = formations.filter(is_active=False)

    if cycle:
        formations = formations.filter(cycle_id=cycle)

    # Pagination
    paginator = Paginator(formations, 20)
    page = request.GET.get('page', 1)
    formations = paginator.get_page(page)

    context = {
        'page_title': 'Formations',
        'formations': formations,
        'cycles': Cycle.objects.all(),
        'filters': {'search': search, 'status': status, 'cycle': cycle},
    }

    # Support HTMX partial rendering
    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/formations/_list_table.html', context)

    return render(request, 'superadmin/formations/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def formation_create(request):
    """Créer une nouvelle formation"""
    if request.method == 'POST':
        # Récupération des données du formulaire
        title = request.POST.get('title')
        description = request.POST.get('description', '')
        cycle_id = request.POST.get('cycle')
        filiere_id = request.POST.get('filiere')
        duration = request.POST.get('duration', '')
        is_active = request.POST.get('is_active') == 'on'

        # Validation
        if not title:
            messages.error(request, "Le titre est obligatoire.")
            return redirect('superadmin:formation_create')

        # Création
        formation = Programme.objects.create(
            title=title,
            description=description,
            cycle_id=cycle_id if cycle_id else None,
            filiere_id=filiere_id if filiere_id else None,
            duration=duration,
            is_active=is_active,
        )

        messages.success(request, f"Formation '{title}' créée avec succès!")
        return redirect('superadmin:formation_list')

    context = {
        'page_title': 'Nouvelle Formation',
        'cycles': Cycle.objects.all(),
        'filieres': Filiere.objects.all(),
    }
    return render(request, 'superadmin/formations/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def formation_edit(request, pk):
    """Modifier une formation existante"""
    formation = get_object_or_404(Programme, pk=pk)

    if request.method == 'POST':
        formation.title = request.POST.get('title', formation.title)
        formation.description = request.POST.get('description', '')
        formation.cycle_id = request.POST.get('cycle') or None
        formation.filiere_id = request.POST.get('filiere') or None
        formation.duration = request.POST.get('duration', '')
        formation.is_active = request.POST.get('is_active') == 'on'
        formation.save()

        messages.success(request, f"Formation '{formation.title}' mise à jour!")
        return redirect('superadmin:formation_list')

    context = {
        'page_title': f'Modifier: {formation.title}',
        'formation': formation,
        'cycles': Cycle.objects.all(),
        'filieres': Filiere.objects.all(),
    }
    return render(request, 'superadmin/formations/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_formation(request, pk):
    """Toggle actif/inactif (HTMX)"""
    formation = get_object_or_404(Programme, pk=pk)
    formation.is_active = not formation.is_active
    formation.save()

    status = "activée" if formation.is_active else "désactivée"

    if request.headers.get('HX-Request'):
        return HttpResponse(
            f'''<span class="badge badge-{'success' if formation.is_active else 'secondary'}">
                {'Actif' if formation.is_active else 'Inactif'}
            </span>''',
            headers={'HX-Trigger': f'{{"showToast": "Formation {status}"}}'}
        )

    messages.success(request, f"Formation {status}!")
    return redirect('superadmin:formation_list')


# ============================================
# CYCLES - CRUD
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def cycle_list(request):
    cycles = Cycle.objects.annotate(
        formations_count=Count('programmes')
    ).order_by('order', 'name')

    context = {
        'page_title': 'Cycles',
        'cycles': cycles,
    }
    return render(request, 'superadmin/cycles/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def cycle_create(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        order = request.POST.get('order', 0)

        if name:
            Cycle.objects.create(name=name, description=description, order=order)
            messages.success(request, f"Cycle '{name}' créé!")
            return redirect('superadmin:cycle_list')

        messages.error(request, "Le nom est obligatoire.")

    context = {'page_title': 'Nouveau Cycle'}
    return render(request, 'superadmin/cycles/form.html', context)


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

    context = {
        'page_title': f'Modifier: {cycle.name}',
        'cycle': cycle,
    }
    return render(request, 'superadmin/cycles/form.html', context)


# ============================================
# FILIERES - CRUD
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def filiere_list(request):
    filieres = Filiere.objects.annotate(
        formations_count=Count('programmes')
    ).order_by('name')

    context = {
        'page_title': 'Filières',
        'filieres': filieres,
    }
    return render(request, 'superadmin/filieres/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def filiere_create(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')

        if name:
            Filiere.objects.create(name=name, description=description)
            messages.success(request, f"Filière '{name}' créée!")
            return redirect('superadmin:filiere_list')

    context = {'page_title': 'Nouvelle Filière'}
    return render(request, 'superadmin/filieres/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def filiere_edit(request, pk):
    filiere = get_object_or_404(Filiere, pk=pk)

    if request.method == 'POST':
        filiere.name = request.POST.get('name', filiere.name)
        filiere.description = request.POST.get('description', '')
        filiere.save()
        messages.success(request, f"Filière '{filiere.name}' mise à jour!")
        return redirect('superadmin:filiere_list')

    context = {
        'page_title': f'Modifier: {filiere.name}',
        'filiere': filiere,
    }
    return render(request, 'superadmin/filieres/form.html', context)


# ============================================
# DIPLOMAS - CRUD
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def diploma_list(request):
    diplomas = Diploma.objects.all().order_by('name')
    context = {
        'page_title': 'Diplômes',
        'diplomas': diplomas,
    }
    return render(request, 'superadmin/diplomas/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def diploma_create(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        abbreviation = request.POST.get('abbreviation', '')

        if name:
            Diploma.objects.create(name=name, abbreviation=abbreviation)
            messages.success(request, f"Diplôme '{name}' créé!")
            return redirect('superadmin:diploma_list')

    context = {'page_title': 'Nouveau Diplôme'}
    return render(request, 'superadmin/diplomas/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def diploma_edit(request, pk):
    diploma = get_object_or_404(Diploma, pk=pk)

    if request.method == 'POST':
        diploma.name = request.POST.get('name', diploma.name)
        diploma.abbreviation = request.POST.get('abbreviation', '')
        diploma.save()
        messages.success(request, f"Diplôme '{diploma.name}' mis à jour!")
        return redirect('superadmin:diploma_list')

    context = {
        'page_title': f'Modifier: {diploma.name}',
        'diploma': diploma,
    }
    return render(request, 'superadmin/diplomas/form.html', context)


# ============================================
# CANDIDATURES
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def candidature_list(request):
    candidatures = Candidature.objects.select_related(
        'user', 'programme'
    ).order_by('-created_at')

    # Filtres
    status = request.GET.get('status', '')
    if status:
        candidatures = candidatures.filter(status=status)

    paginator = Paginator(candidatures, 20)
    page = request.GET.get('page', 1)
    candidatures = paginator.get_page(page)

    context = {
        'page_title': 'Candidatures',
        'candidatures': candidatures,
        'status_choices': Candidature.STATUS_CHOICES if hasattr(Candidature, 'STATUS_CHOICES') else [],
    }
    return render(request, 'superadmin/candidatures/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def candidature_detail(request, pk):
    candidature = get_object_or_404(
        Candidature.objects.select_related('user', 'programme'),
        pk=pk
    )
    documents = CandidatureDocument.objects.filter(candidature=candidature)

    context = {
        'page_title': f'Candidature #{pk}',
        'candidature': candidature,
        'documents': documents,
    }
    return render(request, 'superadmin/candidatures/detail.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def candidature_status(request, pk):
    """Changer le statut d'une candidature"""
    candidature = get_object_or_404(Candidature, pk=pk)

    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status:
            candidature.status = new_status
            candidature.save()
            messages.success(request, f"Statut mis à jour: {new_status}")

    return redirect('superadmin:candidature_detail', pk=pk)


# ============================================
# INSCRIPTIONS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def inscription_list(request):
    inscriptions = Inscription.objects.select_related(
        'student', 'programme'
    ).order_by('-created_at')

    status = request.GET.get('status', '')
    if status:
        inscriptions = inscriptions.filter(status=status)

    paginator = Paginator(inscriptions, 20)
    page = request.GET.get('page', 1)
    inscriptions = paginator.get_page(page)

    context = {
        'page_title': 'Inscriptions',
        'inscriptions': inscriptions,
    }
    return render(request, 'superadmin/inscriptions/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def inscription_detail(request, pk):
    inscription = get_object_or_404(Inscription, pk=pk)
    context = {
        'page_title': f'Inscription #{pk}',
        'inscription': inscription,
    }
    return render(request, 'superadmin/inscriptions/detail.html', context)


# ============================================
# STUDENTS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def student_list(request):
    students = Student.objects.select_related('user').order_by('-created_at')

    search = request.GET.get('search', '')
    if search:
        students = students.filter(
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search) |
            Q(user__email__icontains=search) |
            Q(matricule__icontains=search)
        )

    paginator = Paginator(students, 20)
    page = request.GET.get('page', 1)
    students = paginator.get_page(page)

    context = {
        'page_title': 'Étudiants',
        'students': students,
    }
    return render(request, 'superadmin/students/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def student_detail(request, pk):
    student = get_object_or_404(Student.objects.select_related('user'), pk=pk)
    inscriptions = Inscription.objects.filter(student=student)
    payments = Payment.objects.filter(student=student)

    context = {
        'page_title': f'Étudiant: {student.user.get_full_name()}',
        'student': student,
        'inscriptions': inscriptions,
        'payments': payments,
    }
    return render(request, 'superadmin/students/detail.html', context)


# ============================================
# PAYMENTS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def payment_list(request):
    payments = Payment.objects.select_related('student', 'inscription').order_by('-created_at')

    status = request.GET.get('status', '')
    if status:
        payments = payments.filter(status=status)

    paginator = Paginator(payments, 20)
    page = request.GET.get('page', 1)
    payments = paginator.get_page(page)

    # Statistiques
    total_amount = Payment.objects.filter(status='completed').aggregate(
        total=Sum('amount')
    )['total'] or 0

    context = {
        'page_title': 'Paiements',
        'payments': payments,
        'total_amount': total_amount,
    }
    return render(request, 'superadmin/payments/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def payment_detail(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    context = {
        'page_title': f'Paiement #{pk}',
        'payment': payment,
    }
    return render(request, 'superadmin/payments/detail.html', context)


# ============================================
# FEES (Frais de scolarité)
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def fee_list(request):
    fees = Fee.objects.select_related('programme').order_by('-id')
    context = {
        'page_title': 'Frais de scolarité',
        'fees': fees,
    }
    return render(request, 'superadmin/fees/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def fee_create(request):
    if request.method == 'POST':
        programme_id = request.POST.get('programme')
        amount = request.POST.get('amount')
        academic_year = request.POST.get('academic_year')

        if programme_id and amount:
            Fee.objects.create(
                programme_id=programme_id,
                amount=amount,
                academic_year=academic_year,
            )
            messages.success(request, "Frais créés avec succès!")
            return redirect('superadmin:fee_list')

    context = {
        'page_title': 'Nouveaux Frais',
        'programmes': Programme.objects.all(),
    }
    return render(request, 'superadmin/fees/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def fee_edit(request, pk):
    fee = get_object_or_404(Fee, pk=pk)

    if request.method == 'POST':
        fee.programme_id = request.POST.get('programme', fee.programme_id)
        fee.amount = request.POST.get('amount', fee.amount)
        fee.academic_year = request.POST.get('academic_year', fee.academic_year)
        fee.save()
        messages.success(request, "Frais mis à jour!")
        return redirect('superadmin:fee_list')

    context = {
        'page_title': 'Modifier Frais',
        'fee': fee,
        'programmes': Programme.objects.all(),
    }
    return render(request, 'superadmin/fees/form.html', context)


# ============================================
# ARTICLES (Blog)
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def article_list(request):
    articles = Article.objects.select_related('author', 'category').order_by('-created_at')

    status = request.GET.get('status', '')
    if status:
        articles = articles.filter(status=status)

    paginator = Paginator(articles, 20)
    page = request.GET.get('page', 1)
    articles = paginator.get_page(page)

    context = {
        'page_title': 'Articles Blog',
        'articles': articles,
    }
    return render(request, 'superadmin/articles/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def article_create(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        content = request.POST.get('content', '')
        category_id = request.POST.get('category')
        status = request.POST.get('status', 'draft')

        if title:
            article = Article.objects.create(
                title=title,
                content=content,
                category_id=category_id if category_id else None,
                status=status,
                author=request.user,
            )
            messages.success(request, f"Article '{title}' créé!")
            return redirect('superadmin:article_list')

    context = {
        'page_title': 'Nouvel Article',
        'categories': BlogCategory.objects.all(),
    }
    return render(request, 'superadmin/articles/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def article_edit(request, pk):
    article = get_object_or_404(Article, pk=pk)

    if request.method == 'POST':
        article.title = request.POST.get('title', article.title)
        article.content = request.POST.get('content', '')
        article.category_id = request.POST.get('category') or None
        article.status = request.POST.get('status', article.status)
        article.save()
        messages.success(request, f"Article '{article.title}' mis à jour!")
        return redirect('superadmin:article_list')

    context = {
        'page_title': f'Modifier: {article.title}',
        'article': article,
        'categories': BlogCategory.objects.all(),
    }
    return render(request, 'superadmin/articles/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_article(request, pk):
    article = get_object_or_404(Article, pk=pk)

    if article.status == 'published':
        article.status = 'draft'
    else:
        article.status = 'published'
    article.save()

    if request.headers.get('HX-Request'):
        return HttpResponse(
            f'''<span class="badge badge-{'success' if article.status == 'published' else 'warning'}">
                {article.status}
            </span>''',
            headers={'HX-Trigger': '{"showToast": "Statut mis à jour"}'}
        )

    messages.success(request, "Statut mis à jour!")
    return redirect('superadmin:article_list')


# ============================================
# NEWS (Actualités)
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def news_list(request):
    news = News.objects.order_by('-created_at')

    paginator = Paginator(news, 20)
    page = request.GET.get('page', 1)
    news = paginator.get_page(page)

    context = {
        'page_title': 'Actualités',
        'news_list': news,
    }
    return render(request, 'superadmin/news/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def news_create(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        content = request.POST.get('content', '')
        is_published = request.POST.get('is_published') == 'on'

        if title:
            News.objects.create(
                title=title,
                content=content,
                is_published=is_published,
            )
            messages.success(request, f"Actualité '{title}' créée!")
            return redirect('superadmin:news_list')

    context = {'page_title': 'Nouvelle Actualité'}
    return render(request, 'superadmin/news/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def news_edit(request, pk):
    news_item = get_object_or_404(News, pk=pk)

    if request.method == 'POST':
        news_item.title = request.POST.get('title', news_item.title)
        news_item.content = request.POST.get('content', '')
        news_item.is_published = request.POST.get('is_published') == 'on'
        news_item.save()
        messages.success(request, f"Actualité '{news_item.title}' mise à jour!")
        return redirect('superadmin:news_list')

    context = {
        'page_title': f'Modifier: {news_item.title}',
        'news_item': news_item,
    }
    return render(request, 'superadmin/news/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_news(request, pk):
    news_item = get_object_or_404(News, pk=pk)
    news_item.is_published = not news_item.is_published
    news_item.save()

    if request.headers.get('HX-Request'):
        return HttpResponse(
            f'''<span class="badge badge-{'success' if news_item.is_published else 'secondary'}">
                {'Publié' if news_item.is_published else 'Brouillon'}
            </span>''',
            headers={'HX-Trigger': '{"showToast": "Statut mis à jour"}'}
        )

    return redirect('superadmin:news_list')


# ============================================
# EVENTS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def event_list(request):
    events = Event.objects.order_by('-start_date')

    context = {
        'page_title': 'Événements',
        'events': events,
    }
    return render(request, 'superadmin/events/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def event_create(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description', '')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        location = request.POST.get('location', '')

        if title and start_date:
            Event.objects.create(
                title=title,
                description=description,
                start_date=start_date,
                end_date=end_date,
                location=location,
            )
            messages.success(request, f"Événement '{title}' créé!")
            return redirect('superadmin:event_list')

    context = {'page_title': 'Nouvel Événement'}
    return render(request, 'superadmin/events/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk)

    if request.method == 'POST':
        event.title = request.POST.get('title', event.title)
        event.description = request.POST.get('description', '')
        event.start_date = request.POST.get('start_date', event.start_date)
        event.end_date = request.POST.get('end_date', event.end_date)
        event.location = request.POST.get('location', '')
        event.save()
        messages.success(request, f"Événement '{event.title}' mis à jour!")
        return redirect('superadmin:event_list')

    context = {
        'page_title': f'Modifier: {event.title}',
        'event': event,
    }
    return render(request, 'superadmin/events/form.html', context)


# ============================================
# PAGES (Legal Pages)
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def page_list(request):
    pages = LegalPage.objects.order_by('title')
    context = {
        'page_title': 'Pages légales',
        'pages': pages,
    }
    return render(request, 'superadmin/pages/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def page_create(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        content = request.POST.get('content', '')
        is_published = request.POST.get('is_published') == 'on'

        if title:
            LegalPage.objects.create(
                title=title,
                content=content,
                is_published=is_published,
            )
            messages.success(request, f"Page '{title}' créée!")
            return redirect('superadmin:page_list')

    context = {'page_title': 'Nouvelle Page'}
    return render(request, 'superadmin/pages/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def page_edit(request, pk):
    page = get_object_or_404(LegalPage, pk=pk)

    if request.method == 'POST':
        page.title = request.POST.get('title', page.title)
        page.content = request.POST.get('content', '')
        page.is_published = request.POST.get('is_published') == 'on'
        page.save()
        messages.success(request, f"Page '{page.title}' mise à jour!")
        return redirect('superadmin:page_list')

    context = {
        'page_title': f'Modifier: {page.title}',
        'page_obj': page,
    }
    return render(request, 'superadmin/pages/form.html', context)


# ============================================
# PARTNERS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def partner_list(request):
    partners = Partner.objects.order_by('name')
    context = {
        'page_title': 'Partenaires',
        'partners': partners,
    }
    return render(request, 'superadmin/partners/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def partner_create(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        website = request.POST.get('website', '')
        is_active = request.POST.get('is_active') == 'on'

        if name:
            Partner.objects.create(
                name=name,
                website=website,
                is_active=is_active,
            )
            messages.success(request, f"Partenaire '{name}' créé!")
            return redirect('superadmin:partner_list')

    context = {'page_title': 'Nouveau Partenaire'}
    return render(request, 'superadmin/partners/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def partner_edit(request, pk):
    partner = get_object_or_404(Partner, pk=pk)

    if request.method == 'POST':
        partner.name = request.POST.get('name', partner.name)
        partner.website = request.POST.get('website', '')
        partner.is_active = request.POST.get('is_active') == 'on'
        partner.save()
        messages.success(request, f"Partenaire '{partner.name}' mis à jour!")
        return redirect('superadmin:partner_list')

    context = {
        'page_title': f'Modifier: {partner.name}',
        'partner': partner,
    }
    return render(request, 'superadmin/partners/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_partner(request, pk):
    partner = get_object_or_404(Partner, pk=pk)
    partner.is_active = not partner.is_active
    partner.save()

    if request.headers.get('HX-Request'):
        return HttpResponse(
            f'''<span class="badge badge-{'success' if partner.is_active else 'secondary'}">
                {'Actif' if partner.is_active else 'Inactif'}
            </span>''',
            headers={'HX-Trigger': '{"showToast": "Statut mis à jour"}'}
        )

    return redirect('superadmin:partner_list')


# ============================================
# TESTIMONIALS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def testimonial_list(request):
    testimonials = Testimonial.objects.order_by('-created_at')
    context = {
        'page_title': 'Témoignages',
        'testimonials': testimonials,
    }
    return render(request, 'superadmin/testimonials/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def testimonial_create(request):
    if request.method == 'POST':
        author_name = request.POST.get('author_name')
        content = request.POST.get('content', '')
        is_active = request.POST.get('is_active') == 'on'

        if author_name:
            Testimonial.objects.create(
                author_name=author_name,
                content=content,
                is_active=is_active,
            )
            messages.success(request, "Témoignage créé!")
            return redirect('superadmin:testimonial_list')

    context = {'page_title': 'Nouveau Témoignage'}
    return render(request, 'superadmin/testimonials/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def testimonial_edit(request, pk):
    testimonial = get_object_or_404(Testimonial, pk=pk)

    if request.method == 'POST':
        testimonial.author_name = request.POST.get('author_name', testimonial.author_name)
        testimonial.content = request.POST.get('content', '')
        testimonial.is_active = request.POST.get('is_active') == 'on'
        testimonial.save()
        messages.success(request, "Témoignage mis à jour!")
        return redirect('superadmin:testimonial_list')

    context = {
        'page_title': 'Modifier Témoignage',
        'testimonial': testimonial,
    }
    return render(request, 'superadmin/testimonials/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_testimonial(request, pk):
    testimonial = get_object_or_404(Testimonial, pk=pk)
    testimonial.is_active = not testimonial.is_active
    testimonial.save()

    if request.headers.get('HX-Request'):
        return HttpResponse(
            f'''<span class="badge badge-{'success' if testimonial.is_active else 'secondary'}">
                {'Actif' if testimonial.is_active else 'Inactif'}
            </span>''',
            headers={'HX-Trigger': '{"showToast": "Statut mis à jour"}'}
        )

    return redirect('superadmin:testimonial_list')


# ============================================
# BRANCHES (Campus)
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def branch_list(request):
    branches = Branch.objects.order_by('name')
    context = {
        'page_title': 'Campus',
        'branches': branches,
    }
    return render(request, 'superadmin/branches/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def branch_create(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        address = request.POST.get('address', '')
        phone = request.POST.get('phone', '')
        email = request.POST.get('email', '')
        is_active = request.POST.get('is_active') == 'on'

        if name:
            Branch.objects.create(
                name=name,
                address=address,
                phone=phone,
                email=email,
                is_active=is_active,
            )
            messages.success(request, f"Campus '{name}' créé!")
            return redirect('superadmin:branch_list')

    context = {'page_title': 'Nouveau Campus'}
    return render(request, 'superadmin/branches/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def branch_edit(request, pk):
    branch = get_object_or_404(Branch, pk=pk)

    if request.method == 'POST':
        branch.name = request.POST.get('name', branch.name)
        branch.address = request.POST.get('address', '')
        branch.phone = request.POST.get('phone', '')
        branch.email = request.POST.get('email', '')
        branch.is_active = request.POST.get('is_active') == 'on'
        branch.save()
        messages.success(request, f"Campus '{branch.name}' mis à jour!")
        return redirect('superadmin:branch_list')

    context = {
        'page_title': f'Modifier: {branch.name}',
        'branch': branch,
    }
    return render(request, 'superadmin/branches/form.html', context)


# ============================================
# CONTACT MESSAGES
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def message_list(request):
    contact_messages = ContactMessage.objects.order_by('-created_at')

    filter_status = request.GET.get('status', '')
    if filter_status == 'pending':
        contact_messages = contact_messages.filter(status='pending')
    elif filter_status == 'answered':
        contact_messages = contact_messages.filter(status='answered')
    elif filter_status == 'closed':
        contact_messages = contact_messages.filter(status='closed')

    paginator = Paginator(contact_messages, 20)
    page = request.GET.get('page', 1)
    contact_messages = paginator.get_page(page)

    context = {
        'page_title': 'Messages de contact',
        'contact_messages': contact_messages,
        'pending_count': ContactMessage.objects.filter(status='pending').count(),
    }
    return render(request, 'superadmin/messages/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def message_detail(request, pk):
    """Détail d'un message de contact"""
    message = get_object_or_404(ContactMessage, pk=pk)

    context = {
        'page_title': f'Message de {message.full_name}',
        'message': message,
    }
    return render(request, 'superadmin/messages/detail.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def update_message_status(request, pk):
    """Changer le statut d'un message"""
    if request.method == 'POST':
        message = get_object_or_404(ContactMessage, pk=pk)
        new_status = request.POST.get('status', 'pending')

        if new_status in ['pending', 'answered', 'closed']:
            message.status = new_status
            message.save()
            messages.success(request, f'Statut mis à jour: {new_status}')

        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Refresh': 'true'})

        return redirect('superadmin:message_list')

    return redirect('superadmin:message_list')

@user_passes_test(superuser_required, login_url='/accounts/login/')
def message_delete(request, pk):
    """Supprimer un message"""
    if request.method == 'POST':
        message = get_object_or_404(ContactMessage, pk=pk)
        message.delete()
        messages.success(request, 'Message supprimé.')

        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/messages/'})

        return redirect('superadmin:message_list')

    return redirect('superadmin:message_list')


# ============================================================================
# SETTINGS / INSTITUTION
# ============================================================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def settings(request):
    """Paramètres généraux - Institution"""
    try:
        institution = Institution.objects.first()
    except:
        institution = None

    if request.method == 'POST':
        if institution:
            # Mise à jour des champs
            institution.name = request.POST.get('name', institution.name)
            institution.slogan = request.POST.get('slogan', institution.slogan)
            institution.email = request.POST.get('email', institution.email)
            institution.phone = request.POST.get('phone', institution.phone)
            institution.address = request.POST.get('address', institution.address)
            institution.description = request.POST.get('description', institution.description)

            # Réseaux sociaux
            institution.facebook_url = request.POST.get('facebook_url', '')
            institution.twitter_url = request.POST.get('twitter_url', '')
            institution.linkedin_url = request.POST.get('linkedin_url', '')
            institution.instagram_url = request.POST.get('instagram_url', '')
            institution.youtube_url = request.POST.get('youtube_url', '')

            # Logo si uploadé
            if 'logo' in request.FILES:
                institution.logo = request.FILES['logo']

            institution.save()
            messages.success(request, 'Paramètres mis à jour avec succès.')
        else:
            messages.error(request, 'Aucune institution configurée.')

        return redirect('superadmin:settings')

    context = {
        'page_title': 'Paramètres',
        'institution': institution,
    }
    return render(request, 'superadmin/settings/index.html', context)


# ============================================================================
# CATEGORIES (Blog)
# ============================================================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def category_list(request):
    """Liste des catégories de blog"""
    from blog.models import Category
    categories = Category.objects.annotate(
        articles_count=Count('articles')
    ).order_by('name')

    context = {
        'page_title': 'Catégories Blog',
        'categories': categories,
    }
    return render(request, 'superadmin/categories/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def category_create(request):
    """Créer une catégorie"""
    from blog.models import Category

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        slug = request.POST.get('slug', '').strip()
        description = request.POST.get('description', '').strip()

        if not name:
            messages.error(request, 'Le nom est obligatoire.')
            return redirect('superadmin:category_create')

        if not slug:
            slug = slugify(name)

        if Category.objects.filter(slug=slug).exists():
            messages.error(request, 'Ce slug existe déjà.')
            return redirect('superadmin:category_create')

        Category.objects.create(
            name=name,
            slug=slug,
            description=description
        )
        messages.success(request, 'Catégorie créée avec succès.')
        return redirect('superadmin:category_list')

    context = {
        'page_title': 'Nouvelle catégorie',
    }
    return render(request, 'superadmin/categories/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def category_edit(request, pk):
    """Modifier une catégorie"""
    from blog.models import Category
    category = get_object_or_404(Category, pk=pk)

    if request.method == 'POST':
        category.name = request.POST.get('name', '').strip()
        category.slug = request.POST.get('slug', '').strip() or slugify(category.name)
        category.description = request.POST.get('description', '').strip()

        if not category.name:
            messages.error(request, 'Le nom est obligatoire.')
            return redirect('superadmin:category_edit', pk=pk)

        category.save()
        messages.success(request, 'Catégorie mise à jour.')
        return redirect('superadmin:category_list')

    context = {
        'page_title': f'Modifier: {category.name}',
        'category': category,
    }
    return render(request, 'superadmin/categories/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def category_delete(request, pk):
    """Supprimer une catégorie"""
    from blog.models import Category

    if request.method == 'POST':
        category = get_object_or_404(Category, pk=pk)

        # Vérifier s'il y a des articles liés
        if category.articles.exists():
            messages.error(request, 'Impossible de supprimer: des articles utilisent cette catégorie.')
            return redirect('superadmin:category_list')

        category.delete()
        messages.success(request, 'Catégorie supprimée.')

        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/categories/'})

        return redirect('superadmin:category_list')

    return redirect('superadmin:category_list')


# ============================================================================
# HTMX SEARCH ENDPOINTS
# ============================================================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def search_global(request):
    """Recherche globale HTMX"""
    query = request.GET.get('q', '').strip()

    if len(query) < 2:
        return HttpResponse('<div class="search-results empty">Tapez au moins 2 caractères...</div>')

    results = []

    # Recherche Formations
    formations = Programme.objects.filter(
        Q(title__icontains=query) | Q(description__icontains=query)
    )[:5]
    for f in formations:
        results.append({
            'type': 'Formation',
            'title': f.title,
            'url': f"/superadmin/formations/{f.pk}/edit/",
            'icon': 'fa-graduation-cap'
        })

    # Recherche Articles
    try:
        from blog.models import Article
        articles = Article.objects.filter(
            Q(title__icontains=query) | Q(content__icontains=query)
        )[:5]
        for a in articles:
            results.append({
                'type': 'Article',
                'title': a.title,
                'url': f"/superadmin/articles/{a.pk}/edit/",
                'icon': 'fa-newspaper'
            })
    except:
        pass

    # Recherche Étudiants
    try:
        students = Student.objects.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(student_id__icontains=query)
        )[:5]
        for s in students:
            results.append({
                'type': 'Étudiant',
                'title': s.user.get_full_name() or s.user.email,
                'url': f"/superadmin/students/{s.pk}/",
                'icon': 'fa-user-graduate'
            })
    except:
        pass

    if not results:
        return HttpResponse(f'<div class="search-results empty">Aucun résultat pour "{query}"</div>')

    # Générer le HTML des résultats
    html = '<div class="search-results">'
    for r in results:
        html += f'''
            <a href="{r['url']}" class="search-result-item">
                <i class="fas {r['icon']}"></i>
                <span class="result-type">{r['type']}</span>
                <span class="result-title">{r['title']}</span>
            </a>
        '''
    html += '</div>'

    return HttpResponse(html)


# ============================================================================
# BULK ACTIONS (Actions groupées)
# ============================================================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def bulk_action(request):
    """Traitement des actions groupées"""
    if request.method != 'POST':
        return redirect('superadmin:dashboard')

    action = request.POST.get('action', '')
    model_type = request.POST.get('model_type', '')
    selected_ids = request.POST.getlist('selected_ids')

    if not selected_ids:
        messages.warning(request, 'Aucun élément sélectionné.')
        return redirect(request.META.get('HTTP_REFERER', 'superadmin:dashboard'))

    count = 0

    if model_type == 'formation':
        queryset = Programme.objects.filter(pk__in=selected_ids)

        if action == 'publish':
            count = queryset.update(status='published')
            messages.success(request, f'{count} formation(s) publiée(s).')
        elif action == 'unpublish':
            count = queryset.update(status='draft')
            messages.success(request, f'{count} formation(s) mise(s) en brouillon.')
        elif action == 'archive':
            count = queryset.update(status='archived')
            messages.success(request, f'{count} formation(s) archivée(s).')
        elif action == 'delete':
            count = queryset.count()
            queryset.delete()
            messages.success(request, f'{count} formation(s) supprimée(s).')

    elif model_type == 'article':
        from blog.models import Article
        queryset = Article.objects.filter(pk__in=selected_ids)

        if action == 'publish':
            count = queryset.update(status='published')
        elif action == 'unpublish':
            count = queryset.update(status='draft')
        elif action == 'delete':
            count = queryset.count()
            queryset.delete()

        messages.success(request, f'{count} article(s) traité(s).')

    elif model_type == 'message':

        queryset = ContactMessage.objects.filter(pk__in=selected_ids)

    if action == 'mark_answered':

        count = queryset.update(status='answered')

        messages.success(request, f'{count} message(s) marqué(s) comme répondu(s).')

    elif action == 'mark_closed':

        count = queryset.update(status='closed')

        messages.success(request, f'{count} message(s) clôturé(s).')

    elif action == 'delete':

        count = queryset.count()

        queryset.delete()

        messages.success(request, f'{count} message(s) supprimé(s).')

    return redirect(request.META.get('HTTP_REFERER', 'superadmin:dashboard'))


# ============================================================================
# EXPORT DATA
# ============================================================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def export_data(request, model_type):
    """Export CSV des données"""
    import csv
    from django.http import HttpResponse as DjangoHttpResponse

    response = DjangoHttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{model_type}_export.csv"'
    response.write('\ufeff'.encode('utf-8'))  # BOM pour Excel

    writer = csv.writer(response, delimiter=';')

    if model_type == 'formations':
        writer.writerow(['ID', 'Titre', 'Cycle', 'Statut', 'Créé le'])
        for p in Programme.objects.all():
            writer.writerow([
                p.pk,
                p.title,
                getattr(p.cycle, 'name', 'N/A'),
                p.status,
                p.created_at.strftime('%d/%m/%Y') if hasattr(p, 'created_at') else 'N/A'
            ])

    elif model_type == 'students':
        writer.writerow(['ID', 'Matricule', 'Nom', 'Email', 'Téléphone'])
        for s in Student.objects.select_related('user').all():
            writer.writerow([
                s.pk,
                s.student_id,
                s.user.get_full_name(),
                s.user.email,
                getattr(s, 'phone', 'N/A')
            ])

    elif model_type == 'candidatures':
        writer.writerow(['ID', 'Candidat', 'Formation', 'Statut', 'Date'])
        for c in Candidature.objects.select_related('user', 'programme').all():
            writer.writerow([
                c.pk,
                c.user.get_full_name(),
                c.programme.title,
                c.status,
                c.created_at.strftime('%d/%m/%Y')
            ])

    elif model_type == 'payments':
        writer.writerow(['ID', 'Étudiant', 'Montant', 'Statut', 'Date'])
        for p in Payment.objects.select_related('inscription__student__user').all():
            writer.writerow([
                p.pk,
                p.inscription.student.user.get_full_name() if p.inscription else 'N/A',
                p.amount,
                p.status,
                p.created_at.strftime('%d/%m/%Y')
            ])

    return response


# ============================================================================
# VUES MANQUANTES - À AJOUTER DANS views.py
# ============================================================================

# ---------- FORMATIONS ----------

@user_passes_test(superuser_required, login_url='/accounts/login/')
def formation_detail(request, pk):
    formation = get_object_or_404(Programme, pk=pk)
    context = {
        'page_title': formation.title,
        'formation': formation,
    }
    return render(request, 'superadmin/formations/detail.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def formation_delete(request, pk):
    if request.method == 'POST':
        formation = get_object_or_404(Programme, pk=pk)
        formation.delete()
        messages.success(request, 'Formation supprimée.')
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/formations/'})
        return redirect('superadmin:formation_list')
    return redirect('superadmin:formation_list')


# ---------- CYCLES ----------

@user_passes_test(superuser_required, login_url='/accounts/login/')
def cycle_delete(request, pk):
    if request.method == 'POST':
        cycle = get_object_or_404(Cycle, pk=pk)
        cycle.delete()
        messages.success(request, 'Cycle supprimé.')
        return redirect('superadmin:cycle_list')
    return redirect('superadmin:cycle_list')


# ---------- FILIERES ----------

@user_passes_test(superuser_required, login_url='/accounts/login/')
def filiere_delete(request, pk):
    if request.method == 'POST':
        filiere = get_object_or_404(Filiere, pk=pk)
        filiere.delete()
        messages.success(request, 'Filière supprimée.')
        return redirect('superadmin:filiere_list')
    return redirect('superadmin:filiere_list')


# ---------- DIPLOMAS ----------

@user_passes_test(superuser_required, login_url='/accounts/login/')
def diploma_delete(request, pk):
    if request.method == 'POST':
        diploma = get_object_or_404(Diploma, pk=pk)
        diploma.delete()
        messages.success(request, 'Diplôme supprimé.')
        return redirect('superadmin:diploma_list')
    return redirect('superadmin:diploma_list')


# ---------- CANDIDATURES ----------

@user_passes_test(superuser_required, login_url='/accounts/login/')
def candidature_delete(request, pk):
    if request.method == 'POST':
        candidature = get_object_or_404(Candidature, pk=pk)
        candidature.delete()
        messages.success(request, 'Candidature supprimée.')
        return redirect('superadmin:candidature_list')
    return redirect('superadmin:candidature_list')


# ---------- INSCRIPTIONS ----------

@user_passes_test(superuser_required, login_url='/accounts/login/')
def inscription_status(request, pk):
    if request.method == 'POST':
        inscription = get_object_or_404(Inscription, pk=pk)
        new_status = request.POST.get('status')
        if new_status:
            inscription.status = new_status
            inscription.save()
            messages.success(request, f'Statut mis à jour: {new_status}')
        return redirect('superadmin:inscription_detail', pk=pk)
    return redirect('superadmin:inscription_list')


# ---------- STUDENTS ----------

@user_passes_test(superuser_required, login_url='/accounts/login/')
def student_edit(request, pk):
    student = get_object_or_404(Student, pk=pk)

    if request.method == 'POST':
        # Mise à jour des infos de base
        student.user.first_name = request.POST.get('first_name', '')
        student.user.last_name = request.POST.get('last_name', '')
        student.user.save()

        if hasattr(student, 'phone'):
            student.phone = request.POST.get('phone', '')
        student.save()

        messages.success(request, 'Étudiant mis à jour.')
        return redirect('superadmin:student_detail', pk=pk)

    context = {
        'page_title': f'Modifier: {student.user.get_full_name()}',
        'student': student,
    }
    return render(request, 'superadmin/students/form.html', context)


# ---------- FEES ----------

@user_passes_test(superuser_required, login_url='/accounts/login/')
def fee_delete(request, pk):
    if request.method == 'POST':
        fee = get_object_or_404(Fee, pk=pk)
        fee.delete()
        messages.success(request, 'Frais supprimé.')
        return redirect('superadmin:fee_list')
    return redirect('superadmin:fee_list')


# ---------- ARTICLES ----------

@user_passes_test(superuser_required, login_url='/accounts/login/')
def article_detail(request, pk):
    from blog.models import Article
    article = get_object_or_404(Article, pk=pk)
    context = {
        'page_title': article.title,
        'article': article,
    }
    return render(request, 'superadmin/articles/detail.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def article_delete(request, pk):
    if request.method == 'POST':
        from blog.models import Article
        article = get_object_or_404(Article, pk=pk)
        article.delete()
        messages.success(request, 'Article supprimé.')
        return redirect('superadmin:article_list')
    return redirect('superadmin:article_list')


# ---------- NEWS ----------

@user_passes_test(superuser_required, login_url='/accounts/login/')
def news_detail(request, pk):
    from news.models import News
    news_item = get_object_or_404(News, pk=pk)
    context = {
        'page_title': news_item.title,
        'news': news_item,
    }
    return render(request, 'superadmin/news/detail.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def news_delete(request, pk):
    if request.method == 'POST':
        from news.models import News
        news_item = get_object_or_404(News, pk=pk)
        news_item.delete()
        messages.success(request, 'Actualité supprimée.')
        return redirect('superadmin:news_list')
    return redirect('superadmin:news_list')


# ---------- EVENTS ----------

@user_passes_test(superuser_required, login_url='/accounts/login/')
def event_detail(request, pk):
    from news.models import Event
    event = get_object_or_404(Event, pk=pk)
    context = {
        'page_title': event.title,
        'event': event,
    }
    return render(request, 'superadmin/events/detail.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def event_delete(request, pk):
    if request.method == 'POST':
        from news.models import Event
        event = get_object_or_404(Event, pk=pk)
        event.delete()
        messages.success(request, 'Événement supprimé.')
        return redirect('superadmin:event_list')
    return redirect('superadmin:event_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_event(request, pk):
    if request.method == 'POST':
        from news.models import Event
        event = get_object_or_404(Event, pk=pk)
        if hasattr(event, 'is_active'):
            event.is_active = not event.is_active
            event.save()
        messages.success(request, 'Événement mis à jour.')
        return redirect('superadmin:event_list')
    return redirect('superadmin:event_list')


# ---------- PAGES ----------

@user_passes_test(superuser_required, login_url='/accounts/login/')
def page_detail(request, pk):
    page = get_object_or_404(LegalPage, pk=pk)
    context = {
        'page_title': page.title,
        'page': page,
    }
    return render(request, 'superadmin/pages/detail.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def page_delete(request, pk):
    if request.method == 'POST':
        page = get_object_or_404(LegalPage, pk=pk)
        page.delete()
        messages.success(request, 'Page supprimée.')
        return redirect('superadmin:page_list')
    return redirect('superadmin:page_list')


# ---------- PARTNERS ----------

@user_passes_test(superuser_required, login_url='/accounts/login/')
def partner_delete(request, pk):
    if request.method == 'POST':
        partner = get_object_or_404(Partner, pk=pk)
        partner.delete()
        messages.success(request, 'Partenaire supprimé.')
        return redirect('superadmin:partner_list')
    return redirect('superadmin:partner_list')


# ---------- TESTIMONIALS ----------

@user_passes_test(superuser_required, login_url='/accounts/login/')
def testimonial_delete(request, pk):
    if request.method == 'POST':
        testimonial = get_object_or_404(Testimonial, pk=pk)
        testimonial.delete()
        messages.success(request, 'Témoignage supprimé.')
        return redirect('superadmin:testimonial_list')
    return redirect('superadmin:testimonial_list')


# ---------- BRANCHES ----------

@user_passes_test(superuser_required, login_url='/accounts/login/')
def branch_delete(request, pk):
    if request.method == 'POST':
        branch = get_object_or_404(Branch, pk=pk)
        branch.delete()
        messages.success(request, 'Campus supprimé.')
        return redirect('superadmin:branch_list')
    return redirect('superadmin:branch_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_branch(request, pk):
    if request.method == 'POST':
        branch = get_object_or_404(Branch, pk=pk)
        if hasattr(branch, 'is_active'):
            branch.is_active = not branch.is_active
            branch.save()
        messages.success(request, 'Campus mis à jour.')
        return redirect('superadmin:branch_list')
    return redirect('superadmin:branch_list')