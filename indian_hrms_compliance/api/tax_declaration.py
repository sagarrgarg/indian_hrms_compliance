# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Employee self-service: income-tax exemption declaration + proof submission
+ old-vs-new regime comparator. ESS endpoints — every method resolves the
caller's Employee and scopes to it.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from indian_hrms_compliance.api import get_current_employee


def _safe_eval_ctx():
	from datetime import date

	from frappe.utils import get_first_day, get_last_day, getdate as gd

	g = {"int": int, "float": float, "long": int, "round": round, "date": date,
	     "getdate": gd, "get_first_day": get_first_day, "get_last_day": get_last_day}
	return g, {}


def _regime_slab(allow_exemption: int, company: str | None):
	"""Latest submitted Income Tax Slab for the regime; company-specific wins,
	else national (blank-company)."""
	rows = frappe.get_all(
		"Income Tax Slab",
		filters={"docstatus": 1, "disabled": 0, "allow_tax_exemption": allow_exemption},
		or_filters=[{"company": company}, {"company": ("in", ("", None))}],
		fields=["name", "company"],
		order_by="effective_from desc",
	)
	if not rows:
		return None
	for r in rows:
		if r.company == company:
			return frappe.get_doc("Income Tax Slab", r.name)
	return frappe.get_doc("Income Tax Slab", rows[0].name)


def _tax_for(slab, taxable):
	from indian_hrms_compliance.payroll.doctype.salary_slip.salary_slip import calculate_tax_by_tax_slab

	if not slab or taxable <= 0:
		return 0.0
	g, l = _safe_eval_ctx()
	tax, _cess = calculate_tax_by_tax_slab(taxable, slab, g, l)
	return flt(tax, 2)


def _current_period(company):
	from indian_hrms_compliance.payroll.doctype.payroll_period.payroll_period import get_payroll_period

	today = nowdate()
	pp = get_payroll_period(today, today, company)
	return pp.name if pp else None


# --------------------------------------------------------------- declaration
@frappe.whitelist()
def get_my_tax_declaration():
	employee = get_current_employee()
	emp = frappe.db.get_value("Employee", employee, ["employee_name", "company"], as_dict=True)
	period = _current_period(emp.company)
	period_start = period_end = None
	if period:
		period_start, period_end = frappe.db.get_value("Payroll Period", period, ["start_date", "end_date"])

	sub_cats = frappe.get_all(
		"Employee Tax Exemption Sub Category",
		filters={"is_active": 1},
		fields=["name", "exemption_category", "max_amount"],
		order_by="exemption_category asc, name asc",
	)

	existing = frappe.db.get_value(
		"Employee Tax Exemption Declaration",
		{"employee": employee, "payroll_period": period},
		["name", "docstatus", "total_declared_amount", "total_exemption_amount"],
		as_dict=True,
	)
	rows = []
	if existing:
		rows = frappe.get_all(
			"Employee Tax Exemption Declaration Category",
			filters={"parent": existing.name},
			fields=["exemption_sub_category", "exemption_category", "max_amount", "amount"],
		)

	# Projected annual income from the latest Salary Structure Assignment base.
	base = frappe.db.get_value(
		"Salary Structure Assignment",
		{"employee": employee, "docstatus": 1},
		"base",
		order_by="from_date desc",
	)
	annual_income = flt(base) * 12 if base else 0

	return {
		"employee": employee,
		"employee_name": emp.employee_name,
		"company": emp.company,
		"payroll_period": period,
		"period_start": str(period_start) if period_start else None,
		"period_end": str(period_end) if period_end else None,
		"sub_categories": sub_cats,
		"declaration": existing,
		"rows": rows,
		"projected_annual_income": annual_income,
		"editable": not existing or existing.docstatus == 0,
	}


