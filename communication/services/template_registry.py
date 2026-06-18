from django.conf import settings


EMAIL_TEMPLATE_REGISTRY = {
    "candidature_submitted": {
        "html_template": "emails/admissions/candidate_submitted.html",
    },
    "candidature_accepted": {
        "html_template": "emails/admissions/candidate_accepted.html",
    },
    "candidature_rejected": {
        "html_template": "emails/admissions/candidate_rejected.html",
    },
    "candidature_under_review": {
        "html_template": "emails/admissions/candidate_under_review.html",
    },
    "candidature_accepted_with_reserve": {
        "html_template": "emails/admissions/candidate_accepted_with_reserve.html",
    },
    "candidature_to_complete": {
        "html_template": "emails/admissions/candidate_to_complete.html",
    },
    "document_missing": {
        "html_template": "emails/admissions/missing_documents.html",
    },
    "student_welcome_credentials": {
        "html_template": "emails/onboarding/account_created.html",
        "text_template": "emails/student_welcome.txt",
    },
    "first_payment_validated": {
        "html_template": "emails/payments/first_payment_validated.html",
        "text_template": "emails/payment_confirmation.txt",
    },
    "receipt_generated": {
        "html_template": "emails/base_communication.html",
    },
    "payment_receipt_email": {
        "html_template": "emails/base_communication.html",
    },
    "diploma_ready": {
        "html_template": "emails/academics/diploma_ready.html",
    },
}

RESERVED_METADATA_KEYS = {
    "attachments",
    "context",
    "fallback_text",
    "html_template",
    "preheader",
    "template_key",
    "text_template",
}


def _flatten_metadata_context(metadata):
    base_context = {}
    for key, value in metadata.items():
        if key in RESERVED_METADATA_KEYS:
            continue
        base_context[key] = value
    base_context.update(metadata.get("context") or {})
    return base_context


def build_fallback_text(*, title, body, context):
    lines = [title or "Communication ESFE"]
    if body:
        lines.extend(["", body])

    for label, key in (
        ("Reference", "reference"),
        ("Reference dossier", "candidate_reference"),
        ("Montant", "payment_amount"),
        ("Recu", "receipt_number"),
        ("Lien dossier", "public_link"),
        ("Lien recu", "receipt_url"),
        ("Connexion", "login_url"),
        ("Support", "support_email"),
    ):
        value = context.get(key)
        if value:
            lines.append(f"{label}: {value}")

    return "\n".join(lines).strip()


def resolve_email_configuration(*, event_type, title, body, metadata):
    resolved_metadata = dict(metadata or {})
    template_key = resolved_metadata.get("template_key") or event_type
    registry_entry = EMAIL_TEMPLATE_REGISTRY.get(template_key, {})
    html_template = resolved_metadata.get("html_template") or registry_entry.get("html_template") or "emails/base_communication.html"
    text_template = resolved_metadata.get("text_template") or registry_entry.get("text_template")
    context = _flatten_metadata_context(resolved_metadata)

    context.setdefault("title", title)
    context.setdefault("message", body)
    context.setdefault("preheader", resolved_metadata.get("preheader") or body)
    context.setdefault("support_email", getattr(settings, "DEFAULT_FROM_EMAIL", "contact@esfe-mali.org"))

    fallback_text = resolved_metadata.get("fallback_text") or build_fallback_text(
        title=title,
        body=body,
        context=context,
    )

    return {
        "template_key": template_key,
        "html_template": html_template,
        "text_template": text_template,
        "context": context,
        "fallback_text": fallback_text,
        "attachments": resolved_metadata.get("attachments") or [],
    }
