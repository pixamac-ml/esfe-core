from django.urls import path
from .views import (
    dashboard,
    profile_partial,
    academics_partial,
    finance_partial,
    notifications_partial,
)

app_name = "portal_student"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("profile/", profile_partial, name="profile_partial"),
    path("academics/", academics_partial, name="academics_partial"),
    path("finance/", finance_partial, name="finance_partial"),
    path("notifications/", notifications_partial, name="notifications_partial"),
]
