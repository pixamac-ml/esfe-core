from django_components import component


@component.register("shop.product_grid")
class ProductGrid(component.Component):
    template_name = "shop/product_grid.html"

    def get_context_data(
        self,
        products=None,
        empty_message="Aucun produit disponible",
        loading=False,
        columns=3,
        **kwargs,
    ):
        cols_map = {2: "grid-cols-2", 3: "grid-cols-2 md:grid-cols-3", 4: "grid-cols-2 md:grid-cols-3 lg:grid-cols-4"}
        return {
            "products": products or [],
            "empty_message": empty_message,
            "loading": bool(loading),
            "columns_class": cols_map.get(columns, "grid-cols-2 md:grid-cols-3"),
        }
