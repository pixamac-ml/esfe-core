from django_components import component


@component.register("account.profile_editor")
class ProfileEditor(component.Component):
    template_name = "account/profile_editor.html"

    def get_context_data(
        self,
        form=None,
        form_action="",
        form_method="POST",
        hx_post="",
        hx_target="",
        hx_swap="outerHTML",
        drawer_id="director-drawer",
        enctype="multipart/form-data",
        title="Modifier le profil",
        **kwargs,
    ):
        return {
            "form": form,
            "form_action": form_action,
            "form_method": form_method,
            "hx_post": hx_post,
            "hx_target": hx_target,
            "hx_swap": hx_swap,
            "drawer_id": drawer_id,
            "enctype": enctype,
            "title": title,
        }
