from django.urls import path
from . import views

app_name = "ui"

urlpatterns = [
    path("galerie/", views.gallery, name="gallery"),
    path("system/", views.ui_system, name="system"),
    path("system/domains/", views.ui_domain_catalog, name="system_domains"),
    path("system/domains/component/<slug:slug>/", views.ui_domain_component_detail, name="system_domain_component"),
    path("system/domains/demo/<slug:slug>/", views.ui_domain_component_demo, name="system_domain_demo"),
    path("system/demo/table/", views.ui_system_demo_table, name="system_demo_table"),
    path("system/demo/modal/", views.ui_system_demo_modal, name="system_demo_modal"),
    path("system/demo/drawer/", views.ui_system_demo_drawer, name="system_demo_drawer"),
    path("system/demo/form/", views.ui_system_demo_form, name="system_demo_form"),
    path("system/demo/confirm/", views.ui_system_demo_confirm, name="system_demo_confirm"),
    path("system/demo/refresh/", views.ui_system_demo_refresh, name="system_demo_refresh"),
    path("system/demo/error/", views.ui_system_demo_error, name="system_demo_error"),
]
