from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.contrib.auth import password_validation
from django.core.validators import validate_email
from django.urls import reverse

from admissions.models import CandidatureDocument
from accounts.models import Profile, UserPreference
from portal.models import AccountSupportState
from portal.student.widgets.academics import get_student_academic_snapshot


EDITABLE_PROFILE_FIELDS = {"email", "phone"}
EDITABLE_ACCOUNT_FIELDS = {"location", "address", "bio"}
PREFERENCE_FIELDS = {
    "notify_email",
    "notify_in_app",
    "notify_sms",
    "ui_sidebar_collapsed",
    "ui_compact_mode",
    "ui_autorefresh",
}


@dataclass
class StudentProfileContext:
    student: object | None
    candidature: object | None
    enrollment: object | None


def _get_profile_context(user) -> StudentProfileContext:
    snapshot = get_student_academic_snapshot(user)
    student = snapshot["student"]
    candidature = getattr(getattr(student, "inscription", None), "candidature", None) if student else None
    enrollment = snapshot["academic_enrollment"]
    return StudentProfileContext(
        student=student,
        candidature=candidature,
        enrollment=enrollment,
    )


def get_student_documents(user):
    context = _get_profile_context(user)
    candidature = context.candidature
    if candidature is None:
        return []

    required_links = list(
        candidature.programme.required_documents.select_related("document").all()
    )
    uploaded_by_document_id = {
        document.document_type_id: document
        for document in candidature.documents.select_related("document_type").all()
    }

    documents = []
    for link in required_links:
        uploaded = uploaded_by_document_id.get(link.document_id)
        if uploaded is None:
            status = "manquant"
        elif uploaded.is_valid or uploaded.is_validated:
            status = "valide"
        else:
            status = "en_attente"
        documents.append(
            {
                "id": link.document_id,
                "name": link.document.name,
                "description": link.document.description,
                "is_mandatory": link.document.is_mandatory,
                "status": status,
                "status_label": {
                    "manquant": "Manquant",
                    "en_attente": "En attente",
                    "valide": "Valide",
                }[status],
                "file_url": uploaded.file.url if uploaded and uploaded.file else "",
                "uploaded_at": uploaded.uploaded_at if uploaded else None,
                "admin_note": uploaded.admin_note if uploaded else "",
            }
        )
    return documents


def get_missing_fields(user):
    context = _get_profile_context(user)
    candidature = context.candidature
    enrollment = context.enrollment
    if candidature is None:
        return ["profil_etudiant_absent"]

    missing = []
    required_field_map = {
        "email": candidature.email,
        "telephone": candidature.phone,
        "date_naissance": candidature.birth_date,
        "lieu_naissance": candidature.birth_place,
    }
    for field_name, value in required_field_map.items():
        if not value:
            missing.append(field_name)

    if enrollment is None:
        missing.append("affectation_academique")

    missing.extend(
        f"document:{document['name']}"
        for document in get_student_documents(user)
        if document["status"] == "manquant" and document["is_mandatory"]
    )
    return missing


def get_profile_completion(user):
    context = _get_profile_context(user)
    candidature = context.candidature
    if candidature is None:
        return {
            "percent": 0,
            "missing_fields": ["profil_etudiant_absent"],
            "is_complete": False,
            "alert_level": "critical",
            "message": "Votre profil etudiant n'est pas encore completement rattache au systeme.",
        }

    checks = [
        bool(candidature.first_name),
        bool(candidature.last_name),
        bool(candidature.email),
        bool(candidature.phone),
        bool(candidature.birth_date),
        bool(candidature.birth_place),
        bool(context.student and context.student.matricule),
        bool(context.enrollment),
    ]
    documents = get_student_documents(user)
    mandatory_documents = [document for document in documents if document["is_mandatory"]]
    if mandatory_documents:
        checks.extend(document["status"] != "manquant" for document in mandatory_documents)

    completed = sum(1 for item in checks if item)
    percent = round((completed / len(checks)) * 100) if checks else 0
    missing_fields = get_missing_fields(user)
    if percent >= 100:
        alert_level = "success"
        message = "Votre profil est complet."
    elif percent >= 70:
        alert_level = "warning"
        message = "Votre profil est partiellement complet. Quelques elements restent a finaliser."
    else:
        alert_level = "critical"
        message = "Votre profil est incomplet. Des informations ou documents obligatoires manquent."
    return {
        "percent": percent,
        "missing_fields": missing_fields,
        "is_complete": percent == 100 and not missing_fields,
        "alert_level": alert_level,
        "message": message,
    }


