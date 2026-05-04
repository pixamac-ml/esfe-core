import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from academics.models import AcademicClass
from .forms import (
    AppointmentForm,
    DocumentReceiptForm,
    RegistryEntryForm,
    SecretaryTaskForm,
    VisitorLogForm,
)
from .models import Appointment, DocumentReceipt, RegistryEntry, SecretaryTask, VisitorLog
from .permissions import ensure_secretary_access
from .selectors import (
    get_appointments_queryset,
    get_documents_queryset,
    get_registry_queryset,
    get_tasks_queryset,
    get_visits_queryset,
)
from .services import (
    archive_document,
    archive_registry_entry,
    complete_appointment,
    complete_task,
    close_visit,
    create_appointment,
    create_registry_entry,
    create_task,
    get_secretary_dashboard_data,
    get_secretary_recent_messages,
    get_student_snapshot,
    mark_registry_processed,
    register_document,
    register_visitor,
    search_academic_classes,
    search_students,
)


def _paginate(request, queryset, per_page=20):
    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get("page")
    return paginator.get_page(page_number)


def _common_filters(request):
    return {
        "q": request.GET.get("q", "").strip(),
        "status": request.GET.get("status", "").strip(),
        "archived": False,
        "active_only": True,
    }


def _is_htmx(request):
    return request.headers.get("HX-Request") == "true"


def _modal_close_response():
    response = HttpResponse("", content_type="text/html")
    response["HX-Trigger"] = json.dumps(
        {
            "secretary-modal-close": True,
            "secretary-dashboard-refresh": True,
        }
    )
    return response


def _refresh_response():
    response = HttpResponse("", content_type="text/html")
    response["HX-Trigger"] = json.dumps({"secretary-dashboard-refresh": True})
    return response


def _render_create_modal_or_page(request, modal_template, page_template, context):
    if _is_htmx(request):
        return render(request, modal_template, context)
    return render(request, page_template, context)


@login_required
def secretary_dashboard(request):
    ensure_secretary_access(request.user)
    context = get_secretary_dashboard_data(request.user)
    context["student_query"] = request.GET.get("student_q", "").strip()
    if context["student_query"]:
        context["student_results"] = search_students(context["student_query"])[:10]
    else:
        context["student_results"] = []
    context["quick_registry_form"] = RegistryEntryForm()
    context["quick_appointment_form"] = AppointmentForm()
    context["quick_visitor_form"] = VisitorLogForm()
    context["quick_document_form"] = DocumentReceiptForm()
    context["quick_task_form"] = SecretaryTaskForm()
    return render(request, "secretary/dashboard.html", context)


@login_required
def registry_list(request):
    ensure_secretary_access(request.user)
    queryset = get_registry_queryset(_common_filters(request))
    return render(
        request,
        "secretary/registry_list.html",
        {
            "page_obj": _paginate(request, queryset),
            "filters": _common_filters(request),
        },
    )


@login_required
def registry_create(request):
    ensure_secretary_access(request.user)
    form = RegistryEntryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        create_registry_entry(created_by=request.user, **form.cleaned_data)
        messages.success(request, "Entree de registre enregistree.")
        if _is_htmx(request):
            return _modal_close_response()
        return redirect("secretary:registry_list")
    return _render_create_modal_or_page(
        request,
        "secretary/modals/form_modal.html",
        "secretary/registry_form.html",
        {
            "form": form,
            "page_title": "Nouvelle entree de registre",
            "modal_kicker": "Registre",
            "modal_description": "Ajouter une entree sans quitter le tableau de bord.",
            "submit_label": "Enregistrer l'entree",
            "return_url": "secretary:registry_list",
        },
    )


@login_required
def registry_mark_processed(request, pk):
    ensure_secretary_access(request.user)
    entry = get_object_or_404(RegistryEntry, pk=pk)
    mark_registry_processed(entry)
    messages.success(request, "Entree marquee comme traitee.")
    if _is_htmx(request):
        return _refresh_response()
    return redirect("secretary:registry_list")


