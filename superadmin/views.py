# superadmin/views.py
# FICHIER NETTOYÉ - SANS DOUBLONS - PRÊT POUR PRODUCTION

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import user_passes_test
from django.http import HttpResponse
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum
from django.utils.text import slugify
from django.utils import timezone

# Imports des modèles
from formations.models import Programme, Cycle, Diploma, Fee, Filiere, ProgrammeYear, ProgrammeQuickFact, ProgrammeTab, ProgrammeSection, CompetenceBlock, CompetenceItem, RequiredDocument, ProgrammeRequiredDocument
from admissions.models import Candidature, CandidatureDocument
from blog.models import Article, Category as BlogCategory
from news.models import News, Event
from core.models import Institution, LegalPage, Partner, ContactMessage, Testimonial
from inscriptions.models import Inscription
from payments.models import Payment
from students.models import Student
from branches.models import Branch
from community.models import Category as CommunityCategory, Topic, Answer


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
    context = {
        'page_title': 'Tableau de bord',
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

    return render(request, 'superadmin/dashboard.html', context)


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
        title = formation.title
        formation.delete()
        messages.success(request, f"Formation '{title}' supprimée!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/formations/'})
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
        cycle.delete()
        messages.success(request, "Cycle supprimé!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/cycles/'})
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
        filiere.delete()
        messages.success(request, "Filière supprimée!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/filieres/'})
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
        diploma.delete()
        messages.success(request, "Diplôme supprimé!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/diplomas/'})
    return redirect('superadmin:diploma_list')


# ============================================
# CANDIDATURES
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def candidature_list(request):
    candidatures = Candidature.objects.select_related('programme').order_by('-submitted_at')
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
    candidature = get_object_or_404(Candidature.objects.select_related('programme'), pk=pk)
    documents = CandidatureDocument.objects.filter(candidature=candidature)
    context = {'page_title': f'Candidature #{pk}', 'candidature': candidature, 'documents': documents}
    return render(request, 'superadmin/candidatures/detail.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def candidature_status(request, pk):
    candidature = get_object_or_404(Candidature, pk=pk)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status:
            candidature.status = new_status
            candidature.save()
            messages.success(request, f"Statut mis à jour: {new_status}")
    return redirect('superadmin:candidature_detail', pk=pk)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def candidature_edit(request, pk):
    candidature = get_object_or_404(Candidature, pk=pk)
    if request.method == 'POST':
        candidature.status = request.POST.get('status', candidature.status)
        candidature.save()
        messages.success(request, f"Candidature #{candidature.pk} mise à jour!")
        return redirect('superadmin:candidature_list')
    return render(request, 'superadmin/candidatures/form.html', {'page_title': f'Modifier Candidature #{pk}', 'candidature': candidature})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def candidature_delete(request, pk):
    if request.method == 'POST':
        candidature = get_object_or_404(Candidature, pk=pk)
        candidature.delete()
        messages.success(request, "Candidature supprimée!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/candidatures/'})
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
def candidature_document_delete(request, pk):
    document = get_object_or_404(CandidatureDocument, pk=pk)
    candidature_pk = document.candidature.pk
    if request.method == 'POST':
        document.delete()
        messages.success(request, "Document supprimé!")
    return redirect('superadmin:candidature_detail', pk=candidature_pk)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def candidature_document_validate(request, pk):
    document = get_object_or_404(CandidatureDocument, pk=pk)
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
    inscriptions = Inscription.objects.select_related('student', 'programme').order_by('-created_at')
    status = request.GET.get('status', '')
    if status:
        inscriptions = inscriptions.filter(status=status)

    paginator = Paginator(inscriptions, 20)
    page = request.GET.get('page', 1)
    inscriptions = paginator.get_page(page)

    return render(request, 'superadmin/inscriptions/list.html', {'page_title': 'Inscriptions', 'inscriptions': inscriptions})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def inscription_create(request):
    """Créer une inscription depuis une candidature acceptée."""
    if request.method == 'POST':
        candidature_id = request.POST.get('candidature')
        amount_due = request.POST.get('amount_due')
        status = request.POST.get('status', 'awaiting_payment')

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
            amount_due=amount_due,
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
            'candidature': candidature,
            'amount_due': amount_due,
        }
        return render(request, 'superadmin/inscriptions/create.html', context)
    else:
        context = {
            'page_title': 'Créer une inscription',
            'candidature': None,
        }
        return render(request, 'superadmin/inscriptions/create.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def inscription_detail(request, pk):
    inscription = get_object_or_404(Inscription.objects.select_related('student__user', 'programme', 'candidature'), pk=pk)
    return render(request, 'superadmin/inscriptions/detail.html', {'page_title': f'Inscription #{pk}', 'inscription': inscription})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def inscription_edit(request, pk):
    inscription = get_object_or_404(Inscription, pk=pk)
    if request.method == 'POST':
        inscription.status = request.POST.get('status', inscription.status)
        inscription.save()
        messages.success(request, f"Inscription #{inscription.pk} mise à jour!")
        return redirect('superadmin:inscription_list')
    return render(request, 'superadmin/inscriptions/form.html', {'page_title': f'Modifier Inscription #{pk}', 'inscription': inscription})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def inscription_delete(request, pk):
    if request.method == 'POST':
        inscription = get_object_or_404(Inscription, pk=pk)
        inscription.delete()
        messages.success(request, "Inscription supprimée!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/inscriptions/'})
    return redirect('superadmin:inscription_list')


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

    return render(request, 'superadmin/students/list.html', {'page_title': 'Étudiants', 'students': students})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def student_detail(request, pk):
    student = get_object_or_404(Student.objects.select_related('user'), pk=pk)
    inscriptions = Inscription.objects.filter(student=student).select_related('programme')
    payments = Payment.objects.filter(student=student).select_related('inscription')
    context = {
        'page_title': f'Étudiant: {student.user.get_full_name()}',
        'student': student,
        'inscriptions': inscriptions,
        'payments': payments,
    }
    return render(request, 'superadmin/students/detail.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def student_edit(request, pk):
    student = get_object_or_404(Student.objects.select_related('user'), pk=pk)
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
        student.delete()
        messages.success(request, "Étudiant supprimé!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/students/'})
    return redirect('superadmin:student_list')


# ============================================
# PAYMENTS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def payment_list(request):
    payments = Payment.objects.select_related('inscription__student__user', 'inscription__candidature').order_by('-paid_at')
    search = request.GET.get('search', '')
    status = request.GET.get('status', '')
    method = request.GET.get('method', '')

    if search:
        payments = payments.filter(
            Q(inscription__student__user__first_name__icontains=search) |
            Q(inscription__student__user__last_name__icontains=search) |
            Q(inscription__student__matricule__icontains=search) |
            Q(reference__icontains=search)
        )
    if status:
        payments = payments.filter(status=status)
    if method:
        payments = payments.filter(method=method)

    paginator = Paginator(payments, 20)
    page = request.GET.get('page', 1)
    payments = paginator.get_page(page)

    context = {
        'page_title': 'Paiements',
        'payments': payments,
        'status_choices': Payment.STATUS_CHOICES,
        'method_choices': Payment.METHOD_CHOICES,
        'filters': {'search': search, 'status': status, 'method': method},
    }

    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/payments/_payment_table.html', context)
    return render(request, 'superadmin/payments/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def payment_detail(request, pk):
    payment = get_object_or_404(Payment.objects.select_related('inscription__student__user', 'inscription__candidature', 'agent__user'), pk=pk)
    context = {'page_title': f'Paiement #{payment.reference}', 'payment': payment}
    return render(request, 'superadmin/payments/detail.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def payment_edit(request, pk):
    payment = get_object_or_404(Payment, pk=pk)

    if request.method == 'POST':
        payment.status = request.POST.get('status', payment.status)
        payment.reference = request.POST.get('reference', payment.reference)
        payment.save()
        messages.success(request, f"Paiement '{payment.reference}' mis à jour!")
        return redirect('superadmin:payment_list')

    context = {
        'page_title': f'Modifier: {payment.reference}',
        'payment': payment,
        'status_choices': Payment.STATUS_CHOICES,
    }
    return render(request, 'superadmin/payments/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def payment_delete(request, pk):
    if request.method == 'POST':
        payment = get_object_or_404(Payment, pk=pk)
        reference = payment.reference
        payment.delete()
        messages.success(request, f"Paiement '{reference}' supprimé!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/payments/'})
    return redirect('superadmin:payment_list')


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
        'fee': fee,
        'programme_years': ProgrammeYear.objects.select_related('programme').all(),
    }
    return render(request, 'superadmin/fees/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def fee_delete(request, pk):
    if request.method == 'POST':
        fee = get_object_or_404(Fee, pk=pk)
        label = fee.label
        fee.delete()
        messages.success(request, f"Frais '{label}' supprimé!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/fees/'})
    return redirect('superadmin:fee_list')


# ============================================
# ARTICLES
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def article_list(request):
    articles = Article.objects.select_related('author', 'category').order_by('-created_at')
    status = request.GET.get('status', '')
    if status:
        articles = articles.filter(status=status)

    paginator = Paginator(articles, 20)
    articles = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'superadmin/articles/list.html', {'page_title': 'Articles Blog', 'articles': articles})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def article_create(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        if title:
            Article.objects.create(
                title=title,
                content=request.POST.get('content', ''),
                category_id=request.POST.get('category') or None,
                status=request.POST.get('status', 'draft'),
                author=request.user,
            )
            messages.success(request, f"Article '{title}' créé!")
            return redirect('superadmin:article_list')
    return render(request, 'superadmin/articles/form.html', {'page_title': 'Nouvel Article', 'categories': BlogCategory.objects.all()})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def article_detail(request, pk):
    article = get_object_or_404(Article.objects.select_related('author', 'category'), pk=pk)
    return render(request, 'superadmin/articles/detail.html', {'page_title': article.title, 'article': article})


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
    return render(request, 'superadmin/articles/form.html', {'page_title': f'Modifier: {article.title}', 'article': article, 'categories': BlogCategory.objects.all()})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def article_delete(request, pk):
    if request.method == 'POST':
        article = get_object_or_404(Article, pk=pk)
        article.delete()
        messages.success(request, "Article supprimé!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/articles/'})
    return redirect('superadmin:article_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_article(request, pk):
    article = get_object_or_404(Article, pk=pk)
    article.status = 'draft' if article.status == 'published' else 'published'
    article.save()
    if request.headers.get('HX-Request'):
        return HttpResponse(f'<span class="badge">{article.status}</span>', headers={'HX-Trigger': '{"showToast": "Statut mis à jour"}'})
    messages.success(request, "Statut mis à jour!")
    return redirect('superadmin:article_list')


# ============================================
# CATEGORIES
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def category_list(request):
    categories = BlogCategory.objects.annotate(articles_count=Count('article')).order_by('name')
    return render(request, 'superadmin/categories/list.html', {'page_title': 'Catégories Blog', 'categories': categories})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def category_create(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            BlogCategory.objects.create(name=name, slug=slugify(name), description=request.POST.get('description', ''))
            messages.success(request, 'Catégorie créée!')
            return redirect('superadmin:category_list')
    return render(request, 'superadmin/categories/form.html', {'page_title': 'Nouvelle catégorie'})


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
    return render(request, 'superadmin/categories/form.html', {'page_title': f'Modifier: {category.name}', 'category': category})


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
    news = News.objects.order_by('-created_at')
    paginator = Paginator(news, 20)
    news = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'superadmin/news/list.html', {'page_title': 'Actualités', 'news_list': news})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def news_create(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        if title:
            News.objects.create(title=title, content=request.POST.get('content', ''), is_published=request.POST.get('is_published') == 'on')
            messages.success(request, f"Actualité '{title}' créée!")
            return redirect('superadmin:news_list')
    return render(request, 'superadmin/news/form.html', {'page_title': 'Nouvelle Actualité'})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def news_detail(request, pk):
    news_item = get_object_or_404(News, pk=pk)
    return render(request, 'superadmin/news/detail.html', {'page_title': news_item.title, 'news_item': news_item})


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
    return render(request, 'superadmin/news/form.html', {'page_title': f'Modifier: {news_item.title}', 'news_item': news_item})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def news_delete(request, pk):
    if request.method == 'POST':
        news_item = get_object_or_404(News, pk=pk)
        news_item.delete()
        messages.success(request, "Actualité supprimée!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/news/'})
    return redirect('superadmin:news_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_news(request, pk):
    news_item = get_object_or_404(News, pk=pk)
    news_item.is_published = not news_item.is_published
    news_item.save()
    if request.headers.get('HX-Request'):
        return HttpResponse(f'<span class="badge">{"Publié" if news_item.is_published else "Brouillon"}</span>', headers={'HX-Trigger': '{"showToast": "Statut mis à jour"}'})
    return redirect('superadmin:news_list')


# ============================================
# EVENTS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def event_list(request):
    events = Event.objects.order_by('-start_date')
    return render(request, 'superadmin/events/list.html', {'page_title': 'Événements', 'events': events})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def event_create(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        start_date = request.POST.get('start_date')
        if title and start_date:
            Event.objects.create(title=title, description=request.POST.get('description', ''), start_date=start_date, end_date=request.POST.get('end_date'), location=request.POST.get('location', ''))
            messages.success(request, f"Événement '{title}' créé!")
            return redirect('superadmin:event_list')
    return render(request, 'superadmin/events/form.html', {'page_title': 'Nouvel Événement'})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk)
    return render(request, 'superadmin/events/detail.html', {'page_title': event.title, 'event': event})


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
    return render(request, 'superadmin/events/form.html', {'page_title': f'Modifier: {event.title}', 'event': event})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def event_delete(request, pk):
    if request.method == 'POST':
        event = get_object_or_404(Event, pk=pk)
        event.delete()
        messages.success(request, "Événement supprimé!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/events/'})
    return redirect('superadmin:event_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_event(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if hasattr(event, 'is_active'):
        event.is_active = not event.is_active
        event.save()
    messages.success(request, 'Événement mis à jour!')
    return redirect('superadmin:event_list')


# ============================================
# PAGES
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def page_list(request):
    pages = LegalPage.objects.order_by('title')
    return render(request, 'superadmin/pages/list.html', {'page_title': 'Pages légales', 'pages': pages})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def page_create(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        if title:
            LegalPage.objects.create(title=title, content=request.POST.get('content', ''), is_published=request.POST.get('is_published') == 'on')
            messages.success(request, f"Page '{title}' créée!")
            return redirect('superadmin:page_list')
    return render(request, 'superadmin/pages/form.html', {'page_title': 'Nouvelle Page'})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def page_detail(request, pk):
    page = get_object_or_404(LegalPage, pk=pk)
    return render(request, 'superadmin/pages/detail.html', {'page_title': page.title, 'page': page})


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
    return render(request, 'superadmin/pages/form.html', {'page_title': f'Modifier: {page.title}', 'page_obj': page})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def page_delete(request, pk):
    if request.method == 'POST':
        page = get_object_or_404(LegalPage, pk=pk)
        page.delete()
        messages.success(request, "Page supprimée!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/pages/'})
    return redirect('superadmin:page_list')


# ============================================
# PARTNERS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def partner_list(request):
    partners = Partner.objects.order_by('name')
    return render(request, 'superadmin/partners/list.html', {'page_title': 'Partenaires', 'partners': partners})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def partner_create(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        if name:
            Partner.objects.create(name=name, website=request.POST.get('website', ''), is_active=request.POST.get('is_active') == 'on')
            messages.success(request, f"Partenaire '{name}' créé!")
            return redirect('superadmin:partner_list')
    return render(request, 'superadmin/partners/form.html', {'page_title': 'Nouveau Partenaire'})


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
    return render(request, 'superadmin/partners/form.html', {'page_title': f'Modifier: {partner.name}', 'partner': partner})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def partner_delete(request, pk):
    if request.method == 'POST':
        partner = get_object_or_404(Partner, pk=pk)
        partner.delete()
        messages.success(request, "Partenaire supprimé!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/partners/'})
    return redirect('superadmin:partner_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_partner(request, pk):
    partner = get_object_or_404(Partner, pk=pk)
    partner.is_active = not partner.is_active
    partner.save()
    if request.headers.get('HX-Request'):
        return HttpResponse(f'<span class="badge">{"Actif" if partner.is_active else "Inactif"}</span>', headers={'HX-Trigger': '{"showToast": "Statut mis à jour"}'})
    return redirect('superadmin:partner_list')


# ============================================
# TESTIMONIALS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def testimonial_list(request):
    testimonials = Testimonial.objects.order_by('-created_at')
    return render(request, 'superadmin/testimonials/list.html', {'page_title': 'Témoignages', 'testimonials': testimonials})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def testimonial_create(request):
    if request.method == 'POST':
        author_name = request.POST.get('author_name')
        quote = request.POST.get('quote', '')
        if author_name and quote:
            Testimonial.objects.create(author_name=author_name, quote=quote, author_role=request.POST.get('author_role', ''), is_active=request.POST.get('is_active') == 'on')
            messages.success(request, "Témoignage créé!")
            return redirect('superadmin:testimonial_list')
    return render(request, 'superadmin/testimonials/form.html', {'page_title': 'Nouveau Témoignage'})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def testimonial_edit(request, pk):
    testimonial = get_object_or_404(Testimonial, pk=pk)
    if request.method == 'POST':
        testimonial.author_name = request.POST.get('author_name', testimonial.author_name)
        testimonial.quote = request.POST.get('quote', testimonial.quote)
        testimonial.author_role = request.POST.get('author_role', '')
        testimonial.is_active = request.POST.get('is_active') == 'on'
        testimonial.save()
        messages.success(request, "Témoignage mis à jour!")
        return redirect('superadmin:testimonial_list')
    return render(request, 'superadmin/testimonials/form.html', {'page_title': 'Modifier Témoignage', 'testimonial': testimonial})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def testimonial_delete(request, pk):
    if request.method == 'POST':
        testimonial = get_object_or_404(Testimonial, pk=pk)
        testimonial.delete()
        messages.success(request, "Témoignage supprimé!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/testimonials/'})
    return redirect('superadmin:testimonial_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_testimonial(request, pk):
    testimonial = get_object_or_404(Testimonial, pk=pk)
    testimonial.is_active = not testimonial.is_active
    testimonial.save()
    if request.headers.get('HX-Request'):
        return HttpResponse(f'<span class="badge">{"Actif" if testimonial.is_active else "Inactif"}</span>', headers={'HX-Trigger': '{"showToast": "Statut mis à jour"}'})
    return redirect('superadmin:testimonial_list')


# ============================================
# BRANCHES
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def branch_list(request):
    branches = Branch.objects.order_by('name')
    return render(request, 'superadmin/branches/list.html', {'page_title': 'Campus', 'branches': branches})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def branch_create(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        if name:
            Branch.objects.create(name=name, address=request.POST.get('address', ''), phone=request.POST.get('phone', ''), email=request.POST.get('email', ''), is_active=request.POST.get('is_active') == 'on')
            messages.success(request, f"Campus '{name}' créé!")
            return redirect('superadmin:branch_list')
    return render(request, 'superadmin/branches/form.html', {'page_title': 'Nouveau Campus'})


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
    return render(request, 'superadmin/branches/form.html', {'page_title': f'Modifier: {branch.name}', 'branch': branch})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def branch_delete(request, pk):
    if request.method == 'POST':
        branch = get_object_or_404(Branch, pk=pk)
        branch.delete()
        messages.success(request, "Campus supprimé!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/branches/'})
    return redirect('superadmin:branch_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_branch(request, pk):
    branch = get_object_or_404(Branch, pk=pk)
    if hasattr(branch, 'is_active'):
        branch.is_active = not branch.is_active
        branch.save()
    messages.success(request, 'Campus mis à jour!')
    return redirect('superadmin:branch_list')


# ============================================
# MESSAGES
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def message_list(request):
    contact_messages = ContactMessage.objects.order_by('-created_at')
    filter_status = request.GET.get('status', '')
    if filter_status in ['pending', 'answered', 'closed']:
        contact_messages = contact_messages.filter(status=filter_status)

    paginator = Paginator(contact_messages, 20)
    contact_messages = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'superadmin/messages/list.html', {'page_title': 'Messages de contact', 'contact_messages': contact_messages, 'pending_count': ContactMessage.objects.filter(status='pending').count()})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def message_detail(request, pk):
    message = get_object_or_404(ContactMessage, pk=pk)
    return render(request, 'superadmin/messages/detail.html', {'page_title': f'Message de {message.full_name}', 'message': message})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def update_message_status(request, pk):
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
    if request.method == 'POST':
        message = get_object_or_404(ContactMessage, pk=pk)
        message.delete()
        messages.success(request, 'Message supprimé.')
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/messages/'})
        return redirect('superadmin:message_list')
    return redirect('superadmin:message_list')


# ============================================
# SETTINGS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def settings(request):
    institution = Institution.objects.first()
    if request.method == 'POST':
        if institution:
            institution.name = request.POST.get('name', institution.name)
            institution.email = request.POST.get('email', institution.email)
            institution.phone = request.POST.get('phone', institution.phone)
            institution.address = request.POST.get('address', institution.address)
            institution.save()
            messages.success(request, 'Paramètres mis à jour!')
        return redirect('superadmin:settings')
    return render(request, 'superadmin/settings/index.html', {'page_title': 'Paramètres', 'institution': institution})


# ============================================
# SEARCH
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def search_global(request):
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return HttpResponse('<div class="search-results empty">Tapez au moins 2 caractères...</div>')

    results = []
    for f in Programme.objects.filter(Q(title__icontains=query) | Q(description__icontains=query))[:5]:
        results.append({'type': 'Formation', 'title': f.title, 'url': f'/superadmin/formations/{f.pk}/edit/', 'icon': 'fa-graduation-cap'})
    for a in Article.objects.filter(Q(title__icontains=query) | Q(content__icontains=query))[:5]:
        results.append({'type': 'Article', 'title': a.title, 'url': f'/superadmin/articles/{a.pk}/edit/', 'icon': 'fa-newspaper'})
    for s in Student.objects.filter(Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query) | Q(matricule__icontains=query))[:5]:
        results.append({'type': 'Étudiant', 'title': s.user.get_full_name() or s.user.email, 'url': f'/superadmin/students/{s.pk}/', 'icon': 'fa-user-graduate'})

    if not results:
        return HttpResponse(f'<div class="search-results empty">Aucun résultat pour "{query}"</div>')

    html = '<div class="search-results">'
    for r in results:
        html += f'<a href="{r["url"]}" class="search-result-item"><i class="fas {r["icon"]}"></i><span class="result-type">{r["type"]}</span><span class="result-title">{r["title"]}</span></a>'
    html += '</div>'
    return HttpResponse(html)


# ============================================
# BULK ACTION
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def bulk_action(request):
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
        if action == 'delete':
            count = queryset.count(); queryset.delete()
        elif action == 'activate':
            count = queryset.update(is_active=True)
        elif action == 'deactivate':
            count = queryset.update(is_active=False)
    elif model_type == 'article':
        queryset = Article.objects.filter(pk__in=selected_ids)
        if action == 'delete':
            count = queryset.count(); queryset.delete()
        elif action == 'publish':
            count = queryset.update(status='published')
    elif model_type == 'message':
        queryset = ContactMessage.objects.filter(pk__in=selected_ids)
        if action == 'delete':
            count = queryset.count(); queryset.delete()
        elif action == 'mark_answered':
            count = queryset.update(status='answered')

    messages.success(request, f'{count} élément(s) traité(s).')
    redirect_map = {'formation': 'formation_list', 'article': 'article_list', 'message': 'message_list'}
    return redirect(f'superadmin:{redirect_map.get(model_type, "dashboard")}')


# ============================================
# EXPORT
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def export_data(request, model_type):
    import csv
    from django.http import HttpResponse as DjangoHttpResponse

    response = DjangoHttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{model_type}_export.csv"'
    response.write('\ufeff'.encode('utf-8'))
    writer = csv.writer(response, delimiter=';')

    if model_type == 'students':
        writer.writerow(['ID', 'Matricule', 'Nom', 'Email'])
        for s in Student.objects.select_related('user'):
            writer.writerow([s.pk, s.matricule, s.user.get_full_name(), s.user.email])
    elif model_type == 'candidatures':
        writer.writerow(['ID', 'Candidat', 'Formation', 'Statut', 'Date'])
        for c in Candidature.objects.select_related('programme'):
            writer.writerow([c.pk, c.full_name, c.programme.title, c.status, c.submitted_at.strftime('%d/%m/%Y')])
    elif model_type == 'payments':
        writer.writerow(['ID', 'Étudiant', 'Montant', 'Statut', 'Date'])
        for p in Payment.objects.select_related('inscription__student__user'):
            writer.writerow([p.pk, p.inscription.student.user.get_full_name() if p.inscription else 'N/A', p.amount, p.status, p.created_at.strftime('%d/%m/%Y')])
    else:
        return DjangoHttpResponse("Type d'export non supporté", status=400)

    return response


# ============================================
# PROGRAMME YEARS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_year_list(request):
    programme_years = ProgrammeYear.objects.select_related('programme').order_by('programme__title', 'year_number')
    programme = request.GET.get('programme', '')

    if programme:
        programme_years = programme_years.filter(programme_id=programme)

    paginator = Paginator(programme_years, 20)
    page = request.GET.get('page', 1)
    programme_years = paginator.get_page(page)

    context = {
        'page_title': 'Années de Programme',
        'programme_years': programme_years,
        'programmes': Programme.objects.all(),
        'filters': {'programme': programme},
    }

    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/programme_years/_programme_year_table.html', context)
    return render(request, 'superadmin/programme_years/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_year_create(request):
    if request.method == 'POST':
        programme_id = request.POST.get('programme')
        year_number = request.POST.get('year_number')
        if not programme_id or not year_number:
            messages.error(request, "Programme et numéro d'année obligatoires.")
            return redirect('superadmin:programme_year_create')

        ProgrammeYear.objects.create(
            programme_id=programme_id,
            year_number=year_number,
        )
        messages.success(request, "Année de programme créée!")
        return redirect('superadmin:programme_year_list')

    context = {
        'page_title': 'Nouvelle Année de Programme',
        'programmes': Programme.objects.all(),
    }
    return render(request, 'superadmin/programme_years/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_year_edit(request, pk):
    programme_year = get_object_or_404(ProgrammeYear, pk=pk)

    if request.method == 'POST':
        programme_year.programme_id = request.POST.get('programme', programme_year.programme_id)
        programme_year.year_number = request.POST.get('year_number', programme_year.year_number)
        programme_year.save()
        messages.success(request, f"Année de programme '{programme_year}' mise à jour!")
        return redirect('superadmin:programme_year_list')

    context = {
        'page_title': f'Modifier: {programme_year}',
        'programme_year': programme_year,
        'programmes': Programme.objects.all(),
    }
    return render(request, 'superadmin/programme_years/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_year_delete(request, pk):
    if request.method == 'POST':
        programme_year = get_object_or_404(ProgrammeYear, pk=pk)
        name = str(programme_year)
        programme_year.delete()
        messages.success(request, f"Année de programme '{name}' supprimée!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/programme_years/'})
    return redirect('superadmin:programme_year_list')


# ============================================
# PROGRAMME QUICK FACTS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def quick_fact_list(request):
    quick_facts = ProgrammeQuickFact.objects.select_related('programme').order_by('programme__title', 'order')
    programme = request.GET.get('programme', '')

    if programme:
        quick_facts = quick_facts.filter(programme_id=programme)

    paginator = Paginator(quick_facts, 20)
    page = request.GET.get('page', 1)
    quick_facts = paginator.get_page(page)

    context = {
        'page_title': 'Faits Rapides',
        'quick_facts': quick_facts,
        'programmes': Programme.objects.all(),
        'filters': {'programme': programme},
    }

    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/quick_facts/_quick_fact_table.html', context)
    return render(request, 'superadmin/quick_facts/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def quick_fact_create(request):
    if request.method == 'POST':
        programme_id = request.POST.get('programme')
        label = request.POST.get('label')
        value = request.POST.get('value')
        if not programme_id or not label or not value:
            messages.error(request, "Programme, label et valeur obligatoires.")
            return redirect('superadmin:quick_fact_create')

        ProgrammeQuickFact.objects.create(
            programme_id=programme_id,
            icon=request.POST.get('icon', 'academic_cap'),
            label=label,
            value=value,
            order=request.POST.get('order', 0),
        )
        messages.success(request, "Fait rapide créé!")
        return redirect('superadmin:quick_fact_list')

    context = {
        'page_title': 'Nouveau Fait Rapide',
        'programmes': Programme.objects.all(),
        'icon_choices': ProgrammeQuickFact.ICON_CHOICES,
    }
    return render(request, 'superadmin/quick_facts/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def quick_fact_edit(request, pk):
    quick_fact = get_object_or_404(ProgrammeQuickFact, pk=pk)

    if request.method == 'POST':
        quick_fact.programme_id = request.POST.get('programme', quick_fact.programme_id)
        quick_fact.icon = request.POST.get('icon', quick_fact.icon)
        quick_fact.label = request.POST.get('label', quick_fact.label)
        quick_fact.value = request.POST.get('value', quick_fact.value)
        quick_fact.order = request.POST.get('order', quick_fact.order)
        quick_fact.save()
        messages.success(request, f"Fait rapide '{quick_fact.label}' mis à jour!")
        return redirect('superadmin:quick_fact_list')

    context = {
        'page_title': f'Modifier: {quick_fact.label}',
        'quick_fact': quick_fact,
        'programmes': Programme.objects.all(),
        'icon_choices': ProgrammeQuickFact.ICON_CHOICES,
    }
    return render(request, 'superadmin/quick_facts/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def quick_fact_delete(request, pk):
    if request.method == 'POST':
        quick_fact = get_object_or_404(ProgrammeQuickFact, pk=pk)
        label = quick_fact.label
        quick_fact.delete()
        messages.success(request, f"Fait rapide '{label}' supprimé!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/quick_facts/'})
    return redirect('superadmin:quick_fact_list')


# ============================================
# PROGRAMME TABS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_tab_list(request):
    tabs = ProgrammeTab.objects.select_related('programme').order_by('programme__title', 'order')
    programme = request.GET.get('programme', '')

    if programme:
        tabs = tabs.filter(programme_id=programme)

    paginator = Paginator(tabs, 20)
    page = request.GET.get('page', 1)
    tabs = paginator.get_page(page)

    context = {
        'page_title': 'Onglets de Programme',
        'tabs': tabs,
        'programmes': Programme.objects.all(),
        'filters': {'programme': programme},
    }

    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/programme_tabs/_tab_table.html', context)
    return render(request, 'superadmin/programme_tabs/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_tab_create(request):
    if request.method == 'POST':
        programme_id = request.POST.get('programme')
        title = request.POST.get('title')
        if not programme_id or not title:
            messages.error(request, "Programme et titre obligatoires.")
            return redirect('superadmin:programme_tab_create')

        ProgrammeTab.objects.create(
            programme_id=programme_id,
            tab_type=request.POST.get('tab_type', 'custom'),
            title=title,
            slug=request.POST.get('slug', ''),
            order=request.POST.get('order', 0),
            is_active=request.POST.get('is_active') == 'on',
        )
        messages.success(request, "Onglet créé!")
        return redirect('superadmin:programme_tab_list')

    context = {
        'page_title': 'Nouvel Onglet',
        'programmes': Programme.objects.all(),
        'tab_type_choices': ProgrammeTab.TAB_TYPE_CHOICES,
    }
    return render(request, 'superadmin/programme_tabs/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_tab_edit(request, pk):
    tab = get_object_or_404(ProgrammeTab, pk=pk)

    if request.method == 'POST':
        tab.programme_id = request.POST.get('programme', tab.programme_id)
        tab.tab_type = request.POST.get('tab_type', tab.tab_type)
        tab.title = request.POST.get('title', tab.title)
        tab.slug = request.POST.get('slug', tab.slug)
        tab.order = request.POST.get('order', tab.order)
        tab.is_active = request.POST.get('is_active') == 'on'
        tab.save()
        messages.success(request, f"Onglet '{tab.title}' mis à jour!")
        return redirect('superadmin:programme_tab_list')

    context = {
        'page_title': f'Modifier: {tab.title}',
        'tab': tab,
        'programmes': Programme.objects.all(),
        'tab_type_choices': ProgrammeTab.TAB_TYPE_CHOICES,
    }
    return render(request, 'superadmin/programme_tabs/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_tab_delete(request, pk):
    if request.method == 'POST':
        tab = get_object_or_404(ProgrammeTab, pk=pk)
        title = tab.title
        tab.delete()
        messages.success(request, f"Onglet '{title}' supprimé!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/programme_tabs/'})
    return redirect('superadmin:programme_tab_list')


# ============================================
# PROGRAMME SECTIONS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_section_list(request):
    sections = ProgrammeSection.objects.select_related('tab__programme').order_by('tab__programme__title', 'order')
    programme = request.GET.get('programme', '')

    if programme:
        sections = sections.filter(tab__programme_id=programme)

    paginator = Paginator(sections, 20)
    page = request.GET.get('page', 1)
    sections = paginator.get_page(page)

    context = {
        'page_title': 'Sections de Programme',
        'sections': sections,
        'programmes': Programme.objects.all(),
        'filters': {'programme': programme},
    }

    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/programme_sections/_section_table.html', context)
    return render(request, 'superadmin/programme_sections/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_section_create(request):
    if request.method == 'POST':
        tab_id = request.POST.get('tab')
        section_type = request.POST.get('section_type')
        if not tab_id or not section_type:
            messages.error(request, "Onglet et type de section obligatoires.")
            return redirect('superadmin:programme_section_create')

        ProgrammeSection.objects.create(
            tab_id=tab_id,
            section_type=section_type,
            title=request.POST.get('title', ''),
            content=request.POST.get('content', ''),
            order=request.POST.get('order', 0),
        )
        messages.success(request, "Section créée!")
        return redirect('superadmin:programme_section_list')

    context = {
        'page_title': 'Nouvelle Section',
        'tabs': ProgrammeTab.objects.select_related('programme').all(),
        'section_type_choices': ProgrammeSection.SECTION_TYPE_CHOICES,
    }
    return render(request, 'superadmin/programme_sections/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_section_edit(request, pk):
    section = get_object_or_404(ProgrammeSection, pk=pk)

    if request.method == 'POST':
        section.tab_id = request.POST.get('tab', section.tab_id)
        section.section_type = request.POST.get('section_type', section.section_type)
        section.title = request.POST.get('title', section.title)
        section.content = request.POST.get('content', section.content)
        section.order = request.POST.get('order', section.order)
        section.save()
        messages.success(request, f"Section '{section.title or 'Sans titre'}' mise à jour!")
        return redirect('superadmin:programme_section_list')

    context = {
        'page_title': f'Modifier: {section.title or "Section"}',
        'section': section,
        'tabs': ProgrammeTab.objects.select_related('programme').all(),
        'section_type_choices': ProgrammeSection.SECTION_TYPE_CHOICES,
    }
    return render(request, 'superadmin/programme_sections/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_section_delete(request, pk):
    if request.method == 'POST':
        section = get_object_or_404(ProgrammeSection, pk=pk)
        title = section.title or 'Section'
        section.delete()
        messages.success(request, f"Section '{title}' supprimée!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/programme_sections/'})
    return redirect('superadmin:programme_section_list')


# ============================================
# COMPETENCE BLOCKS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def competence_block_list(request):
    blocks = CompetenceBlock.objects.select_related('programme').order_by('programme__title', 'order')
    programme = request.GET.get('programme', '')

    if programme:
        blocks = blocks.filter(programme_id=programme)

    paginator = Paginator(blocks, 20)
    page = request.GET.get('page', 1)
    blocks = paginator.get_page(page)

    context = {
        'page_title': 'Blocs de Compétences',
        'blocks': blocks,
        'programmes': Programme.objects.all(),
        'filters': {'programme': programme},
    }

    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/competence_blocks/_block_table.html', context)
    return render(request, 'superadmin/competence_blocks/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def competence_block_create(request):
    if request.method == 'POST':
        programme_id = request.POST.get('programme')
        title = request.POST.get('title')
        if not programme_id or not title:
            messages.error(request, "Programme et titre obligatoires.")
            return redirect('superadmin:competence_block_create')

        CompetenceBlock.objects.create(
            programme_id=programme_id,
            title=title,
            description=request.POST.get('description', ''),
            order=request.POST.get('order', 0),
        )
        messages.success(request, "Bloc de compétences créé!")
        return redirect('superadmin:competence_block_list')

    context = {
        'page_title': 'Nouveau Bloc de Compétences',
        'programmes': Programme.objects.all(),
    }
    return render(request, 'superadmin/competence_blocks/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def competence_block_edit(request, pk):
    block = get_object_or_404(CompetenceBlock, pk=pk)

    if request.method == 'POST':
        block.programme_id = request.POST.get('programme', block.programme_id)
        block.title = request.POST.get('title', block.title)
        block.description = request.POST.get('description', block.description)
        block.order = request.POST.get('order', block.order)
        block.save()
        messages.success(request, f"Bloc '{block.title}' mis à jour!")
        return redirect('superadmin:competence_block_list')

    context = {
        'page_title': f'Modifier: {block.title}',
        'block': block,
        'programmes': Programme.objects.all(),
    }
    return render(request, 'superadmin/competence_blocks/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def competence_block_delete(request, pk):
    if request.method == 'POST':
        block = get_object_or_404(CompetenceBlock, pk=pk)
        title = block.title
        block.delete()
        messages.success(request, f"Bloc '{title}' supprimé!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/competence_blocks/'})
    return redirect('superadmin:competence_block_list')


# ============================================
# COMPETENCE ITEMS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def competence_item_list(request):
    items = CompetenceItem.objects.select_related('block__programme').order_by('block__programme__title', 'order')
    programme = request.GET.get('programme', '')

    if programme:
        items = items.filter(block__programme_id=programme)

    paginator = Paginator(items, 20)
    page = request.GET.get('page', 1)
    items = paginator.get_page(page)

    context = {
        'page_title': 'Items de Compétences',
        'items': items,
        'programmes': Programme.objects.all(),
        'filters': {'programme': programme},
    }

    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/competence_items/_item_table.html', context)
    return render(request, 'superadmin/competence_items/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def competence_item_create(request):
    if request.method == 'POST':
        block_id = request.POST.get('block')
        title = request.POST.get('title')
        if not block_id or not title:
            messages.error(request, "Bloc et titre obligatoires.")
            return redirect('superadmin:competence_item_create')

        CompetenceItem.objects.create(
            block_id=block_id,
            title=title,
            description=request.POST.get('description', ''),
            order=request.POST.get('order', 0),
        )
        messages.success(request, "Item de compétence créé!")
        return redirect('superadmin:competence_item_list')

    context = {
        'page_title': 'Nouvel Item de Compétence',
        'blocks': CompetenceBlock.objects.select_related('programme').all(),
    }
    return render(request, 'superadmin/competence_items/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def competence_item_edit(request, pk):
    item = get_object_or_404(CompetenceItem, pk=pk)

    if request.method == 'POST':
        item.block_id = request.POST.get('block', item.block_id)
        item.title = request.POST.get('title', item.title)
        item.description = request.POST.get('description', item.description)
        item.order = request.POST.get('order', item.order)
        item.save()
        messages.success(request, f"Item '{item.title}' mis à jour!")
        return redirect('superadmin:competence_item_list')

    context = {
        'page_title': f'Modifier: {item.title}',
        'item': item,
        'blocks': CompetenceBlock.objects.select_related('programme').all(),
    }
    return render(request, 'superadmin/competence_items/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def competence_item_delete(request, pk):
    if request.method == 'POST':
        item = get_object_or_404(CompetenceItem, pk=pk)
        title = item.title
        item.delete()
        messages.success(request, f"Item '{title}' supprimé!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/competence_items/'})
    return redirect('superadmin:competence_item_list')


# ============================================
# REQUIRED DOCUMENTS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def required_document_list(request):
    documents = RequiredDocument.objects.all().order_by('name')
    paginator = Paginator(documents, 20)
    page = request.GET.get('page', 1)
    documents = paginator.get_page(page)

    context = {
        'page_title': 'Documents Requis',
        'documents': documents,
    }

    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/required_documents/_document_table.html', context)
    return render(request, 'superadmin/required_documents/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def required_document_create(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        if not name:
            messages.error(request, "Nom obligatoire.")
            return redirect('superadmin:required_document_create')

        RequiredDocument.objects.create(
            name=name,
            description=request.POST.get('description', ''),
            is_mandatory=request.POST.get('is_mandatory') == 'on',
        )
        messages.success(request, "Document requis créé!")
        return redirect('superadmin:required_document_list')

    context = {
        'page_title': 'Nouveau Document Requis',
    }
    return render(request, 'superadmin/required_documents/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def required_document_edit(request, pk):
    document = get_object_or_404(RequiredDocument, pk=pk)

    if request.method == 'POST':
        document.name = request.POST.get('name', document.name)
        document.description = request.POST.get('description', document.description)
        document.is_mandatory = request.POST.get('is_mandatory') == 'on'
        document.save()
        messages.success(request, f"Document '{document.name}' mis à jour!")
        return redirect('superadmin:required_document_list')

    context = {
        'page_title': f'Modifier: {document.name}',
        'document': document,
    }
    return render(request, 'superadmin/required_documents/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def required_document_delete(request, pk):
    if request.method == 'POST':
        document = get_object_or_404(RequiredDocument, pk=pk)
        name = document.name
        document.delete()
        messages.success(request, f"Document '{name}' supprimé!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/required_documents/'})
    return redirect('superadmin:required_document_list')


# ============================================
# PROGRAMME REQUIRED DOCUMENTS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_required_document_list(request):
    programme_documents = ProgrammeRequiredDocument.objects.select_related('programme', 'document').order_by('programme__title', 'document__name')
    programme = request.GET.get('programme', '')

    if programme:
        programme_documents = programme_documents.filter(programme_id=programme)

    paginator = Paginator(programme_documents, 20)
    page = request.GET.get('page', 1)
    programme_documents = paginator.get_page(page)

    context = {
        'page_title': 'Documents Requis par Programme',
        'programme_documents': programme_documents,
        'programmes': Programme.objects.all(),
        'filters': {'programme': programme},
    }

    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/programme_required_documents/_programme_document_table.html', context)
    return render(request, 'superadmin/programme_required_documents/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_required_document_create(request):
    if request.method == 'POST':
        programme_id = request.POST.get('programme')
        document_id = request.POST.get('document')
        if not programme_id or not document_id:
            messages.error(request, "Programme et document obligatoires.")
            return redirect('superadmin:programme_required_document_create')

        ProgrammeRequiredDocument.objects.create(
            programme_id=programme_id,
            document_id=document_id,
        )
        messages.success(request, "Association créée!")
        return redirect('superadmin:programme_required_document_list')

    context = {
        'page_title': 'Nouvelle Association Document-Programme',
        'programmes': Programme.objects.all(),
        'documents': RequiredDocument.objects.all(),
    }
    return render(request, 'superadmin/programme_required_documents/form.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def programme_required_document_delete(request, pk):
    if request.method == 'POST':
        programme_document = get_object_or_404(ProgrammeRequiredDocument, pk=pk)
        name = f"{programme_document.programme.title} - {programme_document.document.name}"
        programme_document.delete()
        messages.success(request, f"Association '{name}' supprimée!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/programme_required_documents/'})
    return redirect('superadmin:programme_required_document_list')


# ============================================
# COMMUNITY CATEGORIES
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def community_category_list(request):
    categories = CommunityCategory.objects.annotate(
        topics_count=Count('topics', filter=Q(topics__is_deleted=False, topics__is_published=True)),
        subscribers_count=Count('subscribers')
    ).order_by('name')
    return render(request, 'superadmin/community/categories/list.html', {'page_title': 'Catégories Communauté', 'categories': categories})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def community_category_create(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            CommunityCategory.objects.create(
                name=name,
                description=request.POST.get('description', ''),
                is_active=request.POST.get('is_active') == 'on'
            )
            messages.success(request, f"Catégorie '{name}' créée!")
            return redirect('superadmin:community_category_list')
        messages.error(request, "Le nom est obligatoire.")
    return render(request, 'superadmin/community/categories/form.html', {'page_title': 'Nouvelle Catégorie'})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def community_category_edit(request, pk):
    category = get_object_or_404(CommunityCategory, pk=pk)
    if request.method == 'POST':
        category.name = request.POST.get('name', category.name).strip()
        category.description = request.POST.get('description', '')
        category.is_active = request.POST.get('is_active') == 'on'
        category.save()
        messages.success(request, f"Catégorie '{category.name}' mise à jour!")
        return redirect('superadmin:community_category_list')
    return render(request, 'superadmin/community/categories/form.html', {'page_title': f'Modifier: {category.name}', 'category': category})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def community_category_delete(request, pk):
    if request.method == 'POST':
        category = get_object_or_404(CommunityCategory, pk=pk)
        category.delete()
        messages.success(request, "Catégorie supprimée!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/community/categories/'})
    return redirect('superadmin:community_category_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_community_category(request, pk):
    category = get_object_or_404(CommunityCategory, pk=pk)
    category.is_active = not category.is_active
    category.save()
    status = "activée" if category.is_active else "désactivée"
    if request.headers.get('HX-Request'):
        return HttpResponse(f'<span class="badge">{"Actif" if category.is_active else "Inactif"}</span>', headers={'HX-Trigger': '{"showToast": "Catégorie ' + status + '"}'})
    messages.success(request, f"Catégorie {status}!")
    return redirect('superadmin:community_category_list')


# ============================================
# COMMUNITY TOPICS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def community_topic_list(request):
    topics = Topic.objects.select_related('author', 'category').prefetch_related('answers').order_by('-last_activity_at')
    search = request.GET.get('search', '')
    category = request.GET.get('category', '')
    status = request.GET.get('status', '')

    if search:
        topics = topics.filter(Q(title__icontains=search) | Q(content__icontains=search))
    if category:
        topics = topics.filter(category_id=category)
    if status == 'published':
        topics = topics.filter(is_published=True, is_deleted=False)
    elif status == 'deleted':
        topics = topics.filter(is_deleted=True)

    paginator = Paginator(topics, 20)
    page = request.GET.get('page', 1)
    topics = paginator.get_page(page)

    context = {
        'page_title': 'Sujets Communauté',
        'topics': topics,
        'categories': CommunityCategory.objects.all(),
        'filters': {'search': search, 'category': category, 'status': status},
    }

    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/community/topics/_topic_table.html', context)
    return render(request, 'superadmin/community/topics/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def community_topic_detail(request, pk):
    topic = get_object_or_404(Topic.objects.select_related('author', 'category', 'accepted_answer'), pk=pk)
    answers = Answer.objects.filter(topic=topic, is_deleted=False).select_related('author').order_by('created_at')
    context = {
        'page_title': topic.title,
        'topic': topic,
        'answers': answers,
    }
    return render(request, 'superadmin/community/topics/detail.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def community_topic_edit(request, pk):
    topic = get_object_or_404(Topic, pk=pk)
    if request.method == 'POST':
        topic.title = request.POST.get('title', topic.title)
        topic.category_id = request.POST.get('category', topic.category_id)
        topic.is_published = request.POST.get('is_published') == 'on'
        topic.is_locked = request.POST.get('is_locked') == 'on'
        topic.is_pinned = request.POST.get('is_pinned') == 'on'
        topic.save()
        messages.success(request, f"Sujet '{topic.title}' mis à jour!")
        return redirect('superadmin:community_topic_list')
    return render(request, 'superadmin/community/topics/form.html', {
        'page_title': f'Modifier: {topic.title}',
        'topic': topic,
        'categories': CommunityCategory.objects.all()
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def community_topic_delete(request, pk):
    if request.method == 'POST':
        topic = get_object_or_404(Topic, pk=pk)
        title = topic.title
        topic.soft_delete()
        messages.success(request, f"Sujet '{title}' supprimé!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/community/topics/'})
    return redirect('superadmin:community_topic_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_community_topic(request, pk):
    topic = get_object_or_404(Topic, pk=pk)
    action = request.GET.get('action', 'publish')
    if action == 'publish':
        topic.is_published = not topic.is_published
        status = "publié" if topic.is_published else "dépublié"
    elif action == 'lock':
        topic.is_locked = not topic.is_locked
        status = "verrouillé" if topic.is_locked else "déverrouillé"
    elif action == 'pin':
        topic.is_pinned = not topic.is_pinned
        status = "épinglé" if topic.is_pinned else "désépinglé"
    topic.save()
    if request.headers.get('HX-Request'):
        return HttpResponse(f'<span class="badge">{status}</span>', headers={'HX-Trigger': f'{{"showToast": "Sujet {status}"}}'})
    messages.success(request, f"Sujet {status}!")
    return redirect('superadmin:community_topic_list')


# ============================================
# COMMUNITY ANSWERS
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def community_answer_list(request):
    answers = Answer.objects.select_related('author', 'topic').order_by('-created_at')
    search = request.GET.get('search', '')
    topic = request.GET.get('topic', '')

    if search:
        answers = answers.filter(content__icontains=search)
    if topic:
        answers = answers.filter(topic_id=topic)

    paginator = Paginator(answers, 20)
    page = request.GET.get('page', 1)
    answers = paginator.get_page(page)

    context = {
        'page_title': 'Réponses Communauté',
        'answers': answers,
        'topics': Topic.objects.all(),
        'filters': {'search': search, 'topic': topic},
    }

    if request.headers.get('HX-Request'):
        return render(request, 'superadmin/community/answers/_answer_table.html', context)
    return render(request, 'superadmin/community/answers/list.html', context)


@user_passes_test(superuser_required, login_url='/accounts/login/')
def community_answer_detail(request, pk):
    answer = get_object_or_404(Answer.objects.select_related('author', 'topic'), pk=pk)
    return render(request, 'superadmin/community/answers/detail.html', {'page_title': f'Réponse #{answer.pk}', 'answer': answer})


@user_passes_test(superuser_required, login_url='/accounts/login/')
def community_answer_edit(request, pk):
    answer = get_object_or_404(Answer, pk=pk)
    if request.method == 'POST':
        answer.content = request.POST.get('content', answer.content)
        answer.save()
        messages.success(request, f"Réponse #{answer.pk} mise à jour!")
        return redirect('superadmin:community_answer_list')
    return render(request, 'superadmin/community/answers/form.html', {
        'page_title': f'Modifier Réponse #{answer.pk}',
        'answer': answer
    })


@user_passes_test(superuser_required, login_url='/accounts/login/')
def community_answer_delete(request, pk):
    if request.method == 'POST':
        answer = get_object_or_404(Answer, pk=pk)
        answer_id = answer.pk
        answer.is_deleted = True
        answer.save()
        messages.success(request, f"Réponse #{answer_id} supprimée!")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=200, headers={'HX-Redirect': '/superadmin/community/answers/'})
    return redirect('superadmin:community_answer_list')


@user_passes_test(superuser_required, login_url='/accounts/login/')
def toggle_community_answer(request, pk):
    answer = get_object_or_404(Answer, pk=pk)
    action = request.GET.get('action', 'accept')
    if action == 'accept':
        # Remove previous accepted answer
        Answer.objects.filter(topic=answer.topic, topic__accepted_answer__isnull=False).update(topic__accepted_answer=None)
        answer.topic.accepted_answer = answer
        answer.topic.save()
        status = "acceptée"
    elif action == 'delete':
        answer.is_deleted = not answer.is_deleted
        status = "supprimée" if answer.is_deleted else "restaurée"
        answer.save()
    if request.headers.get('HX-Request'):
        return HttpResponse(f'<span class="badge">{status}</span>', headers={'HX-Trigger': f'{{"showToast": "Réponse {status}"}}'})
    messages.success(request, f"Réponse {status}!")
    return redirect('superadmin:community_answer_list')

