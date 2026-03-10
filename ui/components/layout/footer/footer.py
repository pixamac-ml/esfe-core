from django_components import component


@component.register("footer")
class Footer(component.Component):
    template_name = "layout/footer/footer.html"

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
    ):
        # Valeurs par défaut
        if footer_navigation is None:
            footer_navigation = []
        if social_links is None:
            social_links = []
        if annexes is None:
            annexes = []
        if footer_legal_links is None:
            footer_legal_links = []
        if footer_contact is None:
            footer_contact = {}
        if stats is None:
            stats = []

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
        }