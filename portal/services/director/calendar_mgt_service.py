"""
Service de gestion du calendrier academique — Dashboard Directeur.

Responsabilites :
- Metadonnees et regles metier par type d'evenement (EVENT_META)
- Groupes logiques pour le formulaire (EVENT_GROUPS)
- Validation metier des entrees avant persistence (validate_entry_business_rules)
- Construction du contexte complet pour le template (build_director_calendar_context)
"""
import json

from django.core.exceptions import ValidationError
from django.utils import timezone

from academics.models import (
    AcademicCalendar,
    AcademicCalendarDisruption,
    AcademicCalendarEntry,
    AcademicYear,
)


# ---------------------------------------------------------------------------
# Métadonnées par type d'événement
# ---------------------------------------------------------------------------

EVENT_META = {
    AcademicCalendarEntry.EVENT_ACADEMIC_START: {
        "label": "Rentree academique",
        "icon": "flag",
        "tone": "primary",
        "color_bg": "bg-[color:var(--school-primary-soft)]",
        "color_text": "text-[color:var(--school-primary)]",
        "unique_per_calendar": True,
        "force_scope": AcademicCalendarEntry.SCOPE_BRANCH,
        "is_blocking": True,
        "needs_class": False,
        "needs_semester": False,
        "description": "Date officielle de rentree de l'annexe. Un seul autorise par calendrier.",
    },
    AcademicCalendarEntry.EVENT_ACADEMIC_END: {
        "label": "Cloture academique",
        "icon": "flag-off",
        "tone": "muted",
        "color_bg": "bg-slate-100",
        "color_text": "text-slate-600",
        "unique_per_calendar": True,
        "force_scope": AcademicCalendarEntry.SCOPE_BRANCH,
        "is_blocking": False,
        "needs_class": False,
        "needs_semester": False,
        "description": "Date de fin de l'annee academique. Un seul autorise par calendrier.",
    },
    AcademicCalendarEntry.EVENT_SEMESTER_START: {
        "label": "Debut de semestre",
        "icon": "play-circle",
        "tone": "primary",
        "color_bg": "bg-blue-50",
        "color_text": "text-blue-700",
        "unique_per_calendar": False,
        "force_scope": None,
        "is_blocking": False,
        "needs_class": False,
        "needs_semester": False,
        "description": "Debut d'un semestre, commun a l'annexe ou cible a une classe/semestre.",
    },
    AcademicCalendarEntry.EVENT_SEMESTER_END: {
        "label": "Fin de semestre",
        "icon": "stop-circle",
        "tone": "muted",
        "color_bg": "bg-blue-50",
        "color_text": "text-blue-500",
        "unique_per_calendar": False,
        "force_scope": None,
        "is_blocking": False,
        "needs_class": False,
        "needs_semester": False,
        "description": "Fin d'un semestre, commune a l'annexe ou ciblee a une classe/semestre.",
    },
    AcademicCalendarEntry.EVENT_HOLIDAY: {
        "label": "Vacances",
        "icon": "sun",
        "tone": "warning",
        "color_bg": "bg-amber-50",
        "color_text": "text-amber-700",
        "unique_per_calendar": False,
        "force_scope": AcademicCalendarEntry.SCOPE_BRANCH,
        "is_blocking": True,
        "needs_class": False,
        "needs_semester": False,
        "description": "Periode de vacances scolaires. Bloquante pour toute l'annexe.",
    },
    AcademicCalendarEntry.EVENT_PUBLIC_HOLIDAY: {
        "label": "Jour ferie",
        "icon": "star",
        "tone": "warning",
        "color_bg": "bg-amber-50",
        "color_text": "text-amber-600",
        "unique_per_calendar": False,
        "force_scope": AcademicCalendarEntry.SCOPE_BRANCH,
        "is_blocking": True,
        "needs_class": False,
        "needs_semester": False,
        "description": "Jour ferie officiel. Bloquant pour toute l'annexe.",
    },
    AcademicCalendarEntry.EVENT_REGISTRATION: {
        "label": "Inscription",
        "icon": "user-plus",
        "tone": "success",
        "color_bg": "bg-emerald-50",
        "color_text": "text-emerald-700",
        "unique_per_calendar": False,
        "force_scope": AcademicCalendarEntry.SCOPE_BRANCH,
        "is_blocking": False,
        "needs_class": False,
        "needs_semester": False,
        "description": "Periode d'inscription des nouveaux etudiants.",
    },
    AcademicCalendarEntry.EVENT_REREGISTRATION: {
        "label": "Reinscription",
        "icon": "refresh-cw",
        "tone": "success",
        "color_bg": "bg-emerald-50",
        "color_text": "text-emerald-600",
        "unique_per_calendar": False,
        "force_scope": AcademicCalendarEntry.SCOPE_BRANCH,
        "is_blocking": False,
        "needs_class": False,
        "needs_semester": False,
        "description": "Periode de reinscription des etudiants deja en cours.",
    },
    AcademicCalendarEntry.EVENT_EXAM_SESSION: {
        "label": "Session d'examens",
        "icon": "pencil-ruler",
        "tone": "danger",
        "color_bg": "bg-red-50",
        "color_text": "text-red-700",
        "unique_per_calendar": False,
        "force_scope": None,
        "is_blocking": True,
        "needs_class": False,
        "needs_semester": False,
        "description": "Periode d'examens : commune ou ciblee selon la formation, la classe ou le semestre.",
    },
    AcademicCalendarEntry.EVENT_RETAKE_SESSION: {
        "label": "Session de rattrapage",
        "icon": "repeat",
        "tone": "danger",
        "color_bg": "bg-rose-50",
        "color_text": "text-rose-700",
        "unique_per_calendar": False,
        "force_scope": None,
        "is_blocking": True,
        "needs_class": False,
        "needs_semester": False,
        "description": "Periode de rattrapage : commune ou ciblee selon le parcours.",
    },
    AcademicCalendarEntry.EVENT_JURY: {
        "label": "Jury",
        "icon": "gavel",
        "tone": "accent",
        "color_bg": "bg-purple-50",
        "color_text": "text-purple-700",
        "unique_per_calendar": False,
        "force_scope": None,
        "is_blocking": True,
        "needs_class": False,
        "needs_semester": False,
        "description": "Deliberation du jury, rattachee au public academique concerne.",
    },
    AcademicCalendarEntry.EVENT_RESULT_PUBLICATION: {
        "label": "Publication des resultats",
        "icon": "megaphone",
        "tone": "accent",
        "color_bg": "bg-purple-50",
        "color_text": "text-purple-600",
        "unique_per_calendar": False,
        "force_scope": None,
        "is_blocking": False,
        "needs_class": False,
        "needs_semester": False,
        "description": "Publication officielle des resultats pour le public academique concerne.",
    },
    AcademicCalendarEntry.EVENT_CEREMONY: {
        "label": "Ceremonie",
        "icon": "award",
        "tone": "success",
        "color_bg": "bg-emerald-50",
        "color_text": "text-emerald-700",
        "unique_per_calendar": False,
        "force_scope": AcademicCalendarEntry.SCOPE_BRANCH,
        "is_blocking": True,
        "needs_class": False,
        "needs_semester": False,
        "description": "Ceremonie officielle (remise de diplomes, etc.).",
    },
    AcademicCalendarEntry.EVENT_MEETING: {
        "label": "Reunion",
        "icon": "users",
        "tone": "muted",
        "color_bg": "bg-slate-50",
        "color_text": "text-slate-600",
        "unique_per_calendar": False,
        "force_scope": None,
        "is_blocking": False,
        "needs_class": False,
        "needs_semester": False,
        "description": "Reunion de service, de parents ou autre.",
    },
    AcademicCalendarEntry.EVENT_OTHER: {
        "label": "Autre",
        "icon": "circle-dot",
        "tone": "muted",
        "color_bg": "bg-slate-50",
        "color_text": "text-slate-500",
        "unique_per_calendar": False,
        "force_scope": None,
        "is_blocking": False,
        "needs_class": False,
        "needs_semester": False,
        "description": "Evenement divers.",
    },
}

