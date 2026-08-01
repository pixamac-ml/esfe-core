from django_components import component


@component.register("account.profile_dropdown")
class ProfileDropdown(component.Component):
    template_name = "account/profile_dropdown.html"

    def get_context_data(
        self,
        user=None,
        avatar_url="",
        display_name="",
        role="",
        profile_url="#",
        edit_url="#",
        security_url="#",
        preferences_url="#",
        logout_url="#",
        drawer_id="director-drawer",
        **kwargs,
    ):
        if user and not display_name:
            display_name = user.get_full_name() or user.username
        if user and not avatar_url:
            profile = getattr(user, "profile", None)
            avatar_url = getattr(profile, "avatar_url", "") or ""

        return {
            "avatar_url": avatar_url,
            "display_name": display_name,
            "role": role,
            "profile_url": profile_url,
            "edit_url": edit_url,
            "security_url": security_url,
            "preferences_url": preferences_url,
            "logout_url": logout_url,
            "drawer_id": drawer_id,
        }