def get_profile_data(user):
    snapshot = get_student_academic_snapshot(user)
    context = _get_profile_context(user)
    student = context.student
    candidature = context.candidature
    enrollment = context.enrollment
    completion = get_profile_completion(user)
    documents = get_student_documents(user)
    profile, _created = Profile.objects.get_or_create(user=user)
    preference, _preference_created = UserPreference.objects.get_or_create(user=user)
    support_state = AccountSupportState.objects.filter(user=user).first()

    account_center = {
        "full_name": user.get_full_name() or user.username,
        "email": user.email or "",
        "phone": profile.phone or "",
        "location": profile.location or "",
        "address": profile.address or "",
        "avatar_url": profile.avatar_url,
        "bio": profile.bio or "",
        "main_domain": profile.main_domain or "",
        "notify_email": preference.notify_email,
        "notify_in_app": preference.notify_in_app,
        "notify_sms": preference.notify_sms,
        "ui_compact_mode": preference.ui_compact_mode,
        "ui_sidebar_collapsed": preference.ui_sidebar_collapsed,
        "ui_autorefresh": preference.ui_autorefresh,
        "must_change_password": getattr(support_state, "must_change_password", False),
        "is_blocked": getattr(support_state, "is_blocked", False),
        "is_suspended": getattr(support_state, "is_suspended", False),
        "profile_url": reverse("accounts:profile"),
        "edit_profile_url": reverse("accounts:edit_profile"),
        "edit_preferences_url": reverse("accounts:edit_preferences"),
        "password_change_url": reverse("password_change"),
    }

    if student is None or candidature is None:
        return {
            "editable_fields": {},
            "readonly_fields": {},
            "academic_fields": {},
            "documents": [],
            "completion": completion,
            "alerts": completion["missing_fields"],
            "account_center": account_center,
        }

    return {
        "editable_fields": {
            "email": candidature.email or "",
            "phone": candidature.phone or "",
        },
        "readonly_fields": {
            "full_name": student.full_name,
            "matricule": student.matricule,
            "birth_date": candidature.birth_date,
            "birth_place": candidature.birth_place,
            "photo_url": None,
        },
        "academic_fields": {
            "formation": getattr(candidature.programme, "title", "Non disponible"),
            "classroom": getattr(getattr(enrollment, "academic_class", None), "display_name", "Non disponible") if enrollment else "Non disponible",
            "academic_year": getattr(snapshot["academic_year"], "name", "Non disponible"),
            "enrollment_status": getattr(getattr(student, "inscription", None), "get_status_display", lambda: "Non disponible")(),
            "academic_status": snapshot["academic_status_message"],
            "annexe": getattr(candidature.branch, "name", "Non disponible"),
        },
        "documents": documents,
        "completion": completion,
        "alerts": completion["missing_fields"],
        "account_center": account_center,
    }


def update_editable_fields(user, data):
    context = _get_profile_context(user)
    candidature = context.candidature
    if candidature is None:
        raise ValidationError("Aucun profil etudiant editable n'est disponible.")

    cleaned = {}
    errors = {}
    for field in EDITABLE_PROFILE_FIELDS:
        if field not in data:
            continue
        value = (data.get(field) or "").strip()
        cleaned[field] = value

    if "email" in cleaned:
        if not cleaned["email"]:
            errors["email"] = "L'email est obligatoire."
        else:
            try:
                validate_email(cleaned["email"])
            except ValidationError:
                errors["email"] = "Adresse email invalide."

    if "phone" in cleaned and not cleaned["phone"]:
        errors["phone"] = "Le telephone est obligatoire."

    if errors:
        raise ValidationError(errors)

    if "email" in cleaned:
        candidature.email = cleaned["email"]
        user.email = cleaned["email"]
        user.save(update_fields=["email"])
    if "phone" in cleaned:
        candidature.phone = cleaned["phone"]
        profile, _created = Profile.objects.get_or_create(user=user)
        profile.phone = cleaned["phone"]
        profile.save(update_fields=["phone", "updated_at"])

    candidature.save(update_fields=["email", "phone", "updated_at"])
    return get_profile_data(user)


def update_account_center(user, data):
    profile, _created = Profile.objects.get_or_create(user=user)
    cleaned = {field: (data.get(field) or "").strip() for field in EDITABLE_ACCOUNT_FIELDS}
    profile.location = cleaned["location"]
    profile.address = cleaned["address"]
    profile.bio = cleaned["bio"]
    profile.save(update_fields=["location", "address", "bio", "updated_at"])
    return get_profile_data(user)


def update_account_preferences(user, data):
    preference, _created = UserPreference.objects.get_or_create(user=user)
    for field in PREFERENCE_FIELDS:
        setattr(preference, field, data.get(field) == "on")
    preference.save(update_fields=[*PREFERENCE_FIELDS, "updated_at"])
    return get_profile_data(user)


def update_account_password(user, data):
    old_password = data.get("old_password") or ""
    new_password = data.get("new_password") or ""
    confirm_password = data.get("confirm_password") or ""
    errors = {}

    if not user.check_password(old_password):
        errors["old_password"] = "Mot de passe actuel incorrect."
    if new_password != confirm_password:
        errors["confirm_password"] = "La confirmation ne correspond pas."
    try:
        password_validation.validate_password(new_password, user)
    except ValidationError as exc:
        errors["new_password"] = exc.messages

    if errors:
        raise ValidationError(errors)

    user.set_password(new_password)
    user.save(update_fields=["password"])
    support_state = AccountSupportState.objects.filter(user=user).first()
    if support_state and support_state.must_change_password:
        support_state.must_change_password = False
        support_state.save(update_fields=["must_change_password", "updated_at"])
    return get_profile_data(user)


def handle_document_upload(user, file, document_type_id):
    context = _get_profile_context(user)
    candidature = context.candidature
    if candidature is None:
        raise ValidationError("Aucun dossier etudiant disponible pour televersement.")

    if not file:
        raise ValidationError({"file": "Aucun fichier n'a ete fourni."})

    document_type = candidature.programme.required_documents.select_related("document").filter(
        document_id=document_type_id
    ).first()
    if document_type is None:
        raise ValidationError({"document_type": "Ce document n'est pas attendu pour cette formation."})

    upload, created = CandidatureDocument.objects.get_or_create(
        candidature=candidature,
        document_type=document_type.document,
        defaults={
            "file": file,
            "is_valid": False,
            "is_validated": False,
        },
    )
    if not created:
        upload.file = file
        upload.is_valid = False
        upload.is_validated = False
        upload.admin_note = ""
        upload.save(update_fields=["file", "is_valid", "is_validated", "admin_note"])
    return get_profile_data(user)
