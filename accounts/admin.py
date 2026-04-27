from django.contrib import admin

from accounts.models import PayrollEntry, Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "position", "branch", "user_type", "salary_base", "employment_status", "is_public", "updated_at")
    list_filter = ("role", "position", "branch", "user_type", "employment_status", "is_public")
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__email")
    autocomplete_fields = ("user", "branch")


@admin.register(PayrollEntry)
class PayrollEntryAdmin(admin.ModelAdmin):
    list_display = ("employee", "branch", "period_month", "base_salary", "paid_amount", "status", "paid_at")
    list_filter = ("branch", "status", "period_month")
    search_fields = ("employee__username", "employee__first_name", "employee__last_name", "employee__email")
    autocomplete_fields = ("employee", "branch", "created_by", "updated_by")
