# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, get_link_to_form, getdate

from indian_hrms_compliance.payroll.doctype.payroll_period.payroll_period import get_payroll_period


class DuplicateAssignment(frappe.ValidationError):
	pass


class SalaryStructureAssignment(Document):
	def validate(self):
		self.validate_dates()
		self.validate_company()
		self.validate_income_tax_slab()
		self.set_payroll_payable_account()

		if not self.get("payroll_cost_centers"):
			self.set_payroll_cost_centers()

		self.validate_cost_centers()
		self.warn_about_missing_opening_entries()

	def on_update_after_submit(self):
		self.validate_cost_centers()

	def validate_dates(self):
		joining_date, relieving_date = frappe.db.get_value(
			"Employee", self.employee, ["date_of_joining", "relieving_date"]
		)

		if self.from_date:
			if frappe.db.exists(
				"Salary Structure Assignment",
				{"employee": self.employee, "from_date": self.from_date, "docstatus": 1},
			):
				frappe.throw(
					_("Salary Structure Assignment for Employee already exists"), DuplicateAssignment
				)

			if joining_date and getdate(self.from_date) < joining_date:
				frappe.throw(
					_("From Date {0} cannot be before employee's joining Date {1}").format(
						self.from_date, joining_date
					)
				)

			# flag - old_employee is for migrating the old employees data via patch
			if relieving_date and getdate(self.from_date) > relieving_date and not self.flags.old_employee:
				frappe.throw(
					_("From Date {0} cannot be after employee's relieving Date {1}").format(
						self.from_date, relieving_date
					)
				)

	def validate_company(self):
		salary_structure_company = frappe.db.get_value(
			"Salary Structure", self.salary_structure, "company", cache=True
		)
		if self.company != salary_structure_company:
			frappe.throw(
				_("Salary Structure {0} does not belong to company {1}").format(
					frappe.bold(self.salary_structure), frappe.bold(self.company)
				)
			)

	def validate_income_tax_slab(self):
		tax_component = get_tax_component(self.salary_structure)
		if tax_component and not self.income_tax_slab:
			frappe.throw(
				_(
					"Income Tax Slab is mandatory since the Salary Structure {0} has a tax component {1}"
				).format(
					get_link_to_form("Salary Structure", self.salary_structure), frappe.bold(tax_component)
				),
				exc=frappe.MandatoryError,
				title=_("Missing Mandatory Field"),
			)

		if not self.income_tax_slab:
			return

		income_tax_slab_currency = frappe.db.get_value("Income Tax Slab", self.income_tax_slab, "currency")
		if self.currency != income_tax_slab_currency:
			frappe.throw(
				_("Currency of selected Income Tax Slab should be {0} instead of {1}").format(
					self.currency, income_tax_slab_currency
				)
			)

	def set_payroll_payable_account(self):
		if not self.payroll_payable_account:
			payroll_payable_account = frappe.db.get_value(
				"Company", self.company, "default_payroll_payable_account"
			)
			if not payroll_payable_account:
				payroll_payable_account = frappe.db.get_value(
					"Account",
					{
						"account_name": _("Payroll Payable"),
						"company": self.company,
						"account_currency": frappe.db.get_value("Company", self.company, "default_currency"),
						"is_group": 0,
					},
				)
			self.payroll_payable_account = payroll_payable_account

	@frappe.whitelist()
	def set_payroll_cost_centers(self):
		self.payroll_cost_centers = []
		default_payroll_cost_center = self.get_payroll_cost_center()
		if default_payroll_cost_center:
			self.append(
				"payroll_cost_centers", {"cost_center": default_payroll_cost_center, "percentage": 100}
			)

	def get_payroll_cost_center(self):
		payroll_cost_center = frappe.db.get_value("Employee", self.employee, "payroll_cost_center")
		if not payroll_cost_center and self.department:
			payroll_cost_center = frappe.db.get_value("Department", self.department, "payroll_cost_center")

		return payroll_cost_center

	def validate_cost_centers(self):
		if not self.get("payroll_cost_centers"):
			return

		total_percentage = 0
		for entry in self.payroll_cost_centers:
			company = frappe.db.get_value("Cost Center", entry.cost_center, "company")
			if company != self.company:
				frappe.throw(
					_("Row {0}: Cost Center {1} does not belong to Company {2}").format(
						entry.idx, frappe.bold(entry.cost_center), frappe.bold(self.company)
					),
					title=_("Invalid Cost Center"),
				)

			total_percentage += flt(entry.percentage)

		if total_percentage != 100:
			frappe.throw(_("Total percentage against cost centers should be 100"))

	def warn_about_missing_opening_entries(self):
		if (
			self.are_opening_entries_required()
			and not self.taxable_earnings_till_date
			and not self.tax_deducted_till_date
		):
			msg = _("Could not find any salary slip(s) for the employee {0}").format(self.employee)
			msg += "<br><br>"
			msg += _(
				"Please specify {0} and {1} (if any), for the correct tax calculation in future salary slips."
			).format(
				frappe.bold(_("Taxable Earnings Till Date")),
				frappe.bold(_("Tax Deducted Till Date")),
			)
			frappe.msgprint(
				msg,
				indicator="orange",
				title=_("Missing Opening Entries"),
			)

	@frappe.whitelist()
	def are_opening_entries_required(self) -> bool:
		if not get_tax_component(self.salary_structure):
			return False

		return True


def get_assigned_salary_structure(employee, on_date):
	if not employee or not on_date:
		return None
	salary_structure = frappe.db.sql(
		"""
		select salary_structure from `tabSalary Structure Assignment`
		where employee=%(employee)s
		and docstatus = 1
		and %(on_date)s >= from_date order by from_date desc limit 1""",
		{
			"employee": employee,
			"on_date": on_date,
		},
	)
	return salary_structure[0][0] if salary_structure else None


