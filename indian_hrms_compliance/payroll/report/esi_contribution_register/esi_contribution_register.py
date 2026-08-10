# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""ESI Contribution Register.

Per-employee ESI contribution for a wage month, showing BOTH the employee
deduction (0.75%) and the employer contribution (3.25%), so HR can see who was
deducted how much and what the firm paid on top.

Source: the ``ESI Monthly Contribution`` for that (Company x wage month). Reading
the filing guarantees the register equals what was actually generated — the wage
ceiling, the low-wage employee-share waiver and the Reg-26 continuation rule are
already resolved there. If no filing exists yet, we say so instead of silently
re-deriving (and possibly diverging).
"""

import frappe
from frappe import _
from frappe.utils import flt, get_first_day, get_last_day, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.get("company"):
		frappe.throw(_("Please select a Company."))
	if not filters.get("wage_month"):
		frappe.throw(_("Please select a Wage Month."))

	filing = _get_filing(filters)
	if not filing:
		frappe.msgprint(
			_("No ESI Monthly Contribution found for {0} in {1}. Generate it for that month first.").format(
				frappe.bold(filters.company), frappe.bold(getdate(filters.wage_month).strftime("%b %Y"))
			),
			title=_("Nothing to show"),
			indicator="orange",
		)
		return get_columns(), []

	dept_employees = _department_employees(filters)
	data = []
	for r in filing.rows:
		if dept_employees is not None and r.employee not in dept_employees:
			continue
		employee_esi = flt(r.employee_contribution)
		employer_esi = flt(r.employer_contribution)
		data.append(
			{
				"employee": r.employee,
				"employee_name": r.employee_name,
				"ip_number": r.ip_number,
				"no_of_days": flt(r.no_of_days),
				"total_wages": flt(r.total_wages),
				"employee_esi": employee_esi,
				"employer_esi": employer_esi,
				"total": employee_esi + employer_esi,
			}
		)

	data.sort(key=lambda x: (x["employee_name"] or "", x["employee"] or ""))
	return get_columns(), data


def _get_filing(filters):
	"""Latest non-cancelled ESI Monthly Contribution for the company + wage month."""
	wm = getdate(filters.wage_month)
	conds = {
		"company": filters.company,
		"wage_month": ["between", [get_first_day(wm), get_last_day(wm)]],
	}
	if filters.get("filing_status"):
		conds["filing_status"] = filters.filing_status
	else:
		conds["filing_status"] = ["!=", "Cancelled"]
	name = frappe.db.get_value("ESI Monthly Contribution", conds, "name", order_by="modified desc")
	return frappe.get_doc("ESI Monthly Contribution", name) if name else None


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
