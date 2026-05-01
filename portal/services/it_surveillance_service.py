from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date as date_type, datetime, timedelta
from typing import Any

from django.db.models import Count, Q
from django.utils import timezone

from academics.models import AcademicClass
from accounts.dashboards.helpers import get_user_branch
from students.models import AttendanceAlert, Student, StudentAttendance
from students.services.attendance_service import get_student_attendance_history


STATUS_FILTERS = [
	{"value": "", "label": "Tous"},
	{"value": StudentAttendance.STATUS_PRESENT, "label": "Présent"},
	{"value": StudentAttendance.STATUS_ABSENT, "label": "Absent"},
	{"value": StudentAttendance.STATUS_LATE, "label": "Retard"},
]


def _parse_date(raw: str | None) -> date_type:
	if not raw:
		return timezone.localdate()
	try:
		return datetime.strptime(raw, "%Y-%m-%d").date()
	except ValueError:
		return timezone.localdate()


def _normalize_status(raw: str | None) -> str:
	value = (raw or "").strip().lower()
	if value in {StudentAttendance.STATUS_PRESENT, StudentAttendance.STATUS_ABSENT, StudentAttendance.STATUS_LATE}:
		return value
	return ""


def _safe_percent(numerator: int, denominator: int) -> float:
	if not denominator:
		return 0.0
	return round((numerator / denominator) * 100.0, 2)


def _student_display_name(student: Student) -> str:
	# students.Student.full_name = "{first} {last}" dans ce projet
	return student.full_name


def build_it_surveillance_payload(*, user, class_id=None, date=None, status=None) -> dict[str, Any]:
	branch = get_user_branch(user)
	selected_date = _parse_date(date)
	selected_status = _normalize_status(status)

	classes_qs = AcademicClass.objects.select_related("academic_year", "branch", "programme").filter(is_active=True)
	if branch:
		classes_qs = classes_qs.filter(branch=branch)
	classes = list(classes_qs.order_by("level", "programme__title")[:200])

	selected_class = None
	if class_id and str(class_id).isdigit():
		selected_class = classes_qs.filter(pk=int(class_id)).first()

	attendance_qs = StudentAttendance.objects.select_related(
		"student__inscription__candidature",
		"academic_class__academic_year",
		"schedule_event",
		"branch",
	).filter(date=selected_date)
	if branch:
		attendance_qs = attendance_qs.filter(branch=branch)
	if selected_class:
		attendance_qs = attendance_qs.filter(academic_class=selected_class)
	if selected_status:
		attendance_qs = attendance_qs.filter(status=selected_status)

	total_today = attendance_qs.count()
	absents_today = attendance_qs.filter(status=StudentAttendance.STATUS_ABSENT).count()
	late_today = attendance_qs.filter(status=StudentAttendance.STATUS_LATE).count()
	present_today = attendance_qs.filter(status=StudentAttendance.STATUS_PRESENT).count()
	attendance_rate = _safe_percent(present_today + late_today, total_today)

	# Incidents/discipline = AttendanceAlert (assiduité). On expose pending vs resolved.
	incidents_qs = AttendanceAlert.objects.select_related(
		"student__inscription__candidature",
		"branch",
	)
	if branch:
		incidents_qs = incidents_qs.filter(branch=branch)
	if selected_class:
		# Link via inscriptions académiques -> on restreint via présence du jour si possible.
		# Fallback simple: si l'étudiant a une présence du jour dans la classe filtrée, on le garde.
		student_ids_today = attendance_qs.values_list("student_id", flat=True).distinct()
		incidents_qs = incidents_qs.filter(student_id__in=list(student_ids_today))

	incidents_pending = incidents_qs.filter(is_resolved=False).count()

	def _incident_type(alert: AttendanceAlert) -> str:
		if alert.alert_type == AttendanceAlert.TYPE_ABSENCE_REPETITION:
			return "Absence"
		if alert.alert_type == AttendanceAlert.TYPE_LATE_REPETITION:
			return "Retard"
		return "Assiduité"

	incidents = [
		{
			"student_id": alert.student_id,
			"student_name": _student_display_name(alert.student),
			"type": _incident_type(alert),
			"description": f"{alert.get_alert_type_display()} ({alert.count})",
			"status_code": "pending" if not alert.is_resolved else "resolved",
			"status": "Non traité" if not alert.is_resolved else "Traité",
			"created_at": timezone.localtime(alert.triggered_at).strftime("%d/%m/%Y %H:%M"),
		}
		for alert in incidents_qs.order_by("is_resolved", "-triggered_at")[:40]
	]

	# Tableau principal étudiants (attendances)
	students = []
	for attendance in attendance_qs.order_by(
		"academic_class__level",
		"academic_class__programme__title",
		"student__inscription__candidature__last_name",
		"student__inscription__candidature__first_name",
	)[:400]:
		status_code = attendance.status
		students.append(
			{
				"student_id": attendance.student_id,
				"student_name": _student_display_name(attendance.student),
				"matricule": attendance.student.matricule,
				"class_id": attendance.academic_class_id,
				"class_name": attendance.academic_class.display_name,
				"status_code": status_code,
				"status": dict(StudentAttendance.STATUS_CHOICES).get(status_code, status_code),
				"time": (
					attendance.arrival_time.strftime("%H:%M")
					if attendance.arrival_time
					else (
						timezone.localtime(attendance.schedule_event.start_datetime).strftime("%H:%M")
						if attendance.schedule_event_id
						else ""
					)
				),
				"action_label": "Voir suivi",
			}
		)

	followup_students = _build_followup_students(branch=branch, selected_class=selected_class)

	charts = _build_charts(
		branch=branch,
		selected_class=selected_class,
		selected_date=selected_date,
	)

	chart_dom_id = f"surv-{int(timezone.now().timestamp())}"

	return {
		"branch": branch,
		"classes": classes,
		"selected_class": selected_class,
		"selected_date": selected_date,
		"selected_status": selected_status,
		"status_filters": STATUS_FILTERS,
		"absents_today": absents_today,
		"late_today": late_today,
		"incidents_pending": incidents_pending,
		"attendance_rate": attendance_rate,
		"students": students,
		"incidents": incidents,
		"frequent_students": followup_students,
		"charts": charts,
		"charts_json": json.dumps(charts),
		"chart_dom_id": chart_dom_id,
		"table_total": len(students),
	}


