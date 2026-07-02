from django_components import component


@component.register("skeleton")
class Skeleton(component.Component):
    template_name = "atoms/skeleton.html"

    def get_context_data(self, variant="text", width="", height="", **kwargs):
        variants = {
            "text": "h-4 w-full rounded",
            "circle": "rounded-full",
            "card": "h-32 w-full rounded-xl",
            "rect": "rounded-lg",
        }
        base = "animate-pulse bg-[color:var(--line)]"
        variant_class = variants.get(variant, variants["text"])
        style = ""
        if width:
            style += f"width:{width};"
        if height:
            style += f"height:{height};"
        if variant == "circle" and not height:
            variant_class += " w-10 h-10"
        return {
            "base_class": base,
            "variant_class": variant_class,
            "style": style,
            **kwargs,
        }
