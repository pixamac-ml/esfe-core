import json
from urllib.parse import parse_qs, urlparse

from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.core.exceptions import ValidationError

from django.db.models import Prefetch
from django.views.decorators.http import require_POST

from academics.models import AcademicEnrollment, EC, ECChapter, ECContent, StudentContentProgress
from portal.permissions import role_required

from .services import get_student_dashboard_data
from .profile_service import (
    get_profile_data,
    handle_document_upload,
    update_editable_fields,
)
from .widgets.profile import get_profile_widget
from .widgets.academics import get_academics_widget, get_student_academic_snapshot
from .widgets.finance import get_finance_widget
from .widgets.notifications import get_notifications_widget


def _academic_chapters_available():
    return "academics_ecchapter" in connection.introspection.table_names()


def _content_prefetch():
    return Prefetch(
        "contents",
        queryset=ECContent.objects.filter(is_active=True).order_by("order", "id"),
    )


def _get_video_embed_url(video_url: str) -> str:
    if not video_url:
        return ""
    parsed = urlparse(video_url)
    host = (parsed.netloc or "").lower()

    if "youtube.com" in host:
        query = parse_qs(parsed.query)
        video_id = (query.get("v") or [""])[0]
        if video_id:
            return f"https://www.youtube.com/embed/{video_id}"
        if "/embed/" in parsed.path:
            return video_url
    if "youtu.be" in host:
        video_id = parsed.path.strip("/")
        if video_id:
            return f"https://www.youtube.com/embed/{video_id}"
    if "vimeo.com" in host:
        video_id = parsed.path.strip("/")
        if video_id.isdigit():
            return f"https://player.vimeo.com/video/{video_id}"
    return ""


def _content_progress_defaults(content):
    if content.content_type == ECContent.CONTENT_TYPE_TEXT:
        return {"initial_progress": 60, "completion_hint": "Lecture du texte puis validation manuelle."}
    if content.content_type == ECContent.CONTENT_TYPE_PDF:
        return {"initial_progress": 35, "completion_hint": "Consultation du support PDF."}
    if content.content_type in {ECContent.CONTENT_TYPE_DOC, ECContent.CONTENT_TYPE_EXCEL, ECContent.CONTENT_TYPE_PPT}:
        return {"initial_progress": 25, "completion_hint": "Ouverture du document bureautique."}
    if content.content_type == ECContent.CONTENT_TYPE_IMAGE:
        return {"initial_progress": 70, "completion_hint": "Consultation du visuel pedagogique."}
    if content.content_type == ECContent.CONTENT_TYPE_VIDEO:
        return {"initial_progress": 15, "completion_hint": "Progression mise a jour pendant la lecture video."}
    if content.content_type == ECContent.CONTENT_TYPE_AUDIO:
        return {"initial_progress": 10, "completion_hint": "Progression mise a jour pendant l'ecoute audio."}
    return {"initial_progress": 20, "completion_hint": "Consultation du contenu."}


def _get_student_ec_queryset(enrollment):
    if enrollment is None:
        return EC.objects.none()

    queryset = (
        EC.objects.select_related(
            "ue",
            "ue__semester",
            "ue__semester__academic_class",
        )
        .filter(ue__semester__academic_class=enrollment.academic_class)
        .order_by("ue__semester__number", "ue__code", "id")
    )

    if _academic_chapters_available():
        queryset = queryset.prefetch_related(
            Prefetch(
                "chapters",
                queryset=ECChapter.objects.prefetch_related(_content_prefetch()).order_by("order", "id"),
            )
        )

    return queryset


