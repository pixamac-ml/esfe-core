from academic_cycle.models import AcademicAuditLog
from . import shared_task


@shared_task
def count_academic_audit_logs_task():
    return AcademicAuditLog.objects.count()