# Groupes logiques pour le formulaire
def _make_event_groups():
    _raw = [
        ("Structure de l'annee", "calendar-range", [
            AcademicCalendarEntry.EVENT_ACADEMIC_START,
            AcademicCalendarEntry.EVENT_ACADEMIC_END,
            AcademicCalendarEntry.EVENT_SEMESTER_START,
            AcademicCalendarEntry.EVENT_SEMESTER_END,
        ]),
        ("Periodes administratives", "clipboard-list", [
            AcademicCalendarEntry.EVENT_REGISTRATION,
            AcademicCalendarEntry.EVENT_REREGISTRATION,
        ]),
        ("Evaluations", "pencil-ruler", [
            AcademicCalendarEntry.EVENT_EXAM_SESSION,
            AcademicCalendarEntry.EVENT_RETAKE_SESSION,
            AcademicCalendarEntry.EVENT_JURY,
            AcademicCalendarEntry.EVENT_RESULT_PUBLICATION,
        ]),
        ("Conges et celebrations", "sun", [
            AcademicCalendarEntry.EVENT_HOLIDAY,
            AcademicCalendarEntry.EVENT_PUBLIC_HOLIDAY,
            AcademicCalendarEntry.EVENT_CEREMONY,
        ]),
        ("Divers", "more-horizontal", [
            AcademicCalendarEntry.EVENT_MEETING,
            AcademicCalendarEntry.EVENT_OTHER,
        ]),
    ]
    label_map = dict(AcademicCalendarEntry.EVENT_TYPE_CHOICES)
    return [
        {
            "label": grp_label,
            "icon": grp_icon,
            "choices": [(val, label_map[val]) for val in types if val in label_map],
        }
        for grp_label, grp_icon, types in _raw
    ]


