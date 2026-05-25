from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from academics.models import AcademicYear
from .forms import TransferRequestForm
from .models import AcademicCorrectionRequest, AcademicReEnrollment, BranchAcademicCycle
from .permissions import can_handle_correction, can_manage_reenrollment
from .selectors import ensure_user_can_see_branch, get_dg_cycle_overview
from .services.activation_service import activate_academic_year_for_branch, open_registration_for_year
from .services.closure_service import close_branch_cycle, start_deliberation
from .services.correction_service import resolve_correction_request
from .services.readiness_service import generate_closure_report
from .services.reenrollment_service import start_reenrollment, submit_reenrollment


@login_required
def dg_overview(request):
    return render(request, "academic_cycle/dg/overview.html", {"overview": get_dg_cycle_overview(request.user)})


@login_required
def branch_overview(request, pk):
    cycle = get_object_or_404(BranchAcademicCycle.objects.select_related("branch", "academic_year"), pk=pk)
    if not ensure_user_can_see_branch(request.user, cycle.branch):
        raise PermissionDenied
    return render(request, "academic_cycle/staff/branch_overview.html", {"cycle": cycle})


@login_required
def branch_readiness(request, pk):
    cycle = get_object_or_404(BranchAcademicCycle.objects.select_related("branch", "academic_year"), pk=pk)
    if not ensure_user_can_see_branch(request.user, cycle.branch):
        raise PermissionDenied
    report = generate_closure_report(cycle, actor=request.user)
    return render(request, "academic_cycle/staff/readiness.html", {"cycle": cycle, "report": report})


@login_required
@require_POST
def generate_report(request, pk):
    cycle = get_object_or_404(BranchAcademicCycle, pk=pk)
    generate_closure_report(cycle, actor=request.user)
    messages.success(request, "Rapport de readiness genere.")
    return redirect("academic_cycle:branch_readiness", pk=cycle.pk)


@login_required
@require_POST
def start_deliberation_view(request, pk):
    cycle = get_object_or_404(BranchAcademicCycle, pk=pk)
    start_deliberation(cycle, request.user)
    messages.success(request, "Deliberation demarree pour cette annexe.")
    return redirect("academic_cycle:branch_overview", pk=cycle.pk)


@login_required
@require_POST
def close_branch_view(request, pk):
    cycle = get_object_or_404(BranchAcademicCycle, pk=pk)
    try:
        close_branch_cycle(cycle, request.user)
        messages.success(request, "Annexe cloturee.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("academic_cycle:branch_overview", pk=cycle.pk)


@login_required
@require_POST
def open_registration_view(request, pk):
    source_cycle = get_object_or_404(BranchAcademicCycle, pk=pk)
    target_year_id = request.POST.get("target_year")
    target_year = get_object_or_404(AcademicYear, pk=target_year_id)
    target_cycle = open_registration_for_year(source_cycle.branch, target_year, request.user)
    messages.success(request, "Reinscriptions ouvertes pour l'annexe.")
    return redirect("academic_cycle:branch_overview", pk=target_cycle.pk)


@login_required
@require_POST
def activate_year_view(request, pk):
    source_cycle = get_object_or_404(BranchAcademicCycle, pk=pk)
    target_year_id = request.POST.get("target_year")
    target_year = get_object_or_404(AcademicYear, pk=target_year_id)
    target_cycle = activate_academic_year_for_branch(source_cycle.branch, target_year, request.user)
    messages.success(request, "Nouvelle annee activee pour l'annexe.")
    return redirect("academic_cycle:branch_overview", pk=target_cycle.pk)


@login_required
def student_pre_rentree(request):
    student = getattr(request.user, "student_profile", None)
    reenrollments = AcademicReEnrollment.objects.filter(student=student).select_related("target_academic_year", "target_class") if student else []
    return render(request, "academic_cycle/student/pre_rentree.html", {"student": student, "reenrollments": reenrollments})


@login_required
def student_reenrollment(request, token):
    reenrollment = get_object_or_404(AcademicReEnrollment, token=token)
    if request.user != reenrollment.student.user and not can_manage_reenrollment(request.user, reenrollment.branch):
        raise PermissionDenied
    if request.method == "POST":
        if reenrollment.status == AcademicReEnrollment.STATUS_PREPARED:
            start_reenrollment(reenrollment, request.user)
        submit_reenrollment(reenrollment, request.POST.dict(), request.user)
        messages.success(request, "Reinscription soumise. Paiement minimum attendu.")
        return redirect("academic_cycle:student_pre_rentree")
    return render(request, "academic_cycle/student/reenrollment.html", {"reenrollment": reenrollment})


@login_required
def student_transfer_request(request):
    student = getattr(request.user, "student_profile", None)
    if request.method == "POST":
        form = TransferRequestForm(request.POST)
        if form.is_valid() and student:
            transfer = form.save(commit=False)
            transfer.student = student
            enrollment = student.current_academic_enrollment
            transfer.source_academic_year = enrollment.academic_year
            transfer.target_academic_year = form.cleaned_data.get("requested_class").academic_year if form.cleaned_data.get("requested_class") else enrollment.academic_year
            transfer.source_branch = enrollment.branch
            transfer.source_class = enrollment.academic_class
            transfer.status = transfer.STATUS_SUBMITTED
            transfer.save()
            messages.success(request, "Demande de transfert soumise.")
            return redirect("academic_cycle:student_pre_rentree")
    else:
        form = TransferRequestForm()
    return render(request, "academic_cycle/student/transfer_request.html", {"form": form})


@login_required
def correction_list(request):
    qs = AcademicCorrectionRequest.objects.select_related("student", "branch", "academic_year")
    return render(request, "academic_cycle/it/corrections.html", {"corrections": qs})


@login_required
@require_POST
def resolve_correction_view(request, pk):
    correction = get_object_or_404(AcademicCorrectionRequest, pk=pk)
    if not can_handle_correction(request.user, correction):
        raise PermissionDenied
    resolve_correction_request(correction, request.user, request.POST.get("resolution_note", "Correction resolue."))
    messages.success(request, "Correction resolue.")
    return redirect("academic_cycle:correction_list")
