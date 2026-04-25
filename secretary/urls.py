from django.urls import path

import secretary.views as views

app_name = "secretary"

urlpatterns = [
    path("", views.secretary_dashboard, name="secretary_dashboard"),
    path("htmx/students/", views.htmx_student_results, name="htmx_student_results"),
    path("htmx/classes/", views.htmx_class_results, name="htmx_class_results"),
    path("htmx/registry/", views.htmx_registry_results, name="htmx_registry_results"),
    path("htmx/appointments/", views.htmx_appointment_results, name="htmx_appointment_results"),
    path("htmx/documents/", views.htmx_document_results, name="htmx_document_results"),
    path("htmx/tasks/", views.htmx_task_results, name="htmx_task_results"),
    path("htmx/messages/", views.htmx_messages_panel, name="htmx_messages_panel"),
    path("htmx/auto-assign/", views.htmx_auto_assign, name="htmx_auto_assign"),
    path("registry/", views.registry_list, name="registry_list"),
    path("registry/create/", views.registry_create, name="registry_create"),
    path("registry/<int:pk>/processed/", views.registry_mark_processed, name="registry_mark_processed"),
    path("registry/<int:pk>/archive/", views.registry_archive, name="registry_archive"),
    path("appointment/", views.appointment_list, name="appointment_list"),
    path("appointment/create/", views.appointment_create, name="appointment_create"),
    path("appointment/<int:pk>/complete/", views.appointment_complete, name="appointment_complete"),
    path("visitor/", views.visitor_list, name="visitor_list"),
    path("visitor/create/", views.visitor_create, name="visitor_create"),
    path("document-receipt/", views.document_receipt_list, name="document_receipt_list"),
    path("document-receipt/create/", views.document_receipt_create, name="document_receipt_create"),
    path("document-receipt/<int:pk>/archive/", views.document_receipt_archive, name="document_receipt_archive"),
    path("task/", views.task_list, name="task_list"),
    path("task/create/", views.task_create, name="task_create"),
    path("task/<int:pk>/complete/", views.task_complete, name="task_complete"),
    path("students/<int:student_id>/snapshot/", views.student_snapshot_view, name="student_snapshot"),
]