EVENT_GROUPS = _make_event_groups()


def validate_entry_business_rules(*, calendar, event_type, start_datetime, end_datetime,
                                   target_scope, academic_class, semester, programme=None,
                                   exclude_entry_id=None):
    """
    Valide les regles metier specifiques a chaque type d'evenement.
    Doit etre appelee AVANT la creation ou la modification d'une AcademicCalendarEntry.
    La validation des champs du modele (dates aware, start < end) est deleguee a full_clean().
    """
    meta = EVENT_META.get(event_type)
    if not meta:
        raise ValidationError(f"Type d'evenement inconnu : {event_type!r}")

    academic_year = calendar.academic_year

    if target_scope == AcademicCalendarEntry.SCOPE_PROGRAMME and programme is None:
        raise ValidationError("Une formation ciblee est obligatoire pour cette portee.")
    if programme is not None and not AcademicClass.objects.filter(
        branch=calendar.branch,
        academic_year=academic_year,
        programme=programme,
    ).exists():
        raise ValidationError(
            "La formation ciblee n'est pas disponible dans l'annexe et l'annee du calendrier."
        )

    # 1. Unicite par calendrier (types a instance unique)
    if meta["unique_per_calendar"]:
        qs = AcademicCalendarEntry.objects.filter(
            calendar=calendar,
            event_type=event_type,
        ).exclude(status=AcademicCalendarEntry.STATUS_CANCELLED)
        if exclude_entry_id:
            qs = qs.exclude(id=exclude_entry_id)
        if qs.exists():
            raise ValidationError(
                f"Un evenement \u00ab {meta['label']} \u00bb existe d\u00e9j\u00e0 dans ce calendrier. "
                f"Un seul est autorise par calendrier."
            )

    # 2. Portee imposee par le type
    if meta["force_scope"] and target_scope != meta["force_scope"]:
        scope_label = dict(AcademicCalendarEntry.TARGET_SCOPE_CHOICES).get(
            meta["force_scope"], meta["force_scope"]
        )
        raise ValidationError(
            f"Les evenements \u00ab {meta['label']} \u00bb ont obligatoirement "
            f"la portee \u00ab {scope_label} \u00bb."
        )

    # 3. Classe requise
    if meta["needs_class"] and academic_class is None:
        raise ValidationError(
            f"Les evenements \u00ab {meta['label']} \u00bb doivent \u00eatre li\u00e9s "
            f"\u00e0 une classe sp\u00e9cifique."
        )

    # 4. Semestre requis
    if meta["needs_semester"] and semester is None:
        raise ValidationError(
            f"Les evenements \u00ab {meta['label']} \u00bb doivent \u00eatre li\u00e9s "
            f"\u00e0 un semestre."
        )

    # 5. Dates dans les bornes de l'annee academique
    # On compare via .date() pour eviter les problemes de timezone
    if timezone.is_aware(start_datetime):
        start_date = timezone.localtime(start_datetime).date()
        end_date = timezone.localtime(end_datetime).date()
    else:
        start_date = start_datetime.date()
        end_date = end_datetime.date()

    if start_date < academic_year.start_date or end_date > academic_year.end_date:
        raise ValidationError(
            f"Les dates doivent \u00eatre dans l'ann\u00e9e acad\u00e9mique "
            f"{academic_year.name} "
            f"({academic_year.start_date.strftime('%d/%m/%Y')} "
            f"\u2014 {academic_year.end_date.strftime('%d/%m/%Y')})."
        )

    # 6. Cloture apres rentree
    if event_type == AcademicCalendarEntry.EVENT_ACADEMIC_END:
        rentree = AcademicCalendarEntry.objects.filter(
            calendar=calendar,
            event_type=AcademicCalendarEntry.EVENT_ACADEMIC_START,
        ).exclude(status=AcademicCalendarEntry.STATUS_CANCELLED).first()
        if rentree and start_datetime <= rentree.start_datetime:
            raise ValidationError(
                "La cl\u00f4ture acad\u00e9mique doit \u00eatre apr\u00e8s la rentr\u00e9e."
            )

    # 7. Fin de semestre apres debut du meme semestre
    if event_type == AcademicCalendarEntry.EVENT_SEMESTER_END and semester:
        debut = AcademicCalendarEntry.objects.filter(
            calendar=calendar,
            event_type=AcademicCalendarEntry.EVENT_SEMESTER_START,
            semester=semester,
        ).exclude(status=AcademicCalendarEntry.STATUS_CANCELLED).first()
        if debut and start_datetime.date() <= debut.start_datetime.date():
            raise ValidationError(
                f"La fin de semestre doit \u00eatre apr\u00e8s le d\u00e9but "
                f"du semestre {semester.number} "
                f"(planifi\u00e9 le {debut.start_datetime.strftime('%d/%m/%Y')})."
            )

    # 8. Examen apres debut de semestre (verifie seulement si le debut existe deja)
    if event_type in (
        AcademicCalendarEntry.EVENT_EXAM_SESSION,
        AcademicCalendarEntry.EVENT_RETAKE_SESSION,
    ) and semester:
        debut = AcademicCalendarEntry.objects.filter(
            calendar=calendar,
            event_type=AcademicCalendarEntry.EVENT_SEMESTER_START,
            semester=semester,
        ).exclude(status=AcademicCalendarEntry.STATUS_CANCELLED).first()
        if debut and start_datetime.date() < debut.start_datetime.date():
            raise ValidationError(
                f"La session d'examens ne peut pas d\u00e9buter avant le d\u00e9but "
                f"du semestre {semester.number} "
                f"(planifi\u00e9 le {debut.start_datetime.strftime('%d/%m/%Y')})."
            )




