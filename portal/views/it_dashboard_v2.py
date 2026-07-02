from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from portal.views.views import (
    _build_it_dashboard_context,
    build_it_grade_selection_context,
)


@login_required
def it_portal_v2(request):
    """Vue prototype pour le dashboard informaticien refactorisé avec composants UI"""
    context = _build_it_dashboard_context(request)
    context.update(
        build_it_grade_selection_context(
            request.user,
            class_id=request.GET.get("class_id"),
            semester_id=request.GET.get("semester_id"),
        )
    )
    return render(
        request,
        "portal/staff/informaticien_dashboard_v2.html",
        context,
    )
