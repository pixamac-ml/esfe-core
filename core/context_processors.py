import json

from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError

from core.models import Institution, SiteConfiguration


def _absolute_media_url(path: str) -> str:
    if not path:
        return ""
    return f"{settings.BASE_URL}{path}"


def seo_defaults(request):
    site_name = "ESFE"
    default_description = (
        "ESFE - Etablissement superieur de formation en sciences de la sante, "
        "avec des programmes professionnalisants et un accompagnement de qualite."
    )
    default_image = ""

    try:
        institution = Institution.objects.filter(is_active=True).first()
        site_config = SiteConfiguration.objects.first()
    except (ProgrammingError, OperationalError):
        institution = None
        site_config = None

    if institution:
        site_name = institution.short_name or institution.name or site_name
        default_description = (
            f"{institution.name} - Formation superieure en sciences de la sante au Mali, "
            "avec une vision d'excellence academique et d'employabilite."
        )

    if site_config and site_config.site_logo:
        default_image = _absolute_media_url(site_config.site_logo.url)

    canonical_url = f"{settings.BASE_URL}{request.path}"
    robots_value = "noindex, nofollow" if settings.DEBUG else "index, follow, max-image-preview:large"

    organization_schema = {
        "@context": "https://schema.org",
        "@type": "EducationalOrganization",
        "name": site_name,
        "url": settings.BASE_URL,
    }

    if institution:
        organization_schema["email"] = institution.email
        organization_schema["telephone"] = institution.phone
        organization_schema["address"] = {
            "@type": "PostalAddress",
            "streetAddress": institution.address,
            "addressLocality": institution.city,
            "addressCountry": institution.country,
        }

    if default_image:
        organization_schema["logo"] = default_image

    website_schema = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": site_name,
        "url": settings.BASE_URL,
    }

    return {
        "seo_site_name": site_name,
        "seo_default_description": default_description,
        "seo_default_image": default_image,
        "canonical_url": canonical_url,
        "meta_robots": robots_value,
        "organization_schema_json": json.dumps(organization_schema, ensure_ascii=True),
        "website_schema_json": json.dumps(website_schema, ensure_ascii=True),
    }

