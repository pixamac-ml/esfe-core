from django_components import component

@component.register("footer")
class Footer(component.Component):
    template_name = "layout/footer/footer.html"

    def get_context_data(
        self,
        site_name: str,
        site_description: str,
        footer_navigation: list,
        footer_contact: dict,
        footer_legal_links: list,
    ):
        return {
            "institution_name": site_name,
            "description": site_description,
            "navigation": footer_navigation,
            "contact": footer_contact,
            "legal_links": footer_legal_links,
        }
