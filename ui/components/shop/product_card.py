from django_components import component


@component.register("shop.product_card")
class ProductCard(component.Component):
    template_name = "shop/product_card.html"

    def get_context_data(
        self,
        product_id="",
        name="",
        image_url="",
        category="",
        price="",
        original_price="",
        stock=0,
        is_available=True,
        variant_name="",
        branch="",
        action_url="#",
        hx_post="",
        **kwargs,
    ):
        return {
            "product_id": product_id,
            "name": name,
            "image_url": image_url,
            "category": category,
            "price": price,
            "original_price": original_price,
            "stock": int(stock),
            "is_available": bool(is_available),
            "variant_name": variant_name,
            "branch": branch,
            "action_url": action_url,
            "hx_post": hx_post,
        }
