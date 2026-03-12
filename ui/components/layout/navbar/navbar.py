from django_components import component
from django.db.models import Prefetch

from formations.models import Cycle, Programme
from news.models import Category as NewsCategory
from blog.models import Category as BlogCategory
from community.models import Notification


@component.register("navbar")
class Navbar(component.Component):
    template_name = "layout/navbar/navbar.html"

    def get_context_data(self, **kwargs):
        # Récupérer request depuis le contexte (fourni par Django)
        request = self.request

        # FORMATIONS - Cycles et programmes
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

        # NEWS CATEGORIES
        news_categories = (
            NewsCategory.objects
            .filter(is_active=True)
            .order_by("nom")[:6]
        )

        # BLOG CATEGORIES
        blog_categories = (
            BlogCategory.objects
            .filter(is_active=True)
            .order_by("name")[:6]
        )

        # NOTIFICATIONS - COMPTEUR
        unread_notification_count = 0
        if request.user.is_authenticated:
            unread_notification_count = Notification.objects.filter(
                user=request.user,
                is_read=False
            ).count()

        return {
            "cycles": cycles,
            "news_categories": news_categories,
            "blog_categories": blog_categories,
            "unread_notification_count": unread_notification_count,
        }