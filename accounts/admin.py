from django.contrib import admin

from accounts.models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "position", "branch", "user_type", "is_public", "updated_at")
    list_filter = ("role", "position", "branch", "user_type", "is_public")
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__email")
    autocomplete_fields = ("user", "branch")
