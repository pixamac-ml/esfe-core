from django_components import component


@component.register("button")
class Button(component.Component):
    template_name = "ui/button/button.html"

    def get_context_data(
        self,
        label="",
        href="",
        variant="primary",   # primary | secondary | outline | ghost | danger
        size="md",           # sm | md | lg
        disabled=False,
        loading=False,
        icon="",
        icon_left="",
        icon_right="",
        full_width=False,
        type="button",
        x_on_click="",
        hx_get="",
        hx_post="",
        hx_target="",
        hx_swap="",
        hx_indicator="",
        hx_confirm="",
        aria_label="",
        title="",
        class_str="",
    ):
        return {
            "label": label,
            "href": href,
            "variant": variant,
            "size": size,
            "disabled": disabled or loading,
            "loading": loading,
            "icon_left": icon_left or icon,
            "icon_right": icon_right,
            "full_width": full_width,
            "type": type,
            "x_on_click": x_on_click,
            "hx_get": hx_get,
            "hx_post": hx_post,
            "hx_target": hx_target,
            "hx_swap": hx_swap,
            "hx_indicator": hx_indicator,
            "hx_confirm": hx_confirm,
            "aria_label": aria_label,
            "title": title,
            "class_str": class_str,
        }
