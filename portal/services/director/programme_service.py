from __future__ import annotations

from urllib.parse import urlencode

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Count, Prefetch, Q

from academics.models import AcademicClass, AcademicEnrollment, AcademicYear, EC, Semester, UE
from formations.models import Programme


PROGRAMME_SUBVIEWS = {"overview", "classes", "maquettes"}


def _page(queryset, page_number, *, per_page=12):
    paginator = Paginator(queryset, per_page)
    try:
        return paginator.page(page_number or 1)
    except (EmptyPage, PageNotAnInteger):
        return paginator.page(1)


def _active_classes(branch):
    if branch is None:
        return AcademicClass.objects.none()
    return (
        AcademicClass.objects.select_related("programme", "programme__cycle", "academic_year", "branch")
        .filter(branch=branch, is_active=True, is_archived=False)
        .annotate(
            active_student_count=Count(
                "enrollments",
                filter=Q(
                    enrollments__is_active=True,
                    enrollments__status=AcademicEnrollment.STATUS_ACTIVE,
                ),
                distinct=True,
            ),
            programme_semester_count=Count("semesters", distinct=True),
            programme_ue_count=Count(
                "semesters__ues",
                filter=~Q(semesters__ues__structure_status=UE.STRUCTURE_ARCHIVED),
                distinct=True,
            ),
            programme_ec_count=Count(
                "semesters__ues__ecs",
                filter=~Q(semesters__ues__ecs__structure_status=EC.STRUCTURE_ARCHIVED),
                distinct=True,
            ),
        )
        .order_by("programme__title", "level", "academic_year__name", "id")
    )


def _structure_for_class(academic_class):
    if academic_class is None:
        return [], {"semesters": 0, "ues": 0, "ecs": 0, "credits": 0}

    active_ecs = EC.objects.exclude(structure_status=EC.STRUCTURE_ARCHIVED).order_by("title", "id")
    active_ues = (
        UE.objects.exclude(structure_status=UE.STRUCTURE_ARCHIVED)
        .prefetch_related(Prefetch("ecs", queryset=active_ecs, to_attr="active_ecs"))
        .order_by("code", "id")
    )
    semesters = list(
        Semester.objects.filter(academic_class=academic_class)
        .prefetch_related(Prefetch("ues", queryset=active_ues, to_attr="active_ues"))
        .order_by("number", "id")
    )

    rows = []
    total_ues = 0
    total_ecs = 0
    total_credits = 0
    for semester in semesters:
        semester_ues = list(semester.active_ues)
        for ue in semester_ues:
            ue.active_credit_total = sum(ec.credit_required for ec in ue.active_ecs)
            ue.active_coefficient_total = sum(ec.coefficient for ec in ue.active_ecs)
        semester_ec_count = sum(len(ue.active_ecs) for ue in semester_ues)
        semester_credits = sum(
            ec.credit_required for ue in semester_ues for ec in ue.active_ecs
        )
        rows.append(
            {
                "title": f"Semestre {semester.number}",
                "semester": semester,
                "ues": semester_ues,
                "ec_count": semester_ec_count,
                "credits": semester_credits,
                "is_empty": not semester_ues,
            }
        )
        total_ues += len(semester_ues)
        total_ecs += semester_ec_count
        total_credits += semester_credits

    return rows, {
        "semesters": len(semesters),
        "ues": total_ues,
        "ecs": total_ecs,
        "credits": total_credits,
    }


def build_director_programme_context(
    *,
    branch,
    subview="overview",
    selected_class_id=None,
    query="",
    programme_id=None,
    academic_year_id=None,
    level="",
    page_number=1,
):
    subview = subview if subview in PROGRAMME_SUBVIEWS else "overview"
    query = (query or "").strip()
    level = (level or "").strip().upper()

    base_classes = _active_classes(branch)
    filtered_classes = base_classes
    if query:
        filtered_classes = filtered_classes.filter(
            Q(name__icontains=query)
            | Q(level__icontains=query)
            | Q(programme__title__icontains=query)
            | Q(academic_year__name__icontains=query)
        )
    if str(programme_id or "").isdigit():
        filtered_classes = filtered_classes.filter(programme_id=int(programme_id))
        programme_id = str(programme_id)
    else:
        programme_id = ""
    if str(academic_year_id or "").isdigit():
        filtered_classes = filtered_classes.filter(academic_year_id=int(academic_year_id))
        academic_year_id = str(academic_year_id)
    else:
        academic_year_id = ""
    if level:
        filtered_classes = filtered_classes.filter(level__iexact=level)

    selected_class = None
    if str(selected_class_id or "").isdigit():
        selected_class = base_classes.filter(pk=int(selected_class_id)).first()
    if selected_class is None:
        selected_class = filtered_classes.first()

    structure_rows, structure_totals = _structure_for_class(selected_class)
    classes_page = _page(filtered_classes, page_number, per_page=12)

    total_classes = base_classes.count()
    total_semesters = Semester.objects.filter(
        academic_class__branch=branch,
        academic_class__is_active=True,
        academic_class__is_archived=False,
    ).count() if branch else 0
    total_ues = UE.objects.filter(
        semester__academic_class__branch=branch,
        semester__academic_class__is_active=True,
        semester__academic_class__is_archived=False,
    ).exclude(structure_status=UE.STRUCTURE_ARCHIVED).count() if branch else 0
    total_ecs = EC.objects.filter(
        ue__semester__academic_class__branch=branch,
        ue__semester__academic_class__is_active=True,
        ue__semester__academic_class__is_archived=False,
    ).exclude(structure_status=EC.STRUCTURE_ARCHIVED).count() if branch else 0
    incomplete_classes = base_classes.filter(
        Q(programme_semester_count__lt=2)
        | Q(programme_ue_count=0)
        | Q(programme_ec_count=0)
    ).count()

    query_params = {"view": subview}
    if query:
        query_params["programme_q"] = query
    if programme_id:
        query_params["programme_id"] = programme_id
    if academic_year_id:
        query_params["academic_year_id"] = academic_year_id
    if level:
        query_params["level"] = level

    programme_ids = base_classes.values_list("programme_id", flat=True).distinct()
    academic_year_ids = base_classes.values_list("academic_year_id", flat=True).distinct()
    return {
        "programme_subview": subview,
        "programme_classes_page": classes_page,
        "programme_filtered_count": classes_page.paginator.count,
        "programme_selected_class": selected_class,
        "programme_structure_rows": structure_rows,
        "programme_structure_totals": structure_totals,
        "programme_filter_programmes": list(
            Programme.objects.filter(pk__in=programme_ids).order_by("title", "id")
        ),
        "programme_filter_years": list(
            AcademicYear.objects.filter(pk__in=academic_year_ids).order_by("-start_date", "-id")
        ),
        "programme_filter_levels": list(
            base_classes.order_by("level").values_list("level", flat=True).distinct()
        ),
        "programme_q": query,
        "programme_filter_programme_id": programme_id,
        "programme_filter_academic_year_id": academic_year_id,
        "programme_filter_level": level,
        "programme_query_suffix": urlencode(query_params),
        "programme_metrics": {
            "classes": total_classes,
            "semesters": total_semesters,
            "ues": total_ues,
            "ecs": total_ecs,
            "incomplete_classes": incomplete_classes,
        },
    }
