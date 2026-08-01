from django_components import component


@component.register("account.profile_view")
class ProfileView(component.Component):
    template_name = "account/profile_view.html"

    def get_context_data(
        self,
        user=None,
        avatar_url="",
        display_name="",
        email="",
        role="",
        branch="",
        status="active",
        status_label="",
        phone="",
        address="",
        created_at="",
        last_seen="",
        bio="",
        extra_fields=None,
        actions=None,
        **kwargs,
    ):
        if user and not display_name:
            display_name = user.get_full_name() or user.username
        if user and not email:
            email = getattr(user, "email", "")
        if user and not avatar_url:
            avatar_url = getattr(user, "avatar", "") or ""

        return {
            "avatar_url": avatar_url,
            "display_name": display_name,
            "email": email,
            "role": role,
            "branch": branch,
            "status": status,
            "status_label": status_label or status,
            "phone": phone,
            "address": address,
            "created_at": created_at,
            "last_seen": last_seen,
            "bio": bio,
            "extra_fields": extra_fields or [],
            "actions": actions or [],
        }
