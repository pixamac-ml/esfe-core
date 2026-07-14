import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods

from academics.models import AcademicCalendar, AcademicCalendarEntry, AcademicClass, AcademicYear, Semester
from academics.permissions.calendar_permissions import calendar_queryset_for_user
from academics.services.calendar_service import (
    archive_calendar,
    create_calendar,
    create_calendar_entry,
    delete_calendar_entry,
    publish_calendar,
    update_calendar,
    update_calendar_entry,
    validate_calendar,
)
from branches.models import Branch
from formations.models import Programme


def _payload(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Corps JSON invalide.") from exc


def _errors(exc):
    if isinstance(exc, PermissionDenied):
        return JsonResponse({"ok": False, "errors": [str(exc)]}, status=403)
    if hasattr(exc, "message_dict"):
        return JsonResponse({"ok": False, "errors": exc.message_dict}, status=400)
    return JsonResponse({"ok": False, "errors": getattr(exc, "messages", [str(exc)])}, status=400)


def _auth(request):
    if not request.user.is_authenticated:
        raise PermissionDenied("Authentification requise.")


def _calendar_data(calendar, detail=False):
    data = {
        "id": calendar.pk,
        "branch_id": calendar.branch_id,
        "academic_year_id": calendar.academic_year_id,
        "version": calendar.version,
        "status": calendar.status,
        "published_at": calendar.published_at.isoformat() if calendar.published_at else None,
    }
    if detail:
        data["entries"] = [_entry_data(entry) for entry in calendar.entries.all()]
    return data


def _entry_data(entry):
    return {
        "id": entry.pk, "title": entry.title, "description": entry.description,
        "event_type": entry.event_type, "start_datetime": entry.start_datetime.isoformat(),
        "end_datetime": entry.end_datetime.isoformat(), "all_day": entry.all_day,
        "target_scope": entry.target_scope, "programme_id": entry.programme_id,
        "academic_class_id": entry.academic_class_id, "semester_id": entry.semester_id,
        "color": entry.color, "icon": entry.icon, "is_blocking": entry.is_blocking,
        "status": entry.status,
    }


def _calendar(request, pk):
    return get_object_or_404(
        calendar_queryset_for_user(request.user, AcademicCalendar.objects.select_related("branch", "academic_year")),
        pk=pk,
    )


@require_http_methods(["GET", "POST"])
def calendar_list_create(request):
    try:
        _auth(request)
        if request.method == "GET":
            qs = calendar_queryset_for_user(request.user, AcademicCalendar.objects.select_related("branch", "academic_year"))
            if request.GET.get("branch"):
                qs = qs.filter(branch_id=request.GET["branch"])
            if request.GET.get("academic_year"):
                qs = qs.filter(academic_year_id=request.GET["academic_year"])
            return JsonResponse({"ok": True, "calendars": [_calendar_data(item) for item in qs]})
        data = _payload(request)
        calendar = create_calendar(
            actor=request.user,
            branch=get_object_or_404(Branch, pk=data.get("branch_id")),
            academic_year=get_object_or_404(AcademicYear, pk=data.get("academic_year_id")),
            version=data.get("version", 1),
        )
        return JsonResponse({"ok": True, "calendar": _calendar_data(calendar)}, status=201)
    except (ValidationError, PermissionDenied) as exc:
        return _errors(exc)


@require_http_methods(["GET", "PATCH"])
def calendar_detail_update(request, pk):
    try:
        _auth(request)
        calendar = _calendar(request, pk)
        if request.method == "GET":
            return JsonResponse({"ok": True, "calendar": _calendar_data(calendar, detail=True)})
        calendar = update_calendar(calendar, actor=request.user, **_payload(request))
        return JsonResponse({"ok": True, "calendar": _calendar_data(calendar)})
    except (ValidationError, PermissionDenied) as exc:
        return _errors(exc)


def _transition(request, pk, operation):
    try:
        _auth(request)
        calendar = operation(_calendar(request, pk), actor=request.user)
        return JsonResponse({"ok": True, "calendar": _calendar_data(calendar)})
    except (ValidationError, PermissionDenied) as exc:
        return _errors(exc)


@require_http_methods(["POST"])
def calendar_validate(request, pk):
    return _transition(request, pk, validate_calendar)


@require_http_methods(["POST"])
def calendar_publish(request, pk):
    return _transition(request, pk, publish_calendar)


@require_http_methods(["POST"])
def calendar_archive(request, pk):
    return _transition(request, pk, archive_calendar)


def _entry_payload(data):
    values = dict(data)
    for name, model in (("programme", Programme), ("academic_class", AcademicClass), ("semester", Semester)):
        identifier = values.pop(f"{name}_id", None)
        if identifier is not None:
            values[name] = get_object_or_404(model, pk=identifier) if identifier else None
    for name in ("start_datetime", "end_datetime"):
        if name in values:
            values[name] = parse_datetime(values[name])
            if values[name] is None:
                raise ValidationError({name: "Date ISO 8601 invalide."})
    return values


@require_http_methods(["POST"])
def calendar_entry_create(request, pk):
    try:
        _auth(request)
        entry = create_calendar_entry(actor=request.user, calendar=_calendar(request, pk), **_entry_payload(_payload(request)))
        return JsonResponse({"ok": True, "entry": _entry_data(entry)}, status=201)
    except (ValidationError, PermissionDenied) as exc:
        return _errors(exc)


@require_http_methods(["PATCH", "DELETE"])
def calendar_entry_detail(request, pk, entry_pk):
    try:
        _auth(request)
        calendar = _calendar(request, pk)
        entry = get_object_or_404(calendar.entries.all(), pk=entry_pk)
        if request.method == "DELETE":
            delete_calendar_entry(entry, actor=request.user)
            return JsonResponse({"ok": True})
        entry = update_calendar_entry(entry, actor=request.user, **_entry_payload(_payload(request)))
        return JsonResponse({"ok": True, "entry": _entry_data(entry)})
    except (ValidationError, PermissionDenied) as exc:
        return _errors(exc)
