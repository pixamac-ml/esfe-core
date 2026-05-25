from academics.models import AcademicYear
from academic_cycle.selectors import get_students_for_branch_year
from academic_cycle.services.promotion_service import compute_student_year_decision
from branches.models import Branch
from . import shared_task


@shared_task
def compute_branch_student_decisions_task(branch_id, academic_year_id):
    branch = Branch.objects.get(pk=branch_id)
    year = AcademicYear.objects.get(pk=academic_year_id)
    count = 0
    for student in get_students_for_branch_year(branch, year):
        compute_student_year_decision(student, year)
        count += 1
    return count