def _prepare_chapter_contents(request, user, chapters):
    content_ids = [
        content.id
        for chapter in chapters
        for content in chapter.contents.all()
    ]
    progress_map = {
        entry.content_id: entry
        for entry in StudentContentProgress.objects.filter(
            student=user,
            content_id__in=content_ids,
        )
    }

    for chapter in chapters:
        chapter.active_contents = list(chapter.contents.all())
        chapter.active_content_count = len(chapter.active_contents)
        for content in chapter.active_contents:
            progress_entry = progress_map.get(content.id)
            content.student_progress_percent = progress_entry.progress_percent if progress_entry else 0
            content.student_is_completed = progress_entry.is_completed if progress_entry else False
            content.student_last_position = progress_entry.last_position if progress_entry else 0
            content.absolute_file_url = request.build_absolute_uri(content.file.url) if content.file else ""
            defaults = _content_progress_defaults(content)
            content.initial_progress_step = defaults["initial_progress"]
            content.completion_hint = defaults["completion_hint"]
            content.embed_video_url = _get_video_embed_url(content.video_url or "")
            content.preview_as_media = content.content_type in {
                ECContent.CONTENT_TYPE_AUDIO,
                ECContent.CONTENT_TYPE_IMAGE,
            }
            content.document_like = content.content_type in {
                ECContent.CONTENT_TYPE_DOC,
                ECContent.CONTENT_TYPE_EXCEL,
                ECContent.CONTENT_TYPE_PPT,
            }
            content.preview_with_iframe = bool(content.embed_video_url) or content.content_type == ECContent.CONTENT_TYPE_PDF
            content.has_inline_preview = (
                (content.content_type == ECContent.CONTENT_TYPE_VIDEO and bool(content.embed_video_url))
                or (content.content_type == ECContent.CONTENT_TYPE_AUDIO and bool(content.file))
                or (content.content_type == ECContent.CONTENT_TYPE_IMAGE and bool(content.file))
                or (content.content_type == ECContent.CONTENT_TYPE_PDF and bool(content.file))
                or (content.content_type == ECContent.CONTENT_TYPE_TEXT and bool((content.text_content or "").strip()))
            )
            content.has_accessible_source = bool(content.file or content.video_url or (content.text_content or "").strip())
            content.has_broken_source = not content.has_accessible_source
            content.source_label = {
                ECContent.CONTENT_TYPE_PDF: "Support PDF",
                ECContent.CONTENT_TYPE_VIDEO: "Video",
                ECContent.CONTENT_TYPE_DOC: "Document Word",
                ECContent.CONTENT_TYPE_EXCEL: "Fichier Excel",
                ECContent.CONTENT_TYPE_PPT: "Presentation",
                ECContent.CONTENT_TYPE_IMAGE: "Image",
                ECContent.CONTENT_TYPE_AUDIO: "Audio",
                ECContent.CONTENT_TYPE_TEXT: "Texte",
            }.get(content.content_type, "Contenu")
            if content.content_type == ECContent.CONTENT_TYPE_VIDEO and not content.embed_video_url and content.video_url:
                content.preview_notice = "La video ne peut pas etre integree ici. Utilisez le lien d'ouverture."
            elif content.document_like and content.file:
                content.preview_notice = "Apercu integre non disponible pour ce format. Ouvrez le document dans un nouvel onglet."
            elif content.has_broken_source:
                content.preview_notice = "La ressource source est indisponible ou incomplete."
            else:
                content.preview_notice = ""

    return chapters


@login_required
@role_required("student")
def dashboard(request):
    context = get_student_dashboard_data(request.user)
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
def settings_partial(request):
    context = get_profile_data(request.user)
    return render(request, "portal/student/partials/settings_student.html", context)


@login_required
@role_required("student")
def notifications_partial(request):
    context = get_notifications_widget(request.user)
    return render(request, "portal/student/partials/notifications.html", context)


@login_required
@role_required("student")
def courses_partial(request):
    context = get_student_dashboard_data(request.user)
    return render(request, "portal/student/partials/courses_student.html", context)


@login_required
@role_required("student")
def messages_partial(request):
    context = get_student_dashboard_data(request.user)
    return render(request, "portal/student/partials/messages_student.html", context)


@login_required
@role_required("student")
def timetable_partial(request):
    context = get_student_dashboard_data(request.user)
    return render(request, "portal/student/partials/calendar_student.html", context)


@login_required
@role_required("student")
def student_courses(request):
    academic_snapshot = get_student_academic_snapshot(request.user)
    enrollment = academic_snapshot["academic_enrollment"]

    ec_rows = []
    if enrollment is not None:
        ecs = _get_student_ec_queryset(enrollment)
        for ec in ecs:
            if _academic_chapters_available():
                content_count = sum(chapter.contents.count() for chapter in ec.chapters.all())
            else:
                content_count = 0
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
            "academic_status": academic_snapshot["academic_status"],
            "academic_status_message": academic_snapshot["academic_status_message"],
            "ec_rows": ec_rows,
        },
    )


