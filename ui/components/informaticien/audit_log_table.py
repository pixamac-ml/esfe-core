from django_components import component


@component.register("audit_log_table")
class AuditLogTable(component.Component):
    template_name = "informaticien/audit_log_table.html"

    def get_context_data(self, logs):
        return {"logs": logs}
