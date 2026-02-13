from django_components import component

@component.register("footer_cta")
class FooterCTA(component.Component):
    template_name = "layout/footer_cta/footer_cta.html"

    def get_context_data(
        self,
        title: str,
        subtitle: str,
        cta_label: str,
        cta_url: str,
    ):
        return {
            "title": title,
            "subtitle": subtitle,
            "cta_label": cta_label,
            "cta_url": cta_url,
        }