@login_required
@role_required("student")
def ec_detail(request, ec_id):
    academic_snapshot = get_student_academic_snapshot(request.user)
    enrollment = get_object_or_404(
        AcademicEnrollment.objects.filter(pk=getattr(academic_snapshot["academic_enrollment"], "pk", None)),
    )

    ec_queryset = EC.objects.select_related(
        "ue",
        "ue__semester",
        "ue__semester__academic_class",
    )
    if _academic_chapters_available():
        ec_queryset = ec_queryset.prefetch_related(
            Prefetch(
                "chapters",
                queryset=ECChapter.objects.prefetch_related(_content_prefetch()).order_by("order", "id"),
            )
        )

    ec = get_object_or_404(
        ec_queryset,
        pk=ec_id,
        ue__semester__academic_class=enrollment.academic_class,
    )

    chapters = list(ec.chapters.all()) if _academic_chapters_available() else []
    _prepare_chapter_contents(request, request.user, chapters)

    context = {
        "page_title": ec.title,
        "subtitle": "Contenus lies a cette matiere.",
        "enrollment": enrollment,
        "ec": ec,
        "chapters_available": _academic_chapters_available(),
        "chapters": chapters,
    }

    template_name = (
        "portal/student/partials/ec_detail_panel.html"
        if request.GET.get("partial") == "1"
        else "portal/student/ec_detail.html"
    )
    return render(request, template_name, context)


@login_required
@role_required("student")
@require_POST
def update_content_progress(request, content_id):
    academic_snapshot = get_student_academic_snapshot(request.user)
    enrollment = get_object_or_404(
        AcademicEnrollment.objects.filter(pk=getattr(academic_snapshot["academic_enrollment"], "pk", None)),
    )
    content = get_object_or_404(
        ECContent,
        pk=content_id,
        is_active=True,
        chapter__ec__ue__semester__academic_class=enrollment.academic_class,
    )

    payload = json.loads(request.body or "{}")
    progress_percent = int(payload.get("progress_percent", 0) or 0)
    last_position = int(payload.get("last_position", 0) or 0)
    is_completed = bool(payload.get("is_completed", False))

    progress_percent = max(0, min(progress_percent, 100))
    if is_completed:
        progress_percent = 100

    progress, _ = StudentContentProgress.objects.get_or_create(
        student=request.user,
        content=content,
        defaults={
            "progress_percent": progress_percent,
            "last_position": max(0, last_position),
            "is_completed": is_completed,
        },
    )

    if progress.progress_percent < progress_percent:
        progress.progress_percent = progress_percent
    progress.last_position = max(progress.last_position, max(0, last_position))
    progress.is_completed = progress.is_completed or is_completed or progress.progress_percent >= 100
    if progress.is_completed:
        progress.progress_percent = 100
    progress.save()

    return JsonResponse(
        {
            "ok": True,
            "progress_percent": progress.progress_percent,
            "is_completed": progress.is_completed,
        }
    )


@login_required
@role_required("student")
@require_POST
def update_settings_profile(request):
    try:
        context = update_editable_fields(
            request.user,
            {
                "email": request.POST.get("email", ""),
                "phone": request.POST.get("phone", ""),
            },
        )
        context["form_success"] = "Informations mises a jour."
        context["form_errors"] = {}
    except ValidationError as exc:
        context = get_profile_data(request.user)
        context["form_success"] = ""
        context["form_errors"] = getattr(exc, "message_dict", {"__all__": exc.messages})
    return render(request, "portal/student/partials/settings_student.html", context)


@login_required
@role_required("student")
@require_POST
def upload_settings_document(request):
    try:
        context = handle_document_upload(
            request.user,
            request.FILES.get("file"),
            int(request.POST.get("document_type_id") or 0),
        )
        context["form_success"] = "Document televerse avec succes."
        context["form_errors"] = {}
    except (ValidationError, ValueError) as exc:
        context = get_profile_data(request.user)
        if isinstance(exc, ValidationError):
            context["form_errors"] = getattr(exc, "message_dict", {"__all__": exc.messages})
        else:
            context["form_errors"] = {"document_type_id": ["Type de document invalide."]}
        context["form_success"] = ""
    return render(request, "portal/student/partials/settings_student.html", context)