def _build_followup_students(*, branch, selected_class) -> list[dict[str, Any]]:
	# On se base sur les alertes non résolues + un peu d’historique.
	alerts_qs = AttendanceAlert.objects.select_related("student__inscription__candidature").filter(is_resolved=False)
	if branch:
		alerts_qs = alerts_qs.filter(branch=branch)
	if selected_class:
		student_ids = StudentAttendance.objects.filter(
			academic_class=selected_class,
			date__gte=timezone.localdate() - timedelta(days=30),
		).values_list("student_id", flat=True).distinct()
		alerts_qs = alerts_qs.filter(student_id__in=list(student_ids))

	# top 8
	top_alerts = list(alerts_qs.order_by("-count", "-triggered_at")[:8])
	items = []
	for alert in top_alerts:
		student = alert.student
		history = get_student_attendance_history(student, branch=branch, limit=5)
		absences = sum(1 for row in history if row.get("status") == StudentAttendance.STATUS_ABSENT)
		lates = sum(1 for row in history if row.get("status") == StudentAttendance.STATUS_LATE)
		items.append(
			{
				"student_id": student.id,
				"student_name": _student_display_name(student),
				"matricule": student.matricule,
				"incidents": alert.count,
				"absences": absences,
				"lates": lates,
				"history": [
					{
						"date": row.get("date"),
						"classroom": row.get("classroom"),
						"status": dict(StudentAttendance.STATUS_CHOICES).get(row.get("status"), row.get("status")),
					}
					for row in history
				],
			}
		)
	return items