_MUTABLE_CAL_STATUS = {
    AcademicCalendar.STATUS_DRAFT,
    AcademicCalendar.STATUS_REJECTED,
}


def _entry_row(entry):
    """Transforme une AcademicCalendarEntry en dict pret pour le template."""
    now = timezone.now()
    is_past = entry.end_datetime < now
    is_active = entry.start_datetime <= now <= entry.end_datetime
    meta = EVENT_META.get(entry.event_type, {
        "icon": "circle-dot",
        "tone": "muted",
        "color_bg": "bg-slate-50",
        "color_text": "text-slate-500",
        "label": entry.event_type,
        "is_blocking": False,
    })
    cal_is_draft = entry.calendar.status in _MUTABLE_CAL_STATUS
    duration_days = (entry.end_datetime.date() - entry.start_datetime.date()).days
    return {
        "entry": entry,
        "icon": meta["icon"],
        "tone": meta["tone"],
        "color_bg": meta["color_bg"],
        "color_text": meta["color_text"],
        "type_label": entry.get_event_type_display(),
        "status_label": entry.get_status_display(),
        "scope_label": entry.get_target_scope_display(),
        "class_label": (
            entry.academic_class.display_name if entry.academic_class else None
        ),
        "semester_label": (
            f"Semestre {entry.semester.number}" if entry.semester else None
        ),
        "duration_days": duration_days,
        "duration_label": (
            "Journee entiere" if duration_days == 0
            else f"{duration_days + 1} jour{'s' if duration_days > 0 else ''}"
        ),
        "is_past": is_past,
        "is_active": is_active,
        "is_upcoming": not is_past and not is_active,
        "can_edit": cal_is_draft,
        "can_delete": cal_is_draft,
    }


