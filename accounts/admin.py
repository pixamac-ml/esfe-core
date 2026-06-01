from django.contrib import admin

from accounts.models import (
    AccountingDocumentSequence,
    BranchBankTransfer,
    BranchCashMovement,
    BranchExpense,
    BranchMonthlyClosure,
    Donation,
    PayrollEntry,
    Profile,
    TeacherHonorariumEntry,
)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "position", "branch", "user_type", "salary_base", "teacher_hourly_rate", "employment_status", "is_public", "updated_at")
    list_filter = ("role", "position", "branch", "user_type", "employment_status", "is_public")
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__email")
    autocomplete_fields = ("user", "branch")


@admin.register(PayrollEntry)
class PayrollEntryAdmin(admin.ModelAdmin):
    list_display = ("employee", "branch", "period_month", "base_salary", "paid_amount", "status", "paid_at")
    list_filter = ("branch", "status", "period_month")
    search_fields = ("employee__username", "employee__first_name", "employee__last_name", "employee__email")
    autocomplete_fields = ("employee", "branch", "created_by", "updated_by")


@admin.register(BranchExpense)
class BranchExpenseAdmin(admin.ModelAdmin):
    list_display = ("title", "branch", "category", "amount", "expense_date", "status", "paid_at")
    list_filter = ("branch", "category", "status", "expense_date")
    search_fields = ("title", "supplier", "reference")
    autocomplete_fields = ("branch", "created_by", "approved_by", "paid_by")


@admin.register(BranchCashMovement)
class BranchCashMovementAdmin(admin.ModelAdmin):
    list_display = ("reference", "receipt_number", "label", "branch", "movement_type", "source", "amount", "movement_date", "created_by")
    list_filter = ("branch", "movement_type", "source", "movement_date")
    search_fields = ("label", "reference", "source_reference", "receipt_number", "notes")
    autocomplete_fields = ("branch", "expense", "created_by")


@admin.register(AccountingDocumentSequence)
class AccountingDocumentSequenceAdmin(admin.ModelAdmin):
    list_display = ("branch", "document_type", "year", "last_number", "updated_at")
    list_filter = ("branch", "document_type", "year")
    search_fields = ("branch__name", "branch__code")


@admin.register(TeacherHonorariumEntry)
class TeacherHonorariumEntryAdmin(admin.ModelAdmin):
    list_display = ("teacher", "branch", "period_month", "hourly_rate", "validated_hours", "paid_amount", "status", "paid_at")
    list_filter = ("branch", "status", "period_month")
    search_fields = ("teacher__username", "teacher__first_name", "teacher__last_name", "teacher__email")
    autocomplete_fields = ("teacher", "branch", "created_by", "updated_by")


@admin.register(BranchMonthlyClosure)
class BranchMonthlyClosureAdmin(admin.ModelAdmin):
    list_display = ("branch", "period_month", "status", "result_amount", "bank_transfer_amount", "closed_at")
    list_filter = ("branch", "status", "period_month")
    search_fields = ("branch__name", "branch__code", "notes")
    autocomplete_fields = ("branch", "created_by", "validated_by")


@admin.register(BranchBankTransfer)
class BranchBankTransferAdmin(admin.ModelAdmin):
    list_display = ("branch", "bank_name", "reference", "transfer_date", "amount", "created_by")
    list_filter = ("branch", "transfer_date")
    search_fields = ("bank_name", "reference", "comment")
    autocomplete_fields = ("branch", "closure", "created_by")


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    list_display = ("donor_name", "amount", "branch", "date", "motif", "payment_method", "receipt_number", "created_by")
    list_filter = ("branch", "motif", "payment_method", "date")
    search_fields = ("donor_name", "description", "receipt_number")
    autocomplete_fields = ("branch", "cash_movement", "created_by")
