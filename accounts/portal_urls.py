"""Compat legacy: les routes portail sont déplacées dans `portal.urls`."""

from portal.urls import app_name, urlpatterns  # noqa: F401

