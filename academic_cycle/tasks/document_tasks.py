from . import shared_task


@shared_task
def regenerate_student_documents_task(student_id, academic_year_id):
    return {"student_id": student_id, "academic_year_id": academic_year_id, "status": "queued_placeholder"}
