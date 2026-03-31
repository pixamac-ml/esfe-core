from django.urls import NoReverseMatch, reverse
from django.db.utils import OperationalError, ProgrammingError
from django_components import component

from branches.models import Branch
from formations.models import Programme


@component.register("footer")
class Footer(component.Component):
    template_name = "layout/footer/footer.html"

    @staticmethod
    def _safe_reverse(name: str, fallback: str = "#") -> str:
        try:
            return reverse(name)
        except NoReverseMatch:
            return fallback

    def _default_navigation(self):
        formations_url = self._safe_reverse("formations:list")
        return [
            {
                "title": "Explorer",
                "links": [
                    {"label": "Accueil", "url": self._safe_reverse("core:home")},
                    {"label": "A propos", "url": self._safe_reverse("core:about")},
                    {"label": "Contact", "url": self._safe_reverse("core:contact")},
                    {"label": "Plan du site", "url": self._safe_reverse("core:sitemap")},
                ],
            },
            {
                "title": "Formations",
                "links": [
                    {"label": "Tous les programmes", "url": formations_url},
                    {"label": "Licence", "url": f"{formations_url}?cycle=licence"},
                    {"label": "Master", "url": f"{formations_url}?cycle=master"},
                    {"label": "BTS / DTS", "url": f"{formations_url}?cycle=bts"},
                ],
            },
            {
                "title": "Ressources",
                "links": [
                    {"label": "Actualites", "url": self._safe_reverse("news:list")},
                    {"label": "Resultats", "url": self._safe_reverse("news:result_list")},
                    {"label": "Blog", "url": self._safe_reverse("blog:article_list")},
                    {"label": "Communaute", "url": self._safe_reverse("community:topic_list")},
                ],
            },
            {
                "title": "Admission",
                "links": [
                    {"label": "Demarrer ma candidature", "url": formations_url},
                    {"label": "Calendrier des rentrees", "url": self._safe_reverse("news:event_list")},
                    {"label": "FAQ et entraide", "url": self._safe_reverse("community:topic_list")},
                    {"label": "Parler a un conseiller", "url": self._safe_reverse("core:contact")},
                ],
            },
        ]

    def _default_legal_links(self):
        return [
            {"label": "Mentions legales", "url": self._safe_reverse("core:legal_notice")},
            {"label": "Confidentialite", "url": self._safe_reverse("core:privacy_policy")},
            {"label": "Conditions d'utilisation", "url": self._safe_reverse("core:terms_of_service")},
            {"label": "Plan du site", "url": self._safe_reverse("core:sitemap")},
        ]

    @staticmethod
    def _normalize_phone_for_wa(phone: str) -> str:
        return "".join(ch for ch in (phone or "") if ch.isdigit())

    def _default_social_links(self, phone: str = ""):
        wa_phone = self._normalize_phone_for_wa(phone) or "22370000000"
        return [
            {"label": "Facebook", "url": "#", "icon": "facebook"},
            {"label": "Instagram", "url": "#", "icon": "instagram"},
            {"label": "LinkedIn", "url": "#", "icon": "linkedin"},
            {"label": "YouTube", "url": "#", "icon": "youtube"},
            {"label": "WhatsApp", "url": f"https://wa.me/{wa_phone}", "icon": "whatsapp"},
        ]

    @staticmethod
    def _default_annexes():
        try:
            return list(
                Branch.objects.filter(is_active=True)
                .values_list("name", flat=True)[:10]
            )
        except (ProgrammingError, OperationalError):
            return []

    @staticmethod
    def _default_stats():
        try:
            return [
                {"label": "Formations", "value": Programme.objects.filter(is_active=True).count()},
                {"label": "Campus", "value": Branch.objects.filter(is_active=True).count()},
            ]
        except (ProgrammingError, OperationalError):
            return []

    def get_context_data(
            self,
            # Identité
            site_name: str = "ESFE",
            site_slogan: str = "Excellence • Innovation • Engagement",
            site_description: str = "",
            logo_url: str = None,

            # Navigation (liste de dictionnaires avec catégorie)
            footer_navigation: list = None,

            # Contact
            footer_contact: dict = None,

            # Horaires
            opening_hours: str = "Lun-Ven : 8h00 - 17h00",

            # Réseaux sociaux
            social_links: list = None,

            # Annexes/Implantations
            annexes: list = None,

            # Liens légaux
            footer_legal_links: list = None,

            # Stats (optionnel)
            stats: list = None,

            # CTA
            cta: dict = None,
    ):
        # Valeurs par défaut
        if footer_navigation is None:
            footer_navigation = self._default_navigation()
        if not isinstance(footer_contact, dict):
            footer_contact = {}
        if social_links is None:
            social_links = self._default_social_links(footer_contact.get("phone", ""))
        if annexes is None:
            annexes = self._default_annexes()
        if footer_legal_links is None:
            footer_legal_links = self._default_legal_links()
        if stats is None:
            stats = self._default_stats()
        if cta is None:
            cta = {
                "title": "Pret a rejoindre ESFE ?",
                "description": "Nos equipes vous accompagnent de la candidature jusqu'a l'inscription finale.",
                "button_label": "Candidater maintenant",
                "button_url": self._safe_reverse("formations:list"),
            }

        return {
            "site_name": site_name,
            "site_slogan": site_slogan,
            "site_description": site_description,
            "logo_url": logo_url,
            "navigation": footer_navigation,
            "contact": footer_contact,
            "opening_hours": opening_hours,
            "social_links": social_links,
            "annexes": annexes,
            "legal_links": footer_legal_links,
            "stats": stats,
            "cta": cta,
        }