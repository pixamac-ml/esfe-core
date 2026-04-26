from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from admissions.models import CandidatureDocument
from portal.student.widgets.academics import get_student_academic_snapshot


EDITABLE_PROFILE_FIELDS = {"email", "phone"}


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

    if student is None or candidature is None:
        return {
            "editable_fields": {},
            "readonly_fields": {},
            "academic_fields": {},
            "documents": [],
            "completion": completion,
            "alerts": completion["missing_fields"],
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

    candidature.save(update_fields=["email", "phone", "updated_at"])
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