@login_required
def registry_archive(request, pk):
    ensure_secretary_access(request.user)
    entry = get_object_or_404(RegistryEntry, pk=pk)
    archive_registry_entry(entry)
    messages.success(request, "Entree archivee.")
    if _is_htmx(request):
        return _refresh_response()
    return redirect("secretary:registry_list")


@login_required
def appointment_list(request):
    ensure_secretary_access(request.user)
    filters = _common_filters(request)
    filters["date_from"] = request.GET.get("date_from") or None
    filters["date_to"] = request.GET.get("date_to") or None
    queryset = get_appointments_queryset(filters)
    return render(
        request,
        "secretary/appointment_list.html",
        {
            "page_obj": _paginate(request, queryset),
            "filters": filters,
        },
    )


@login_required
def appointment_create(request):
    ensure_secretary_access(request.user)
    form = AppointmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        create_appointment(created_by=request.user, **form.cleaned_data)
        messages.success(request, "Rendez-vous cree.")
        if _is_htmx(request):
            return _modal_close_response()
        return redirect("secretary:appointment_list")
    return _render_create_modal_or_page(
        request,
        "secretary/modals/form_modal.html",
        "secretary/appointment_form.html",
        {
            "form": form,
            "page_title": "Nouveau rendez-vous",
            "modal_kicker": "Agenda",
            "modal_description": "Planifier un rendez-vous sans sortir du pilotage.",
            "submit_label": "Enregistrer le rendez-vous",
            "return_url": "secretary:appointment_list",
        },
    )


@login_required
def appointment_complete(request, pk):
    ensure_secretary_access(request.user)
    appointment = get_object_or_404(Appointment, pk=pk)
    complete_appointment(appointment)
    messages.success(request, "Rendez-vous marque comme termine.")
    if _is_htmx(request):
        return _refresh_response()
    return redirect("secretary:appointment_list")


@login_required
def visitor_list(request):
    ensure_secretary_access(request.user)
    queryset = get_visits_queryset(_common_filters(request))
    return render(
        request,
        "secretary/visitor_list.html",
        {
            "page_obj": _paginate(request, queryset),
            "filters": _common_filters(request),
        },
    )


@login_required
def visitor_complete(request, pk):
    ensure_secretary_access(request.user)
    visitor = get_object_or_404(VisitorLog, pk=pk)
    close_visit(visitor)
    messages.success(request, "Visite cloturee.")
    if _is_htmx(request):
        return _refresh_response()
    return redirect("secretary:visitor_list")


@login_required
def visitor_create(request):
    ensure_secretary_access(request.user)
    form = VisitorLogForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        register_visitor(created_by=request.user, **form.cleaned_data)
        messages.success(request, "Visite enregistree.")
        if _is_htmx(request):
            return _modal_close_response()
        return redirect("secretary:visitor_list")
    return _render_create_modal_or_page(
        request,
        "secretary/modals/form_modal.html",
        "secretary/visitor_form.html",
        {
            "form": form,
            "page_title": "Nouvelle visite",
            "modal_kicker": "Accueil",
            "modal_description": "Enregistrer un visiteur et son lien avec le service.",
            "submit_label": "Enregistrer la visite",
            "return_url": "secretary:visitor_list",
        },
    )


@login_required
def document_receipt_list(request):
    ensure_secretary_access(request.user)
    queryset = get_documents_queryset(_common_filters(request))
    return render(
        request,
        "secretary/document_receipt_list.html",
        {
            "page_obj": _paginate(request, queryset),
            "filters": _common_filters(request),
        },
    )


@login_required
def document_receipt_create(request):
    ensure_secretary_access(request.user)
    form = DocumentReceiptForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        register_document(received_by=request.user, **form.cleaned_data)
        messages.success(request, "Document enregistre.")
        if _is_htmx(request):
            return _modal_close_response()
        return redirect("secretary:document_receipt_list")
    return _render_create_modal_or_page(
        request,
        "secretary/modals/form_modal.html",
        "secretary/document_receipt_form.html",
        {
            "form": form,
            "page_title": "Nouveau document",
            "modal_kicker": "Pieces",
            "modal_description": "Recevoir un document avec sa trace administrative.",
            "submit_label": "Enregistrer le document",
            "return_url": "secretary:document_receipt_list",
        },
    )


