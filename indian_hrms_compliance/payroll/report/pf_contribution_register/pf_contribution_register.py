# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""PF Contribution Register.

Per-employee EPF/EPS contribution for a wage month, showing BOTH the employee
deduction (EPF 12%) and the employer contribution (EPS 8.33% + EPF 3.67%), so
HR can see exactly who was deducted how much and what the firm paid on top.

Source of truth: SUBMITTED Salary Slips. We call the ECR generator's own row
builder (``build_pf_ecr_rows``) so the register is always current and produces
byte-for-byte the same figures the PF ECR file / challan would — no filing needs
to exist first, and the two can never diverge.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_first_day, getdate

from indian_hrms_compliance.overrides.pf_ecr_generator import build_pf_ecr_rows


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.get("company"):
		frappe.throw(_("Please select a Company."))
	if not filters.get("wage_month"):
		frappe.throw(_("Please select a Wage Month."))

	wage_month = get_first_day(getdate(filters.wage_month))
	rows, exceptions, _stats = build_pf_ecr_rows(filters.company, wage_month)

	dept_employees = _department_employees(filters)
	data = []
	for r in rows:
		if dept_employees is not None and r["employee"] not in dept_employees:
			continue
		employee_pf = flt(r["epf_contribution"])
		employer_eps = flt(r["eps_contribution"])
		employer_epf = flt(r["epf_eps_diff"])
		employer_total = employer_eps + employer_epf
		data.append(
			{
				"employee": r["employee"],
				"employee_name": r["employee_name"],
				"uan": r["uan"],
				"gross_wages": flt(r["gross_wages"]),
				"epf_wages": flt(r["epf_wages"]),
				"eps_wages": flt(r["eps_wages"]),
				"employee_pf": employee_pf,
				"employer_eps": employer_eps,
				"employer_epf": employer_epf,
				"employer_total": employer_total,
				"total": employee_pf + employer_total,
				"ncp_days": flt(r["ncp_days"]),
			}
		)

	if not data:
		frappe.msgprint(
			_("No PF members found in submitted Salary Slips for {0} in {1}.").format(
				frappe.bold(filters.company), frappe.bold(getdate(wage_month).strftime("%b %Y"))
			),
			title=_("Nothing to show"),
			indicator="orange",
		)

	data.sort(key=lambda x: (x["employee_name"] or "", x["employee"] or ""))
	return get_columns(), data


def _department_employees(filters):
	"""Set of employees in the chosen department, or None when unfiltered."""
	if not filters.get("department"):
		return None
	return set(
		frappe.get_all(
			"Employee",
			filters={"company": filters.company, "department": filters.department},
			pluck="name",
		)
	)


def get_columns():
	return [
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 120},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 170},
		{"label": _("UAN"), "fieldname": "uan", "fieldtype": "Data", "width": 130},
		{"label": _("Gross Wages"), "fieldname": "gross_wages", "fieldtype": "Currency", "width": 120},
		{"label": _("EPF Wages"), "fieldname": "epf_wages", "fieldtype": "Currency", "width": 110},
		{"label": _("EPS Wages"), "fieldname": "eps_wages", "fieldtype": "Currency", "width": 110},
		{"label": _("Employee PF (12%)"), "fieldname": "employee_pf", "fieldtype": "Currency", "width": 130},
		{"label": _("Employer EPS (8.33%)"), "fieldname": "employer_eps", "fieldtype": "Currency", "width": 140},
		{"label": _("Employer EPF (3.67%)"), "fieldname": "employer_epf", "fieldtype": "Currency", "width": 140},
		{"label": _("Employer Total"), "fieldname": "employer_total", "fieldtype": "Currency", "width": 120},
		{"label": _("Total (EE+ER)"), "fieldname": "total", "fieldtype": "Currency", "width": 120},
		{"label": _("NCP Days"), "fieldname": "ncp_days", "fieldtype": "Float", "width": 90},
	]
