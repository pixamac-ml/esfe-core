from django_components import component


@component.register("portal_settings_section")
class PortalSettingsSection(component.Component):
    """
    Section paramètres universelle — utilisable dans tous les portails.

    Params:
        panel_id          – id HTML du panneau
        role_label        – libellé du rôle affiché (ex: "Secrétaire", "Enseignant")
        profile_form      – formulaire Django de mise à jour profil (optionnel)
        preference_form   – formulaire Django de préférences (optionnel)
        profile_update_url – URL action du formulaire profil
        preferences_update_url – URL action du formulaire préférences
        avatar_url        – URL de l'avatar (optionnel)
        phone             – téléphone
        location          – localisation
        position_display  – libellé de la fonction
        branch_name       – nom de l'annexe
        extra_fields      – liste de dicts [{label, value, tone}] pour infos complémentaires
    """
    template_name = "dashboard/portal_settings_section.html"

    def get_context_data(
        self,
        panel_id="portal-panel-settings",
        role_label="",
        profile_form=None,
        preference_form=None,
        profile_update_url="",
        preferences_update_url="",
        avatar_url="",
        phone="",
        location="",
        position_display="",
        branch_name="",
        extra_fields=None,
        **kwargs,
    ):
        return {
            "panel_id": panel_id,
            "role_label": role_label,
            "profile_form": profile_form,
            "preference_form": preference_form,
            "profile_update_url": profile_update_url,
            "preferences_update_url": preferences_update_url,
            "avatar_url": avatar_url,
            "phone": phone,
            "location": location,
            "position_display": position_display,
            "branch_name": branch_name,
            "extra_fields": extra_fields or [],
            **kwargs,
        }
