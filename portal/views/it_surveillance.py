from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, render

from accounts.access import get_user_position
from students.models import Student

from portal.services.it_surveillance_service import (
	build_it_surveillance_payload,
	build_student_followup_payload,
)


def _deny_it_access(request):
	return HttpResponseForbidden("Acces refuse.")


@login_required
def it_surveillance_workspace_view(request):
	"""Workspace HTMX intégré dans le dashboard informaticien."""

	if get_user_position(request.user) != "it_support":
		return _deny_it_access(request)

	context = build_it_surveillance_payload(
		user=request.user,
		class_id=request.GET.get("class_id"),
		date=request.GET.get("date"),
		status=request.GET.get("status"),
	)
	return render(request, "portal/staff/partials/it_surveillance_workspace.html", context)


@login_required
def it_surveillance_student_followup_view(request, student_id: int):
	"""Panneau 'Suivi étudiant' chargé en HTMX depuis le tableau principal."""

	if get_user_position(request.user) != "it_support":
		return _deny_it_access(request)

	student = get_object_or_404(Student.objects.select_related("inscription__candidature"), pk=student_id)
	context = build_student_followup_payload(
		user=request.user,
		student=student,
		class_id=request.GET.get("class_id"),
		date=request.GET.get("date"),
	)
	return render(
		request,
		"portal/staff/partials/it_surveillance_student_followup.html",
		context,
	)


@login_required
def surveillance_general_api_view(request):
	"""Endpoint JSON demandé : /surveillance/general/"""

	if get_user_position(request.user) != "it_support":
		return JsonResponse({"error": "Acces refuse."}, status=403)

	payload = build_it_surveillance_payload(
		user=request.user,
		class_id=request.GET.get("class_id"),
		date=request.GET.get("date"),
		status=request.GET.get("status"),
	)
	return JsonResponse(
		{
			"absents_today": payload["absents_today"],
			"late_today": payload["late_today"],
			"incidents_pending": payload["incidents_pending"],
			"attendance_rate": payload["attendance_rate"],
			"students": payload["students"],
			"incidents": payload["incidents"],
			"charts": payload["charts"],
		}
	)