def _next_version_for(branch, academic_year):
    """Calcule la prochaine version disponible pour une annee et une annexe."""
    from django.db.models import Max
    result = AcademicCalendar.objects.filter(
        branch=branch, academic_year=academic_year
    ).aggregate(max_v=Max("version"))
    return (result["max_v"] or 0) + 1


def build_director_calendar_context(branch, selected_calendar_id=None, academic_year=None):
    """
    Construit le contexte complet pour la section Calendrier du dashboard directeur.
    Retourne un dict prefixe director_calendar_* pret a etre unpacke dans le contexte.
    """
    from academics.models import AcademicClass, Semester

    # --- Annees academiques ---
    all_years = list(AcademicYear.objects.order_by("-start_date")[:10])
    active_year = academic_year or next((y for y in all_years if y.is_active), None) or (
        all_years[0] if all_years else None
    )

    # --- Tous les calendriers de l'annexe ---
    calendars_queryset = AcademicCalendar.objects.select_related(
        "academic_year", "created_by", "updated_by", "published_by", "revision_of"
    ).filter(branch=branch)
    if academic_year is not None:
        calendars_queryset = calendars_queryset.filter(academic_year=academic_year)
    calendars = list(calendars_queryset.order_by("-academic_year__start_date", "-version"))

    # --- Calendrier selectionne ---
    selected = None
    if selected_calendar_id:
        selected = next((c for c in calendars if c.id == selected_calendar_id), None)
    if selected is None and calendars:
        # Priorite : brouillon actif > valide > publie > plus recent
        for status_pref in (
            AcademicCalendar.STATUS_DRAFT,
            AcademicCalendar.STATUS_REJECTED,
            AcademicCalendar.STATUS_SUBMITTED,
            AcademicCalendar.STATUS_VALIDATED,
            AcademicCalendar.STATUS_PUBLISHED,
        ):
            found = next((c for c in calendars if c.status == status_pref), None)
            if found:
                selected = found
                break
        if selected is None:
            selected = calendars[0]

    # --- Entrees du calendrier selectionne ---
    entries = []
    entry_rows = []
    entry_counts_by_type = {}
    available_classes = []
    available_programmes = []
    available_semesters = []
    missing_key_events = []
    next_version = 1
    upcoming_rows = []
    active_rows = []
    pilotage_alerts = []
    recent_disruptions = []
    recent_disruption_rows = []
    construction_progress = 0
    readiness_checks = []

    if selected:
        entries = list(
            AcademicCalendarEntry.objects.select_related(
                "academic_class",
                "semester",
                "semester__academic_class",
            )
            .filter(calendar=selected)
            .exclude(status=AcademicCalendarEntry.STATUS_ARCHIVED)
            .order_by("start_datetime", "id")
        )
        entry_rows = [_entry_row(e) for e in entries]

        for row in entry_rows:
            t = row["type_label"]
            entry_counts_by_type[t] = entry_counts_by_type.get(t, 0) + 1

        # Classes et semestres disponibles pour le formulaire
        available_classes = list(
            AcademicClass.objects.filter(
                branch=branch,
                academic_year=selected.academic_year,
                is_active=True,
            ).select_related("programme").order_by("name")
        )
        available_programmes = list({
            academic_class.programme_id: academic_class.programme
            for academic_class in available_classes
        }.values())
        available_semesters = list(
            Semester.objects.filter(
                academic_class__branch=branch,
                academic_class__academic_year=selected.academic_year,
            )
            .select_related("academic_class")
            .order_by("academic_class__name", "number")
        )

        # Evenements structurels manquants (guide pour le directeur)
        existing_types = {e.event_type for e in entries}
        KEY_EVENTS = [
            AcademicCalendarEntry.EVENT_ACADEMIC_START,
            AcademicCalendarEntry.EVENT_ACADEMIC_END,
        ]
        missing_key_events = [
            EVENT_META[t]["label"]
            for t in KEY_EVENTS
            if t not in existing_types
        ]

        upcoming_rows = [row for row in entry_rows if row["is_upcoming"]][:5]
        active_rows = [row for row in entry_rows if row["is_active"]]
        recent_disruptions = list(
            AcademicCalendarDisruption.objects.filter(calendar=selected)
            .select_related("reported_by")
            .order_by("-starts_at", "-id")[:3]
        )
        from academics.services.calendar_service import (
            get_calendar_readiness,
            get_disruption_impacts,
        )
        readiness_checks = get_calendar_readiness(selected)
        recent_disruption_rows = [
            {
                "disruption": disruption,
                "impacts": get_disruption_impacts(disruption),
            }
            for disruption in recent_disruptions
        ]
        required_key_event_count = len(KEY_EVENTS)
        completed_key_event_count = required_key_event_count - len(missing_key_events)
        construction_progress = min(
            100,
            round((completed_key_event_count / required_key_event_count) * 45)
            + min(35, len(entries) * 7)
            + (20 if selected.status in {
                AcademicCalendar.STATUS_SUBMITTED,
                AcademicCalendar.STATUS_VALIDATED,
                AcademicCalendar.STATUS_PUBLISHED,
                AcademicCalendar.STATUS_SUPERSEDED,
                AcademicCalendar.STATUS_ARCHIVED,
            } else 0),
        )

        for label in missing_key_events:
            pilotage_alerts.append({
                "tone": "warning",
                "icon": "circle-alert",
                "title": f"{label} manquante",
                "detail": "Ajoutez cette date officielle avant la soumission.",
            })
        for check in readiness_checks:
            if check["level"] == "error":
                tone, icon, title = "danger", "circle-x", "Correction obligatoire"
            elif check["level"] == "warning":
                tone, icon, title = "warning", "triangle-alert", "Point a confirmer"
            else:
                tone, icon, title = "success", "badge-check", "Calendrier coherent"
            pilotage_alerts.append({
                "tone": tone,
                "icon": icon,
                "title": title,
                "detail": check["message"],
            })
        if selected.status == AcademicCalendar.STATUS_REJECTED:
            pilotage_alerts.append({
                "tone": "danger",
                "icon": "rotate-ccw",
                "title": "Calendrier retourne pour correction",
                "detail": selected.rejection_reason,
            })
        elif selected.status == AcademicCalendar.STATUS_SUBMITTED:
            pilotage_alerts.append({
                "tone": "info",
                "icon": "clock-3",
                "title": "En attente de validation",
                "detail": "Le calendrier est verrouille jusqu'a la decision institutionnelle.",
            })
        elif selected.status == AcademicCalendar.STATUS_PUBLISHED:
            pilotage_alerts.append({
                "tone": "success",
                "icon": "badge-check",
                "title": "Version officielle applicable",
                "detail": "Toute modification doit passer par une revision ou un avenant trace.",
            })
        if not available_classes:
            pilotage_alerts.append({
                "tone": "info",
                "icon": "school",
                "title": "Aucune classe active pour cette annee",
                "detail": "Les jalons generaux restent possibles ; les portees classe et semestre apparaitront ensuite.",
            })

        # Prochaine version pour ce couple annee/annexe
        next_version = _next_version_for(branch, selected.academic_year)

    # --- Permissions d'action sur le calendrier selectionne ---
    can_validate = (
        selected is not None
        and selected.status == AcademicCalendar.STATUS_SUBMITTED
        and len(entries) >= 1
    )
    can_publish = (
        selected is not None
        and selected.status == AcademicCalendar.STATUS_VALIDATED
    )
    can_archive = (
        selected is not None
        and selected.status == AcademicCalendar.STATUS_PUBLISHED
    )
    can_add_entry = (
        selected is not None
        and selected.status in _MUTABLE_CAL_STATUS
    )
    can_submit = (
        selected is not None
        and selected.status in _MUTABLE_CAL_STATUS
        and len(entries) >= 1
    )
    can_create_revision = (
        selected is not None
        and selected.status == AcademicCalendar.STATUS_PUBLISHED
    )

    # --- Metadonnees JSON pour Alpine.js ---
    event_meta_json = {
        k: {
            "label": v["label"],
            "icon": v["icon"],
            "tone": v["tone"],
            "force_scope": v["force_scope"] or "",
            "needs_class": v["needs_class"],
            "needs_semester": v["needs_semester"],
            "is_blocking": v["is_blocking"],
            "description": v["description"],
        }
        for k, v in EVENT_META.items()
    }

    # --- Prochaine version globale pour la creation d'un nouveau calendrier ---
    new_cal_next_version = (
        _next_version_for(branch, active_year) if active_year else 1
    )
    calendar_count_by_year = {}
    for calendar in calendars:
        calendar_count_by_year[calendar.academic_year_id] = (
            calendar_count_by_year.get(calendar.academic_year_id, 0) + 1
        )
    academic_year_rows = [
        {
            "year": year,
            "calendar_count": calendar_count_by_year.get(year.id, 0),
            "can_attempt_delete": not year.is_active,
        }
        for year in all_years
    ]

    return {
        "director_all_academic_years": all_years,
        "director_active_academic_year": active_year,
        "director_calendar_academic_year_rows": academic_year_rows,
        "director_academic_calendars": calendars,
        "director_selected_calendar": selected,
        "director_calendar_entries": entry_rows,
        "director_calendar_entry_count": len(entries),
        "director_calendar_construction_progress": construction_progress,
        "director_calendar_upcoming_rows": upcoming_rows,
        "director_calendar_active_rows": active_rows,
        "director_calendar_pilotage_alerts": pilotage_alerts,
        "director_calendar_readiness_checks": readiness_checks,
        "director_calendar_recent_disruptions": recent_disruptions,
        "director_calendar_recent_disruption_rows": recent_disruption_rows,
        "director_calendar_entry_counts_by_type": entry_counts_by_type,
        "director_calendar_can_validate": can_validate,
        "director_calendar_can_submit": can_submit,
        "director_calendar_can_publish": can_publish,
        "director_calendar_can_archive": can_archive,
        "director_calendar_can_add_entry": can_add_entry,
        "director_calendar_can_create_revision": can_create_revision,
        "director_calendar_missing_key_events": missing_key_events,
        "director_calendar_event_type_choices": AcademicCalendarEntry.EVENT_TYPE_CHOICES,
        "director_calendar_event_groups": EVENT_GROUPS,
        "director_calendar_event_meta_json": json.dumps(
            event_meta_json,
            ensure_ascii=False,
        ),
        "director_calendar_available_classes": available_classes,
        "director_calendar_available_programmes": available_programmes,
        "director_calendar_available_semesters": available_semesters,
        "director_calendar_no_semesters": selected is not None and not available_semesters,
        "director_calendar_no_classes": selected is not None and not available_classes,
        "director_calendar_next_version": new_cal_next_version,
    }
