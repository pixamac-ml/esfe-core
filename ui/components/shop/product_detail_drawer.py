from django_components import component


@component.register("shop.product_detail_drawer")
class ProductDetailDrawer(component.Component):
    template_name = "shop/product_detail_drawer.html"

    def get_context_data(
        self,
        drawer_id="product-detail-drawer",
        product=None,
        hx_load="",
        hx_add_to_cart="",
        **kwargs,
    ):
        return {
            "drawer_id": drawer_id,
            "product": product or {},
            "hx_load": hx_load,
            "hx_add_to_cart": hx_add_to_cart,
        }
