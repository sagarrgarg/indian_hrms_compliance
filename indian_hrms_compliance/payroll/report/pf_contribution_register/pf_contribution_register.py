# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""PF Contribution Register.

Per-employee EPF/EPS contribution for a wage month, showing BOTH the employee
deduction (EPF 12%) and the employer contribution (EPS 8.33% + EPF 3.67%), so
HR can see exactly who was deducted how much and what the firm paid on top.

Source: the ``PF ECR Filing`` for that (Company x wage month). Reading the filing
guarantees the register equals what was actually generated/remitted to EPFO — the
per-member EPS cap, EPF/EPS split, etc. are already resolved there. If no filing
exists yet, we say so instead of silently re-deriving (and possibly diverging).
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
			_("No PF ECR Filing found for {0} in {1}. Generate the PF ECR Filing for that month first.").format(
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
		employee_pf = flt(r.epf_contribution)
		employer_eps = flt(r.eps_contribution)
		employer_epf = flt(r.epf_eps_diff)
		employer_total = employer_eps + employer_epf
		data.append(
			{
				"employee": r.employee,
				"employee_name": r.employee_name,
				"uan": r.uan,
				"gross_wages": flt(r.gross_wages),
				"epf_wages": flt(r.epf_wages),
				"eps_wages": flt(r.eps_wages),
				"employee_pf": employee_pf,
				"employer_eps": employer_eps,
				"employer_epf": employer_epf,
				"employer_total": employer_total,
				"total": employee_pf + employer_total,
				"ncp_days": flt(r.ncp_days),
			}
		)

	data.sort(key=lambda x: (x["employee_name"] or "", x["employee"] or ""))
	return get_columns(), data


def _get_filing(filters):
	"""Latest non-cancelled PF ECR Filing for the company + wage month."""
	wm = getdate(filters.wage_month)
	conds = {
		"company": filters.company,
		"wage_month": ["between", [get_first_day(wm), get_last_day(wm)]],
	}
	if filters.get("filing_status"):
		conds["filing_status"] = filters.filing_status
	else:
		conds["filing_status"] = ["!=", "Cancelled"]
	name = frappe.db.get_value("PF ECR Filing", conds, "name", order_by="modified desc")
	return frappe.get_doc("PF ECR Filing", name) if name else None


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
