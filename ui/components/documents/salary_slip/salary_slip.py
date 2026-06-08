from django_components import component


@component.register("esfe_salary_slip")
class SalarySlip(component.Component):
    template_name = "documents/salary_slip/salary_slip.html"

    def get_context_data(
        self,
        slip_number="",
        date="",
        period="",
        employee_name="",
        employee_position="",
        employee_matricule="",
        base_salary="",
        allowances=None,
        deductions=None,
        advances="",
        net_salary="",
        paid_amount="",
        remaining="",
        status="",
        **kwargs,
    ):
        if allowances is None:
            allowances = []
        if deductions is None:
            deductions = []
        return {
            "title": "FICHE DE PAIE",
            "slip_number": slip_number,
            "date": date,
            "period": period,
            "employee_name": employee_name,
            "employee_position": employee_position,
            "employee_matricule": employee_matricule,
            "base_salary": base_salary,
            "allowances": allowances,
            "deductions": deductions,
            "advances": advances,
            "net_salary": net_salary,
            "paid_amount": paid_amount,
            "remaining": remaining,
            "status": status,
            **kwargs,
        }
