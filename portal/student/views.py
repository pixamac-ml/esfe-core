from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from django.db.models import Prefetch

from academics.models import AcademicEnrollment, EC, ECChapter
from portal.permissions import role_required

from .services import get_student_dashboard_shell
from .widgets.profile import get_profile_widget
from .widgets.academics import get_academics_widget
from .widgets.finance import get_finance_widget
from .widgets.notifications import get_notifications_widget


def _get_active_enrollment_for_user(user):
    return (
        AcademicEnrollment.objects.select_related(
            "academic_class",
            "academic_year",
            "programme",
            "branch",
        )
        .filter(student=user, is_active=True)
        .order_by("-created_at", "-id")
        .first()
    )


def _get_student_ec_queryset(enrollment):
    if enrollment is None:
        return EC.objects.none()

    return (
        EC.objects.select_related(
            "ue",
            "ue__semester",
            "ue__semester__academic_class",
        )
        .prefetch_related(
            Prefetch(
                "chapters",
                queryset=ECChapter.objects.prefetch_related("contents").order_by("order", "id"),
            )
        )
        .filter(ue__semester__academic_class=enrollment.academic_class)
        .order_by("ue__semester__number", "ue__code", "id")
    )


@login_required
@role_required("student")
def dashboard(request):
    context = get_student_dashboard_shell(request.user)
    enrollment = _get_active_enrollment_for_user(request.user)
    course_preview = list(_get_student_ec_queryset(enrollment)[:6])
    context.update(
        {
            "course_preview": course_preview,
            "course_preview_count": len(course_preview),
        }
    )
    return render(request, "portal/student/dashboard.html", context)


@login_required
@role_required("student")
def profile_partial(request):
    context = get_profile_widget(request.user)
    return render(request, "portal/student/partials/profile.html", context)


@login_required
@role_required("student")
def academics_partial(request):
    context = get_academics_widget(request.user)
    return render(request, "portal/student/partials/academics.html", context)


@login_required
@role_required("student")
def finance_partial(request):
    context = get_finance_widget(request.user)
    return render(request, "portal/student/partials/finance.html", context)


@login_required
@role_required("student")
def notifications_partial(request):
    context = get_notifications_widget(request.user)
    return render(request, "portal/student/partials/notifications.html", context)


@login_required
@role_required("student")
def student_courses(request):
    enrollment = _get_active_enrollment_for_user(request.user)

    ec_rows = []
    if enrollment is not None:
        ecs = _get_student_ec_queryset(enrollment)
        for ec in ecs:
            content_count = sum(chapter.contents.count() for chapter in ec.chapters.all())
            ec_rows.append({
                "ec": ec,
                "content_count": content_count,
            })

    return render(
        request,
        "portal/student/courses.html",
        {
            "page_title": "Mes cours",
            "subtitle": "Consultez vos matieres et les contenus pedagogiques disponibles.",
            "enrollment": enrollment,
            "ec_rows": ec_rows,
        },
    )


@login_required
@role_required("student")
def ec_detail(request, ec_id):
    enrollment = get_object_or_404(
        AcademicEnrollment.objects.filter(pk=getattr(_get_active_enrollment_for_user(request.user), "pk", None)),
    )

    ec = get_object_or_404(
        EC.objects.select_related(
            "ue",
            "ue__semester",
            "ue__semester__academic_class",
        ).prefetch_related(
            Prefetch(
                "chapters",
                queryset=ECChapter.objects.prefetch_related("contents").order_by("order", "id"),
            )
        ),
        pk=ec_id,
        ue__semester__academic_class=enrollment.academic_class,
    )

    return render(
        request,
        "portal/student/ec_detail.html",
        {
            "page_title": ec.title,
            "subtitle": "Contenus lies a cette matiere.",
            "enrollment": enrollment,
            "ec": ec,
            "chapters": ec.chapters.all(),
        },
    )
