# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Overtime pay (OSH Code s.27: work beyond the daily / weekly limit is paid at
twice the ordinary rate of wages).

Hours come from the Time and Overtime Register (Attendance working hours, daily vs
weekly excess, holiday / weekly-off work counted as comp-off, not OT). This module
only values them and books them as Additional Salary on the "Overtime" component:

    hourly rate = monthly (Basic + DA) / (days x hours)     HR Settings, 26 x 8
    amount      = OT hours x hourly rate x multiplier        HR Settings, 2

Basic + DA is the employee's full-month wage from the Salary Structure Assignment
in force at the period end. Drafts go through the usual Additional Salary approval;
submit=1 approves and submits them straight away.
"""

import frappe
from frappe import _
from frappe.utils import add_months, cint, flt, get_first_day, getdate

from indian_hrms_compliance.hr.doctype.statutory_component_mapping.statutory_component_mapping import (
	get_mapping_for_company,
)
from indian_hrms_compliance.hr.report.time_and_overtime_register.time_and_overtime_register import (
	execute as overtime_register,
)
from indian_hrms_compliance.overrides.salary_structure_validator import _is_pf_wage_row, _row_monthly_amount

OVERTIME_COMPONENT = "Overtime"


@frappe.whitelist()
def create_overtime_pay(company, from_date, to_date, payroll_date=None, submit=0):
	"""Create (or refresh) one Overtime Additional Salary per employee with payable
	OT hours in [from_date, to_date]. Returns a summary for the caller to show."""
	frappe.only_for(("HR Manager", "System Manager"))
	if not frappe.db.exists("Salary Component", OVERTIME_COMPONENT):
		frappe.throw(_("Create the Salary Component '{0}' first.").format(OVERTIME_COMPONENT))

	payroll_date = getdate(payroll_date or to_date)
	settings = _settings()
	rows = overtime_register({"company": company, "from_date": from_date, "to_date": to_date})[1]
	quarter_hours = _quarter_hours(company, to_date)

	created, updated, skipped, over_limit = [], [], [], []
	for row in rows:
		hours = flt(row.get("ot_hours"))
		if hours <= 0:
			continue
		employee = row["employee"]
		wage = monthly_wage(employee, company, to_date)
		if not wage:
			skipped.append(_("{0}: no Basic + DA found on the salary assignment").format(employee))
			continue

		hourly = wage / (settings.days * settings.hours)
		amount = flt(hours * hourly * settings.multiplier, 2)
		status = _upsert(employee, company, payroll_date, amount, cint(submit))
		if status == "submitted-exists":
			skipped.append(_("{0}: overtime already submitted for {1}").format(employee, payroll_date))
			continue
		(created if status == "created" else updated).append(
			{"employee": employee, "hours": hours, "hourly_rate": flt(hourly, 2), "amount": amount}
		)
		if settings.quarter_limit and quarter_hours.get(employee, 0) > settings.quarter_limit:
			over_limit.append({"employee": employee, "quarter_hours": quarter_hours[employee]})

	return {
		"created": created,
		"updated": updated,
		"skipped": skipped,
		"over_quarterly_limit": over_limit,
		"quarterly_limit": settings.quarter_limit,
	}


def monthly_wage(employee, company, on_date):
	"""Full-month Basic + DA from the Salary Structure Assignment in force on on_date."""
	ssa = frappe.get_all(
		"Salary Structure Assignment",
		filters={"employee": employee, "company": company, "docstatus": 1, "from_date": ("<=", on_date)},
		fields=["salary_structure", "base"],
		order_by="from_date desc",
		limit=1,
	)
	if not ssa:
		return 0
	structure = frappe.get_cached_doc("Salary Structure", ssa[0].salary_structure)
	mapping = get_mapping_for_company(company)
	context = {"uan_number": frappe.db.get_value("Employee", employee, "uan_number") or ""}
	return sum(
		_row_monthly_amount(r, flt(ssa[0].base), context)
		for r in structure.earnings
		if _is_pf_wage_row(r, mapping) and not r.statistical_component
	)


def _settings():
	def get(field, default):
		return flt(frappe.db.get_single_value("HR Settings", field)) or default

	return frappe._dict(
		multiplier=get("ot_rate_multiplier", 2),
		days=get("ot_wage_divisor_days", 26),
		hours=get("ot_wage_divisor_hours", 8),
		quarter_limit=get("ot_quarterly_limit_hours", 144),
	)


def _quarter_hours(company, to_date):
	"""Payable OT hours per employee from the start of to_date's calendar quarter."""
	to_date = getdate(to_date)
	quarter_start = add_months(get_first_day(to_date), -((to_date.month - 1) % 3))
	rows = overtime_register({"company": company, "from_date": quarter_start, "to_date": to_date})[1]
	return {r["employee"]: flt(r.get("ot_hours")) for r in rows}


def _upsert(employee, company, payroll_date, amount, submit):
	existing = frappe.get_all(
		"Additional Salary",
		filters={
			"employee": employee,
			"salary_component": OVERTIME_COMPONENT,
			"payroll_date": payroll_date,
			"docstatus": ("<", 2),
		},
		fields=["name", "docstatus"],
		limit=1,
	)
	if existing and existing[0].docstatus == 1:
		return "submitted-exists"

	if existing:
		doc = frappe.get_doc("Additional Salary", existing[0].name)
		doc.amount = amount
		status = "updated"
	else:
		doc = frappe.get_doc(
			{
				"doctype": "Additional Salary",
				"employee": employee,
				"company": company,
				"salary_component": OVERTIME_COMPONENT,
				"amount": amount,
				"payroll_date": payroll_date,
				"overwrite_salary_structure_amount": 1,
			}
		)
		status = "created"

	if submit:
		# Overtime is computed from attendance, not requested — HR running this
		# with submit=1 is the approval.
		frappe.flags.ignore_additional_salary_approval = True
		try:
			doc.approval_status = "Approved"
			doc.save()
			doc.submit()
		finally:
			frappe.flags.ignore_additional_salary_approval = False
	else:
		doc.save()
	return status
