# branches/admin.py

from django.contrib import admin
from .models import Branch


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "city", "is_active", "cash_reserve_target"]
    list_filter = ["is_active", "city"]
    search_fields = ["name", "code"]
    prepopulated_fields = {"slug": ("name",)}