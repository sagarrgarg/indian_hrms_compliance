# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today


class Form16(Document):
	def validate(self):
		self._recompute_derived_lines()
		self._recompute_form_12ba_total()
		self._stamp_issued_on()

	def _recompute_derived_lines(self):
		# 3 = 1 - 2
		self.balance_after_sec10 = flt(self.gross_salary) - flt(self.section_10_exemptions)
		# 5 = 3 - 4
		self.income_under_salaries = flt(self.balance_after_sec10) - flt(self.section_16_deductions)
		# 7 = 5 + 6
		self.gross_total_income = flt(self.income_under_salaries) + flt(self.other_income)
		# 9 = 7 - 8
		self.taxable_income = max(
			flt(self.gross_total_income) - flt(self.chapter_via_deductions), 0
		)
		# 13 = 10 + 11 + 12
		self.tax_liability = (
			flt(self.tax_payable) + flt(self.surcharge) + flt(self.health_education_cess)
		)
		# 15 = 13 - 14
		self.net_tax_payable = max(flt(self.tax_liability) - flt(self.relief_us_89), 0)
		# 17 = 15 - 16 (signed)
		self.tds_balance = flt(self.net_tax_payable) - flt(self.tds_deducted)

	def _recompute_form_12ba_total(self):
		# Child controllers don't auto-fire on parent save in Frappe — derive
		# taxable_value here too so the form 12BA total is always coherent.
		for p in self.perquisites or []:
			if not flt(p.taxable_value):
				p.taxable_value = flt(p.value_of_perquisite) - flt(p.amount_recovered)
		self.form_12ba_total = sum(
			flt(p.taxable_value) for p in (self.perquisites or [])
		)

	def _stamp_issued_on(self):
		if self.issue_status == "Issued" and not self.issued_on:
			self.issued_on = today()
		elif self.issue_status != "Issued":
			self.issued_on = None


# ---- whitelisted generation helpers ----


@frappe.whitelist()
def generate_form_16(employee, fiscal_year, company):
	"""Idempotent: returns existing Form 16 if present for (employee, FY, company),
	else creates a draft populated from Salary Slips + Tax Exemption
	Declaration aggregated over the FY.

	Drafts are HR's starting point — manual edits override the autofill on
	the next save."""
	existing = frappe.db.exists(
		"Form 16",
		{"employee": employee, "fiscal_year": fiscal_year, "company": company},
	)
	if existing:
		return existing

	fy = frappe.db.get_value(
		"Fiscal Year", fiscal_year, ["year_start_date", "year_end_date"], as_dict=True
	)
	if not fy:
		frappe.throw(_("Fiscal Year {0} not found.").format(fiscal_year))

	emp = frappe.db.get_value(
		"Employee",
		employee,
		[
			"employee_name",
			"pan_number",
			"date_of_joining",
			"relieving_date",
			"current_address",
		],
		as_dict=True,
	)
	if not emp:
		frappe.throw(_("Employee {0} not found.").format(employee))

	# Active period clamp: mid-FY joiner/exit gets a narrower window.
	period_from = max(getdate(fy.year_start_date), getdate(emp.date_of_joining)) if emp.date_of_joining else fy.year_start_date
	period_to = min(getdate(fy.year_end_date), getdate(emp.relieving_date)) if emp.relieving_date else fy.year_end_date

	# Aggregate Salary Slip earnings + deductions for the period.
	gross, tds_deducted, section_10, sec_16, chapter_via = _aggregate_salary_slips(
		employee, period_from, period_to
	)

	doc = frappe.get_doc(
		{
			"doctype": "Form 16",
			"employee": employee,
			"fiscal_year": fiscal_year,
			"company": company,
			"employer_pan": frappe.db.get_value("Company", company, "pan") or "",
			"employer_tan": "",  # HR fills
			"employee_pan": emp.pan_number or "",
			"employee_address": emp.current_address or "",
			"period_from": period_from,
			"period_to": period_to,
			"gross_salary": gross,
			"section_10_exemptions": section_10,
			"section_16_deductions": sec_16,
			"chapter_via_deductions": chapter_via,
			"tds_deducted": tds_deducted,
			"issue_status": "Draft",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


@frappe.whitelist()
def bulk_generate_form_16(company, fiscal_year):
	"""Generate Form 16 for every Employee of this Company who has at
	least one submitted Salary Slip in the FY. Returns count + names."""
	fy = frappe.db.get_value(
		"Fiscal Year", fiscal_year, ["year_start_date", "year_end_date"], as_dict=True
	)
	if not fy:
		frappe.throw(_("Fiscal Year {0} not found.").format(fiscal_year))

	employees_with_slips = frappe.db.sql(
		"""
		SELECT DISTINCT employee
		FROM `tabSalary Slip`
		WHERE company = %s AND docstatus = 1
		  AND start_date BETWEEN %s AND %s
		""",
		(company, fy.year_start_date, fy.year_end_date),
		as_dict=True,
	)

	created = []
	for row in employees_with_slips:
		try:
			name = generate_form_16(row.employee, fiscal_year, company)
			created.append(name)
		except Exception:
			frappe.log_error(
				title=f"Form 16 generation failed: {row.employee} / {fiscal_year}",
				message=frappe.get_traceback(),
			)
	frappe.msgprint(
		_("Form 16 draft(s) processed for {0} employees in {1} / {2}").format(
			len(created), company, fiscal_year
		)
	)
	return {"count": len(created), "names": created}


def _aggregate_salary_slips(employee, period_from, period_to):
	"""Pull Salary Slip aggregates for the period. Returns
	(gross, tds_deducted, section_10_exemptions, section_16_deductions,
	chapter_via_deductions).

	Section 10 / 16 / Chapter VI-A are sourced from the Employee Tax
	Exemption Declaration for the FY when present; falls back to 0."""
	# Gross from Salary Slips
	gross = flt(
		frappe.db.sql(
			"""
			SELECT COALESCE(SUM(gross_pay), 0)
			FROM `tabSalary Slip`
			WHERE employee = %s AND docstatus = 1
			  AND start_date BETWEEN %s AND %s
			""",
			(employee, period_from, period_to),
		)[0][0]
	)

	# TDS deducted (Income Tax / TDS component)
	tds = flt(
		frappe.db.sql(
			"""
			SELECT COALESCE(SUM(sd.amount), 0)
			FROM `tabSalary Detail` sd
			JOIN `tabSalary Slip` ss ON ss.name = sd.parent
			WHERE ss.employee = %s AND ss.docstatus = 1
			  AND ss.start_date BETWEEN %s AND %s
			  AND sd.parentfield = 'deductions'
			  AND sd.salary_component IN ('Income Tax', 'TDS')
			""",
			(employee, period_from, period_to),
		)[0][0]
	)

	# Section 10 / 16 / Chapter VI-A from Tax Exemption Declaration for the FY.
	# Take the latest declaration if multiple exist.
	decl = frappe.db.get_value(
		"Employee Tax Exemption Declaration",
		{
			"employee": employee,
			"docstatus": 1,
			"payroll_period": ("like", f"%{period_to.year}%"),
		},
		[
			"total_exemption_amount",
			"total_declared_amount",
		],
		as_dict=True,
		order_by="modified desc",
	) or {}

	chapter_via = flt(decl.get("total_declared_amount"))
	section_10 = flt(decl.get("total_exemption_amount"))
	# Standard deduction (Sec 16) = 50000 for FY 2023-24+, ERPNext computes
	# automatically; we leave HR to fill the actual when generating.
	section_16 = 50000.0

	return gross, tds, section_10, section_16, chapter_via
