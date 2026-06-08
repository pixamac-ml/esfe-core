import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.urls import reverse, NoReverseMatch

urls_to_test = [
    ('accounts_portal:portal_it', []),
    ('accounts_portal:it_diagnostics_panel', []),
    ('accounts_portal:it_accounts_panel', []),
    ('accounts_portal:it_support_panel', []),
    ('accounts_portal:it_notes_kpi', []),
    ('accounts_portal:it_workflow_section', []),
    ('accounts_portal:it_notes_decisions', []),
    ('accounts_portal:it_notes_flow_workspace', []),
    ('accounts_portal:it_home_workspace', []),
    ('accounts_portal:it_notes_workflow_action', []),
    ('accounts_portal:it_notes_retake_modal', []),
    ('accounts_portal:load_notes_workspace', []),
    ('accounts_portal:it_accounts_flow_workspace', []),
    ('accounts_portal:it_accounts_flow_action', []),
    ('accounts_portal:it_user_modal', [1]),
    ('accounts_portal:it_user_modal_save', [1]),
    ('accounts_portal:it_support_flow_workspace', []),
    ('accounts_portal:it_support_flow_action', []),
    ('accounts_portal:it_audit_workspace', []),
    ('accounts_portal:it_archives_workspace', []),
    ('accounts_portal:it_archives_action', []),
    ('accounts_portal:it_archive_detail', [1]),
    ('accounts_portal:it_import_workspace', []),
    ('accounts_portal:it_import_upload', []),
    ('accounts_portal:it_export_notes_excel', []),
    ('accounts_portal:it_structure_workspace', []),
    ('accounts_portal:it_structure_drawer', []),
    ('accounts_portal:it_structure_modal', []),
    ('accounts_portal:it_structure_action', []),
    ('accounts_portal:it_supervision_workspace', []),
    ('accounts_portal:it_catalog_workspace', []),
    ('accounts_portal:it_catalog_action', []),
    ('accounts_portal:it_cards_workspace', []),
    ('accounts_portal:it_class_cards_pdf', []),
    ('accounts_portal:it_student_card_pdf', [1]),
    ('accounts_portal:it_notifications_workspace', []),
    ('accounts_portal:it_notifications_action', []),
    ('accounts_portal:it_branch_settings_workspace', []),
    ('accounts_portal:it_branch_settings_save', []),
    ('accounts_portal:it_my_account_workspace', []),
    ('accounts_portal:it_my_account_save', []),
    ('accounts_portal:it_surveillance_workspace', []),
    ('accounts_portal:it_surveillance_student_followup', [1]),
    ('accounts_portal:it_notes_grid', []),
    ('accounts_portal:it_notes_workspace', []),
    ('accounts_portal:it_grade_sheet_pdf', [1, 1]),
    ('accounts_portal:it_grade_sheet_print', [1, 1]),
    ('accounts_portal:it_grades_import', []),
    ('communication:notifications_partial', []),
    ('communication:notification_detail', [1]),
    ('communication:mark_all_notifications_read', []),
]

all_ok = True
for name, args in urls_to_test:
    try:
        path = reverse(name, args=args)
        print(f'  OK  {name} -> {path}')
    except NoReverseMatch as e:
        print(f'  FAIL {name} -> {e}')
        all_ok = False

print()
if all_ok:
    print('All IT URLs resolved successfully!')
else:
    print('SOME URLs FAILED!')
