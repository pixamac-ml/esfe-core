from django.shortcuts import render

from portal.views.views import _position_required
from portal.views.views import (
    _build_it_dashboard_context,
    build_it_grade_selection_context,
)


def _quality_score_to_tone(score):
    if score >= 85:
        return "success"
    if score >= 70:
        return "info"
    if score >= 50:
        return "warning"
    return "danger"


@_position_required({"it_support"})
def it_portal_v2(request):
    """Affiche le dashboard opérationnel du support informatique."""
    context = _build_it_dashboard_context(request)
    context.update(
        build_it_grade_selection_context(
            request.user,
            class_id=request.GET.get("class_id"),
            semester_id=request.GET.get("semester_id"),
        )
    )
    quality = context.get("quality", {})
    context["quality_tone"] = _quality_score_to_tone(quality.get("score", 0))
    return render(
        request,
        "portal/staff/informaticien_dashboard_v2.html",
        context,
    )
