from django.urls import path

from .views import (
    annual_class_report_view,
    class_reports_overview_view,
    export_class_reports_view,
    export_selected_reports_view,
    student_annual_report_view,
    student_semester_pdf_view,
    student_semester_report_view,
    student_year_report_view,
)

app_name = "academics"
urlpatterns = [
    path(
        "reports/student/<int:student_id>/semester/<int:semester_id>/",
        student_semester_report_view,
        name="student_semester_report",
    ),
    path(
        "reports/student/<int:student_id>/semester/<int:semester_id>/pdf/",
        student_semester_pdf_view,
        name="student_semester_pdf",
    ),
    path(
        "reports/semester/<int:semester_id>/export-selected/",
        export_selected_reports_view,
        name="export_selected_reports",
    ),
    path(
        "reports/semester/<int:semester_id>/export-all/",
        export_class_reports_view,
        name="export_class_reports",
    ),
    path(
        "reports/semester/<int:semester_id>/overview/",
        class_reports_overview_view,
        name="class_reports_overview",
    ),
    path(
        "reports/class/<int:class_id>/annual/",
        annual_class_report_view,
        name="annual_class_report",
    ),
    path(
        "reports/student/<int:student_id>/annual/",
        student_annual_report_view,
        name="student_annual_report",
    ),
    path(
        "reports/student/<int:student_id>/year/<int:academic_year_id>/",
        student_year_report_view,
        name="student_year_report",
    ),
]
