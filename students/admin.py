# students/admin.py

from django.contrib import admin
from .models import Student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = (
        "matricule",
        "full_name",
        "email",
        "is_active",
        "created_at",
    )

    list_filter = (
        "is_active",
        "created_at",
    )

    search_fields = (
        "matricule",
        "user__first_name",
        "user__last_name",
        "user__email",
    )

    readonly_fields = (
        "created_at",
    )

    def full_name(self, obj):
        return obj.user.get_full_name()
    full_name.short_description = "Nom complet"

    def email(self, obj):
        return obj.user.email
