from django_components import component


@component.register("portal_salary_section")
class PortalSalarySection(component.Component):
    """
    Section salaire/honoraires universelle — utilisable dans tous les portails.

    salary_type:
        "salaire"   → fiche de paie mensuelle (staff : secrétaire, gestionnaire, etc.)
        "honoraire" → bordereau d'heures (enseignant)

    Params communs:
        panel_id        – id HTML du panneau (ex: "secretary-panel-salary")
        active_section  – section active courante (pour affichage conditionnel legacy)
        salary_type     – "salaire" | "honoraire"
        salary_base     – montant de base mensuel
        latest_entry    – dict {net_salary, remaining_salary, status, period_month}
        entries         – liste de fiches / bordereaux
        entries_page    – objet Page Django (optionnel, pour pagination)
        recent_payments – liste de paiements récents [{label, date, montant}]
        download_url_name – nom d'URL Django pour télécharger un PDF (ex: 'accounts:honorarium_download')
        hx_target       – sélecteur CSS pour la pagination HTMX
    """
    template_name = "dashboard/portal_salary_section.html"

    def get_context_data(
        self,
        panel_id="portal-panel-salary",
        active_section="",
        salary_type="salaire",
        salary_base=0,
        latest_entry=None,
        entries=None,
        entries_page=None,
        recent_payments=None,
        download_url_name="",
        hx_target="",
        **kwargs,
    ):
        return {
            "panel_id": panel_id,
            "active_section": active_section,
            "salary_type": salary_type,
            "salary_base": salary_base,
            "latest_entry": latest_entry or {},
            "entries": entries or [],
            "entries_page": entries_page,
            "recent_payments": recent_payments or [],
            "download_url_name": download_url_name,
            "hx_target": hx_target,
            **kwargs,
        }
