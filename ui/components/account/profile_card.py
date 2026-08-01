from django_components import component


@component.register("account.profile_card")
class ProfileCard(component.Component):
    template_name = "account/profile_card.html"

    def get_context_data(
        self,
        user=None,
        avatar_url="",
        display_name="",
        role="",
        branch="",
        status="active",
        status_label="",
        profile_url="#",
        compact=False,
        **kwargs,
    ):
        if user and not display_name:
            display_name = user.get_full_name() or user.username
        if user and not avatar_url:
            avatar_url = getattr(user, "avatar", "") or ""

        return {
            "avatar_url": avatar_url,
            "display_name": display_name,
            "role": role,
            "branch": branch,
            "status": status,
            "status_label": status_label or status,
            "profile_url": profile_url,
            "compact": bool(compact),
        }
