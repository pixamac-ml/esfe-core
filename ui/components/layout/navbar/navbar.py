from django_components import component
from formations.models import Cycle, Programme
from django.db.models import Prefetch


@component.register("navbar")
class Navbar(component.Component):
    template_name = "layout/navbar/navbar.html"

    def get_context_data(self, **kwargs):
        cycles = (
            Cycle.objects
            .filter(is_active=True)
            .prefetch_related(
                Prefetch(
                    "programmes",
                    queryset=Programme.objects.filter(is_active=True)
                )
            )
            .order_by("min_duration_years")
        )

        return {
            "cycles": cycles
        }