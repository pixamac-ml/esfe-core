from django.urls import path

from . import views

app_name = "academic_cycle"

urlpatterns = [
    path("dg/overview/", views.dg_overview, name="dg_overview"),
    path("branch/<int:pk>/overview/", views.branch_overview, name="branch_overview"),
    path("branch/<int:pk>/readiness/", views.branch_readiness, name="branch_readiness"),
    path("branch/<int:pk>/generate-report/", views.generate_report, name="generate_report"),
    path("branch/<int:pk>/start-deliberation/", views.start_deliberation_view, name="start_deliberation"),
    path("branch/<int:pk>/close/", views.close_branch_view, name="close_branch"),
    path("branch/<int:pk>/open-registration/", views.open_registration_view, name="open_registration"),
    path("branch/<int:pk>/activate-year/", views.activate_year_view, name="activate_year"),
    path("student/pre-rentree/", views.student_pre_rentree, name="student_pre_rentree"),
    path("student/reenrollment/<str:token>/", views.student_reenrollment, name="student_reenrollment"),
    path("student/transfer/request/", views.student_transfer_request, name="student_transfer_request"),
    path("corrections/", views.correction_list, name="correction_list"),
    path("corrections/<int:pk>/resolve/", views.resolve_correction_view, name="resolve_correction"),
]
