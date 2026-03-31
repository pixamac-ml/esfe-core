from django.contrib.sitemaps import Sitemap
from django.urls import NoReverseMatch, reverse

from blog.models import Article
from formations.models import Programme
from news.models import News


class StaticViewSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return [
            "core:home",
            "core:about",
            "core:contact",
            "core:sitemap",
            "formations:list",
            "news:list",
            "news:result_list",
            "blog:article_list",
            "community:topic_list",
            "core:legal_notice",
            "core:privacy_policy",
            "core:terms_of_service",
        ]

    def location(self, item):
        try:
            return reverse(item)
        except NoReverseMatch:
            return "/"


class ProgrammeSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return Programme.objects.filter(is_active=True).order_by("-updated_at")

    def lastmod(self, obj):
        return obj.updated_at


class NewsSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.8

    def items(self):
        return News.objects.filter(status=News.STATUS_PUBLISHED).order_by("-updated_at")

    def lastmod(self, obj):
        return obj.updated_at


class BlogArticleSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return Article.objects.filter(status="published", is_deleted=False).order_by("-updated_at")

    def lastmod(self, obj):
        return obj.updated_at


def build_sitemaps():
    return {
        "static": StaticViewSitemap,
        "formations": ProgrammeSitemap,
        "news": NewsSitemap,
        "blog": BlogArticleSitemap,
    }
