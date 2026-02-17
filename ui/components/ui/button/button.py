from django_components import component


@component.register("button")
class Button(component.Component):
    template_name = "ui/button/button.html"

    def get_context_data(
        self,
        label="",
        href="#",
        variant="primary",   # primary | secondary | outline | ghost | soft
        size="md",           # sm | md | lg
        disabled=False,
        icon_left="",
        icon_right="",
        full_width=False,
        type="button",
    ):
        return {
            "label": label,
            "href": href,
            "variant": variant,
            "size": size,
            "disabled": disabled,
            "icon_left": icon_left,
            "icon_right": icon_right,
            "full_width": full_width,
            "type": type,
        }
