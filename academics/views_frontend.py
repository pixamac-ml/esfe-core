import json
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from academics.models import AcademicCalendarEntry


@login_required
def academic_calendar_frontend(request):
    """Page frontend du Calendrier Académique (UI client, endpoints JSON existants)."""
    today = timezone.now()
    event_types = [{"value": t[0], "label": t[1]} for t in AcademicCalendarEntry.EVENT_TYPE_CHOICES]
    statuses = [{"value": s[0], "label": s[1]} for s in AcademicCalendarEntry.STATUS_CHOICES]
    context = {
        "current_year": today.year,
        "current_month": today.month,
        "event_types_json": json.dumps(event_types),
        "statuses_json": json.dumps(statuses),
    }
    return render(request, "academics/calendar/calendar.html", context)