@login_required
def document_receipt_archive(request, pk):
    ensure_secretary_access(request.user)
    document = get_object_or_404(DocumentReceipt, pk=pk)
    archive_document(document)
    messages.success(request, "Document archive.")
    if _is_htmx(request):
        return _refresh_response()
    return redirect("secretary:document_receipt_list")


@login_required
def task_list(request):
    ensure_secretary_access(request.user)
    queryset = get_tasks_queryset(_common_filters(request))
    return render(
        request,
        "secretary/task_list.html",
        {
            "page_obj": _paginate(request, queryset),
            "filters": _common_filters(request),
        },
    )


@login_required
def task_create(request):
    ensure_secretary_access(request.user)
    form = SecretaryTaskForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        create_task(created_by=request.user, **form.cleaned_data)
        messages.success(request, "Tache creee.")
        if _is_htmx(request):
            return _modal_close_response()
        return redirect("secretary:task_list")
    return _render_create_modal_or_page(
        request,
        "secretary/modals/form_modal.html",
        "secretary/task_form.html",
        {
            "form": form,
            "page_title": "Nouvelle tache",
            "modal_kicker": "Suivi",
            "modal_description": "Créer une tâche de pilotage sans quitter la page.",
            "submit_label": "Enregistrer la tache",
            "return_url": "secretary:task_list",
        },
    )


@login_required
def task_complete(request, pk):
    ensure_secretary_access(request.user)
    task = get_object_or_404(SecretaryTask, pk=pk)
    complete_task(task)
    messages.success(request, "Tache marquee comme terminee.")
    if _is_htmx(request):
        return _refresh_response()
    return redirect("secretary:task_list")


@login_required
def student_snapshot_view(request, student_id):
    ensure_secretary_access(request.user)
    return JsonResponse(get_student_snapshot(student_id))


@login_required
def htmx_student_results(request):
    ensure_secretary_access(request.user)
    query = request.GET.get("q", "").strip()
    students = search_students(query)[:12] if query else []
    return render(
        request,
        "secretary/partials/student_results.html",
        {"students": students, "query": query},
    )


@login_required
def htmx_class_results(request):
    ensure_secretary_access(request.user)
    query = request.GET.get("q", "").strip()
    classes = search_academic_classes(query)[:12] if query else []
    return render(
        request,
        "secretary/partials/class_results.html",
        {"classes": classes, "query": query},
    )


@login_required
def htmx_registry_results(request):
    ensure_secretary_access(request.user)
    filters = _common_filters(request)
    entries = get_registry_queryset(filters)[:12]
    return render(
        request,
        "secretary/partials/registry_results.html",
        {"entries": entries, "query": filters.get("q", "")},
    )


@login_required
def htmx_appointment_results(request):
    ensure_secretary_access(request.user)
    filters = _common_filters(request)
    appointments = get_appointments_queryset(filters)[:12]
    return render(
        request,
        "secretary/partials/appointment_results.html",
        {"appointments": appointments, "query": filters.get("q", "")},
    )


@login_required
def htmx_document_results(request):
    ensure_secretary_access(request.user)
    filters = _common_filters(request)
    receipts = get_documents_queryset(filters)[:12]
    return render(
        request,
        "secretary/partials/document_results.html",
        {"receipts": receipts, "query": filters.get("q", "")},
    )


@login_required
def htmx_task_results(request):
    ensure_secretary_access(request.user)
    filters = _common_filters(request)
    tasks = get_tasks_queryset(filters)[:12]
    return render(
        request,
        "secretary/partials/task_results.html",
        {"tasks": tasks, "query": filters.get("q", "")},
    )


@login_required
def htmx_messages_panel(request):
    ensure_secretary_access(request.user)
    messages_list = get_secretary_recent_messages(request.user, limit=8)
    return render(
        request,
        "secretary/partials/messages_panel.html",
        {"recent_messages": messages_list},
    )


@login_required
def htmx_auto_assign(request):
    ensure_secretary_access(request.user)
    return HttpResponse(
        '<div class="message">Affectation automatique prete pour integration metier future.</div>'
    )
