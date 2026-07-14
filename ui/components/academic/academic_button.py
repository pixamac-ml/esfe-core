from django_components import component


@component.register("academic_button")
class AcademicButton(component.Component):
    """Bouton scolaire normalisé (primary, secondary, success, danger, warning, info, ghost, outline)."""

    template_name = "academic/academic_button.html"

    def get_context_data(
        self,
        label="",
        variant="primary",
        size="md",
        type="button",
        icon=None,
        icon_only=False,
        disabled=False,
        loading=False,
        confirm=None,
        hx_get=None,
        hx_post=None,
        hx_put=None,
        hx_patch=None,
        hx_delete=None,
        hx_target=None,
        hx_swap=None,
        hx_confirm=None,
        hx_indicator=None,
        extra_class="",
        attrs="",
        **kwargs,
    ):
        return {
            "label": label,
            "variant": variant,
            "size": size,
            "type": type,
            "icon": icon,
            "icon_only": icon_only,
            "disabled": disabled,
            "loading": loading,
            "confirm": confirm,
            "hx_get": hx_get,
            "hx_post": hx_post,
            "hx_put": hx_put,
            "hx_patch": hx_patch,
            "hx_delete": hx_delete,
            "hx_target": hx_target,
            "hx_swap": hx_swap,
            "hx_confirm": hx_confirm or confirm,
            "hx_indicator": hx_indicator,
            "extra_class": extra_class,
            "attrs": attrs,
            **kwargs,
        }
