from academic_cycle.services.dashboard_access_service import compute_student_access_policy
from academic_cycle.services.reenrollment_service import prepare_reenrollment_for_student


def run_student_reenrollment_preparation(student, decision, target_year):
    reenrollment = prepare_reenrollment_for_student(student, decision, target_year)
    policy = compute_student_access_policy(student, target_year)
    return {"reenrollment": reenrollment, "policy": policy}