@frappe.whitelist()
def save_my_tax_declaration(declarations, submit=0):
	employee = get_current_employee()
	emp = frappe.db.get_value("Employee", employee, ["employee_name", "company"], as_dict=True)
	period = _current_period(emp.company)
	if not period:
		frappe.throw(_("No active Payroll Period found — ask HR to set one up."))

	declarations = json.loads(declarations) if isinstance(declarations, str) else (declarations or [])
	rows = [d for d in declarations if flt(d.get("amount")) > 0]

	existing = frappe.db.get_value(
		"Employee Tax Exemption Declaration",
		{"employee": employee, "payroll_period": period},
		["name", "docstatus"],
		as_dict=True,
	)
	if existing and existing.docstatus == 1:
		frappe.throw(_("Your declaration for this period is already submitted. Contact HR to revise."))

	doc = frappe.get_doc("Employee Tax Exemption Declaration", existing.name) if existing else frappe.new_doc(
		"Employee Tax Exemption Declaration"
	)
	doc.employee = employee
	doc.company = emp.company
	doc.payroll_period = period
	doc.currency = frappe.db.get_value("Company", emp.company, "default_currency") or "INR"
	doc.set("declarations", [])
	for r in rows:
		doc.append("declarations", {
			"exemption_sub_category": r.get("exemption_sub_category"),
			"amount": flt(r.get("amount")),
		})
	doc.flags.ignore_permissions = True
	doc.save()
	if int(submit or 0):
		doc.submit()
	return {"name": doc.name, "docstatus": doc.docstatus, "total_exemption_amount": doc.total_exemption_amount}


# --------------------------------------------------------------- comparator
@frappe.whitelist()
def compare_tax_regimes(annual_income, total_deductions=0, hra_exemption=0):
	"""Compute annual tax under both regimes and recommend the cheaper one.
	Old: income - std - (80C/HRA/etc declared). New: income - new std, no exemptions."""
	employee = get_current_employee()
	company = frappe.db.get_value("Employee", employee, "company")

	annual_income = flt(annual_income)
	total_deductions = flt(total_deductions)
	hra_exemption = flt(hra_exemption)

	old = _regime_slab(1, company)
	new = _regime_slab(0, company)

	old_std = flt(old.standard_tax_exemption_amount) if old else 0
	new_std = flt(new.standard_tax_exemption_amount) if new else 0

	old_taxable = max(0.0, annual_income - old_std - total_deductions - hra_exemption)
	new_taxable = max(0.0, annual_income - new_std)

	old_tax = _tax_for(old, old_taxable)
	new_tax = _tax_for(new, new_taxable)

	recommended = "New" if new_tax <= old_tax else "Old"
	return {
		"old": {
			"slab": old.name if old else None,
			"standard_deduction": old_std,
			"other_deductions": total_deductions + hra_exemption,
			"taxable": old_taxable,
			"tax": old_tax,
		},
		"new": {
			"slab": new.name if new else None,
			"standard_deduction": new_std,
			"other_deductions": 0,
			"taxable": new_taxable,
			"tax": new_tax,
		},
		"recommended": recommended,
		"savings": abs(round(old_tax - new_tax, 2)),
	}


# --------------------------------------------------------------- proofs
@frappe.whitelist()
def submit_tax_proof(declaration, proofs=None):
	"""Create a Proof Submission mirroring a submitted declaration. `proofs` is
	an optional list of {exemption_sub_category, amount, file_url}."""
	employee = get_current_employee()
	dec = frappe.db.get_value(
		"Employee Tax Exemption Declaration", declaration,
		["name", "employee", "company", "payroll_period", "currency", "docstatus"], as_dict=True,
	)
	if not dec or dec.employee != employee:
		frappe.throw(_("Declaration not found."))
	if dec.docstatus != 1:
		frappe.throw(_("Submit your declaration before uploading proofs."))

	proofs = json.loads(proofs) if isinstance(proofs, str) else (proofs or [])
	doc = frappe.new_doc("Employee Tax Exemption Proof Submission")
	doc.employee = employee
	doc.company = dec.company
	doc.payroll_period = dec.payroll_period
	doc.currency = dec.currency
	for p in proofs:
		if flt(p.get("amount")) <= 0:
			continue
		doc.append("tax_exemption_proofs", {
			"exemption_sub_category": p.get("exemption_sub_category"),
			"type_of_proof": p.get("type_of_proof") or "Other",
			"amount": flt(p.get("amount")),
		})
	doc.flags.ignore_permissions = True
	doc.insert()
	return {"name": doc.name}