@frappe.whitelist()
def get_employee_currency(employee):
	employee_currency = frappe.db.get_value("Salary Structure Assignment", {"employee": employee}, "currency")
	if not employee_currency:
		frappe.throw(
			_("There is no Salary Structure assigned to {0}. First assign a Salary Structure.").format(
				employee
			)
		)
	return employee_currency


def get_tax_component(salary_structure: str) -> str | None:
	salary_structure = frappe.get_cached_doc("Salary Structure", salary_structure)
	for d in salary_structure.deductions:
		if cint(d.variable_based_on_taxable_salary) and not d.formula and not flt(d.amount):
			return d.salary_component
	return None


def _annual_income_tax(slab, taxable):
	tax = 0.0
	for s in slab.slabs:
		frm_a = flt(s.from_amount)
		to_a = flt(s.to_amount) or taxable  # 0 to_amount = no upper bound
		if taxable > frm_a:
			tax += (min(taxable, to_a) - frm_a) * flt(s.percent_deduction) / 100.0
	return tax


def _estimate_monthly_tds(slab_name, monthly_gross):
	"""Rough monthly TDS estimate from an Income Tax Slab. Annualises gross,
	applies the slab's standard deduction, new-regime 87A rebate (nil up to
	₹12L taxable) and 4% cess. Excludes surcharge / marginal relief / chapter
	VI-A — it's an estimate, not the payroll-engine figure."""
	slab = frappe.get_cached_doc("Income Tax Slab", slab_name)
	taxable = max(flt(monthly_gross) * 12 - flt(slab.standard_tax_exemption_amount), 0)
	# 87A rebate: the engine charges tax only above tax_relief_limit.
	if slab.tax_relief_limit and taxable <= flt(slab.tax_relief_limit):
		return 0.0
	annual_tax = _annual_income_tax(slab, taxable)
	# cess / surcharge rows (e.g. 4% Health & Education Cess)
	for c in slab.other_taxes_and_charges or []:
		annual_tax += annual_tax * flt(c.percent) / 100.0
	return flt(annual_tax / 12, 2)


@frappe.whitelist()
def preview_salary(salary_structure, base=0, variable=0, leave_encashment=0, employee=None, income_tax_slab=None):
	"""Interactive payslip preview — evaluates the Salary Structure's formulas
	against the supplied base / variable / leave-encashment.

	Employee-aware where context is given:
	  - PF is skipped (flagged) when the employee has no UAN.
	  - TDS is estimated from the linked Income Tax Slab (else shown as 0).
	Earnings are evaluated first, then deductions with `gross_pay` available."""
	from datetime import date as _date
	from math import ceil, floor

	from frappe.utils import get_first_day, get_last_day, rounded

	from indian_hrms_compliance.payroll.doctype.salary_slip.salary_slip import _safe_eval

	base, variable, le = flt(base), flt(variable), flt(leave_encashment)
	ss = frappe.get_doc("Salary Structure", salary_structure)

	g = {
		"int": int, "float": float, "long": int, "round": round, "rounded": rounded,
		"date": _date, "getdate": getdate, "get_first_day": get_first_day,
		"get_last_day": get_last_day, "ceil": ceil, "floor": floor,
	}
	data = {a: 0 for a in frappe.get_all("Salary Component", pluck="salary_component_abbr") if a}
	data.update({"base": base, "variable": variable, "leave_encashment": le, "gross_pay": 0})

	def row_amount(r):
		if r.condition and not _safe_eval(r.condition, g, data):
			return None
		amt = flt(_safe_eval(r.formula, g, data), 2) if (r.amount_based_on_formula and r.formula) else flt(r.amount)
		data[r.abbr] = amt
		return amt

	earnings, gross = [], 0.0
	for r in ss.earnings:
		amt = row_amount(r)
		if amt is None:
			continue
		earnings.append({"component": r.salary_component, "amount": amt, "statistical": bool(r.statistical_component)})
		if not r.statistical_component:
			gross += amt
	if le:
		earnings.append({"component": _("Leave Encashment"), "amount": le, "statistical": False})
		gross += le

	data["gross_pay"] = gross
	emp_uan = frappe.db.get_value("Employee", employee, "uan_number") if employee else None

	deductions, total_ded = [], 0.0
	for r in ss.deductions:
		comp = r.salary_component or ""

		# TDS — estimate from the linked Income Tax Slab.
		if r.variable_based_on_taxable_salary:
			if income_tax_slab:
				tds = _estimate_monthly_tds(income_tax_slab, gross)
				deductions.append({"component": comp, "amount": tds, "note": _("estimated from {0}").format(income_tax_slab)})
				total_ded += tds
			else:
				deductions.append({"component": comp, "amount": 0, "note": _("no Income Tax Slab selected")})
			continue

		# PF — needs the employee to be UAN-registered.
		is_pf = "provident" in comp.lower() or comp.lower() in ("pf", "pf employee", "employee pf")
		if is_pf and employee and not emp_uan:
			data[r.abbr] = 0
			deductions.append({"component": comp, "amount": 0, "note": _("employee has no UAN — PF not applicable")})
			continue

		amt = row_amount(r)
		if amt is None:
			continue
		deductions.append({"component": comp, "amount": amt})
		if not r.statistical_component:
			total_ded += amt

	return {
		"currency": ss.currency,
		"earnings": earnings,
		"deductions": deductions,
		"gross": flt(gross, 2),
		"total_deduction": flt(total_ded, 2),
		"net": flt(gross - total_ded, 2),
	}
