# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""ESI Contribution Register.

Per-employee ESI contribution for a wage month, showing BOTH the employee
deduction (0.75%) and the employer contribution (3.25%), so HR can see who was
deducted how much and what the firm paid on top.

Source of truth: SUBMITTED Salary Slips. We call the ESI generator's own row
builder (``build_esi_rows``) so the register is always current and produces the
same figures the ESIC upload / challan would — wage ceiling, low-wage employee
waiver and Reg-26 continuation included — with no filing needing to exist first.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_first_day, getdate

from indian_hrms_compliance.overrides.esi_generator import build_esi_rows


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.get("company"):
		frappe.throw(_("Please select a Company."))
	if not filters.get("wage_month"):
		frappe.throw(_("Please select a Wage Month."))

	wage_month = get_first_day(getdate(filters.wage_month))
	rows, exceptions, _stats = build_esi_rows(filters.company, wage_month)

	dept_employees = _department_employees(filters)
	data = []
	for r in rows:
		if dept_employees is not None and r["employee"] not in dept_employees:
			continue
		employee_esi = flt(r["employee_contribution"])
		employer_esi = flt(r["employer_contribution"])
		data.append(
			{
				"employee": r["employee"],
				"employee_name": r["employee_name"],
				"ip_number": r["ip_number"],
				"no_of_days": flt(r["no_of_days"]),
				"total_wages": flt(r["total_wages"]),
				"employee_esi": employee_esi,
				"employer_esi": employer_esi,
				"total": employee_esi + employer_esi,
			}
		)

	if not data:
		frappe.msgprint(
			_("No ESI-covered employees found in submitted Salary Slips for {0} in {1}.").format(
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
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
		{"label": _("IP Number"), "fieldname": "ip_number", "fieldtype": "Data", "width": 130},
		{"label": _("No. of Days"), "fieldname": "no_of_days", "fieldtype": "Float", "width": 100},
		{"label": _("ESI Wages"), "fieldname": "total_wages", "fieldtype": "Currency", "width": 120},
		{"label": _("Employee ESI (0.75%)"), "fieldname": "employee_esi", "fieldtype": "Currency", "width": 150},
		{"label": _("Employer ESI (3.25%)"), "fieldname": "employer_esi", "fieldtype": "Currency", "width": 150},
		{"label": _("Total (EE+ER)"), "fieldname": "total", "fieldtype": "Currency", "width": 130},
	]