def _build_charts(*, branch, selected_class, selected_date: date_type) -> dict[str, Any]:
	# Line: 7 derniers jours absences
	start = selected_date - timedelta(days=6)
	dates = [start + timedelta(days=i) for i in range(7)]
	line_absences = []
	for d in dates:
		qs = StudentAttendance.objects.filter(date=d, status=StudentAttendance.STATUS_ABSENT)
		if branch:
			qs = qs.filter(branch=branch)
		if selected_class:
			qs = qs.filter(academic_class=selected_class)
		line_absences.append(qs.count())

	# Pie: incidents pending vs resolved
	alerts_qs = AttendanceAlert.objects.all()
	if branch:
		alerts_qs = alerts_qs.filter(branch=branch)
	if selected_class:
		student_ids = StudentAttendance.objects.filter(
			academic_class=selected_class,
			date__gte=selected_date - timedelta(days=30),
		).values_list("student_id", flat=True).distinct()
		alerts_qs = alerts_qs.filter(student_id__in=list(student_ids))
	pending_count = alerts_qs.filter(is_resolved=False).count()
	resolved_count = alerts_qs.filter(is_resolved=True).count()

	# Bar: absences par classe (sur la date sélectionnée)
	bar_qs = StudentAttendance.objects.filter(date=selected_date, status=StudentAttendance.STATUS_ABSENT)
	if branch:
		bar_qs = bar_qs.filter(branch=branch)
	if selected_class:
		bar_qs = bar_qs.filter(academic_class=selected_class)
	else:
		bar_qs = bar_qs.select_related("academic_class")

	by_class = (
		bar_qs.values("academic_class__level", "academic_class__programme__title")
		.annotate(total=Count("id"))
		.order_by("-total", "academic_class__level", "academic_class__programme__title")[:10]
	)
	bar_labels = [
		f"{row['academic_class__level']} {row['academic_class__programme__title']}".strip()
		for row in by_class
	]
	bar_values = [row["total"] for row in by_class]

	return {
		"line": {
			"labels": [d.strftime("%d/%m") for d in dates],
			"datasets": [
				{
					"label": "Absences",
					"data": line_absences,
					"borderColor": "#ef4444",
					"backgroundColor": "rgba(239, 68, 68, 0.12)",
					"tension": 0.35,
					"fill": True,
				}
			],
		},
		"pie": {
			"labels": ["Non traités", "Traités"],
			"datasets": [
				{
					"data": [pending_count, resolved_count],
					"backgroundColor": ["#f43f5e", "#10b981"],
				}
			],
		},
		"bar": {
			"labels": bar_labels,
			"datasets": [
				{
					"label": "Absences",
					"data": bar_values,
					"backgroundColor": "rgba(59, 130, 246, 0.55)",
				}
			],
		},
	}


def build_student_followup_payload(*, user, student: Student, class_id=None, date=None) -> dict[str, Any]:
	branch = get_user_branch(user)
	selected_date = _parse_date(date)

	history = get_student_attendance_history(student, branch=branch, limit=15)
	formatted_history = [
		{
			"date": row.get("date"),
			"classroom": row.get("classroom"),
			"time": row.get("arrival_time") or row.get("schedule_event_time") or "",
			"status": dict(StudentAttendance.STATUS_CHOICES).get(row.get("status"), row.get("status")),
			"justification": row.get("justification") or "",
		}
		for row in history
	]

	alerts_qs = AttendanceAlert.objects.filter(student=student)
	if branch:
		alerts_qs = alerts_qs.filter(branch=branch)

	open_alerts = alerts_qs.filter(is_resolved=False).count()
	resolved_alerts = alerts_qs.filter(is_resolved=True).count()

	recent_incidents = [
		{
			"type": "Absence" if alert.alert_type == AttendanceAlert.TYPE_ABSENCE_REPETITION else "Retard",
			"description": f"{alert.get_alert_type_display()} ({alert.count})",
			"status_code": "pending" if not alert.is_resolved else "resolved",
			"status": "Non traité" if not alert.is_resolved else "Traité",
			"created_at": timezone.localtime(alert.triggered_at).strftime("%d/%m/%Y %H:%M"),
		}
		for alert in alerts_qs.order_by("is_resolved", "-triggered_at")[:10]
	]

	return {
		"selected_date": selected_date,
		"student_id": student.id,
		"student_name": _student_display_name(student),
		"matricule": student.matricule,
		"open_alerts": open_alerts,
		"resolved_alerts": resolved_alerts,
		"history": formatted_history,
		"recent_incidents": recent_incidents,
	}


