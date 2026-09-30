# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Slip-time, state-aware Professional Tax + Labour Welfare Fund.

A single Salary Structure can serve employees across states: at slip time we
resolve the employee's work state and overwrite the mapped PT / LWF deduction
with the amount that state actually mandates (PT from the state's slab, LWF in
the state's deduction months, flat or a capped percentage of gross).

The employer LWF share goes on the slip as a statistical earning (employer cost,
never a deduction) when the mapping names an lwf_employer_component.

Opt-in & backward-compatible: nothing happens unless the Company has a
Statutory Component Mapping pointing at the PT / LWF salary components.
"""

from decimal import ROUND_HALF_UP, Decimal

import frappe
from frappe.utils import flt, getdate


def apply_state_statutory_overrides(slip):
	from indian_hrms_compliance.hr.doctype.statutory_component_mapping.statutory_component_mapping import (
		get_mapping_for_company,
	)

	mapping = get_mapping_for_company(slip.company)
	if not mapping:
		return
	if not (mapping.get("pt_component") or mapping.get("lwf_employee_component")):
		return

	from indian_hrms_compliance.overrides._state_resolver import resolve_employee_state

	state_code = resolve_employee_state(slip.employee)
	if not state_code or not frappe.db.exists("Indian State", state_code):
		frappe.log_error(
			title="PT/LWF: work state not resolved",
			message=f"Employee {slip.employee} ({slip.name or 'new slip'}): no Indian State from Branch "
			f"State, Office address, Company address or HR Settings default ({state_code!r}). "
			"PT / LWF not applied.",
		)
		return
	state = frappe.get_cached_doc("Indian State", state_code)

	month = getdate(slip.start_date).month
	gender = frappe.db.get_value("Employee", slip.employee, "gender")

	# --- Professional Tax (slab-driven) ---
	if mapping.get("pt_component") and state.pt_applicable:
		from indian_hrms_compliance.overrides.pt_return_generator import _compute_expected_pt

		pt = flt(_compute_expected_pt(state, flt(slip.gross_pay), gender, month))
		_set_deduction(slip, mapping.pt_component, pt)

	# --- LWF (only in the state's deduction months) ---
	if mapping.get("lwf_employee_component") and state.lwf_applicable and _is_lwf_month(state, month):
		employee, employer = lwf_amounts(state, flt(slip.gross_pay)) if flt(slip.payment_days) else (0, 0)
		_set_deduction(slip, mapping.lwf_employee_component, employee)
		if mapping.get("lwf_employer_component"):
			_set_statistical_earning(slip, mapping.lwf_employer_component, employer)


def lwf_amounts(state, gross):
	"""(employee, employer) LWF for one deduction period, in whole rupees.

	Flat states: the state's amounts as-is.
	Percentage of Gross (Haryana): employee = % x gross capped at the employee
	amount; employer = multiple x employee, capped at the employer amount."""
	if (state.get("lwf_calculation") or "Flat") != "Percentage of Gross":
		return flt(state.lwf_employee_amount), flt(state.lwf_employer_amount)

	employee = flt(gross) * flt(state.lwf_employee_percent) / 100
	if flt(state.lwf_employee_amount):
		employee = min(employee, flt(state.lwf_employee_amount))
	employer = employee * flt(state.get("lwf_employer_multiplier") or 0)
	if flt(state.lwf_employer_amount):
		employer = min(employer, flt(state.lwf_employer_amount))
	return _round_rupee(employee), _round_rupee(employer)


def _round_rupee(value):
	return float(Decimal(str(flt(value))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _is_lwf_month(state, month) -> bool:
	freq = (state.lwf_filing_frequency or "Monthly").strip().lower()
	if freq.startswith("month"):
		return True
	if "half" in freq:
		return month in (6, 12)
	if freq.startswith("year") or freq.startswith("annual"):
		return month == 12
	if "quarter" in freq:
		return month in (3, 6, 9, 12)
	return True


def _set_statistical_earning(slip, component, amount):
	"""Employer-side contribution: a statistical earning row, so it shows on the
	slip and in reports without touching gross or net pay."""
	amount = flt(amount)
	for row in slip.get("earnings") or []:
		if row.salary_component == component:
			row.amount = amount
			row.default_amount = amount
			row.statistical_component = 1
			row.do_not_include_in_total = 1
			return
	if amount <= 0:
		return
	abbr = frappe.db.get_value("Salary Component", component, "salary_component_abbr")
	slip.append(
		"earnings",
		{
			"salary_component": component,
			"abbr": abbr,
			"amount": amount,
			"default_amount": amount,
			"statistical_component": 1,
			# Slip totals skip rows by this flag, not by statistical_component.
			"do_not_include_in_total": 1,
			"depends_on_payment_days": 0,
		},
	)


def _set_deduction(slip, component, amount):
	"""Overwrite an existing deduction row's amount, or append one if the state
	mandates a non-zero amount and the structure didn't include it."""
	amount = flt(amount)
	for row in slip.get("deductions") or []:
		if row.salary_component == component:
			row.amount = amount
			row.default_amount = amount
			return
	if amount <= 0:
		return
	# PT is deductible u/s 16(iii); LWF is not — take it from the component master.
	abbr, exempt = frappe.db.get_value(
		"Salary Component", component, ["salary_component_abbr", "exempted_from_income_tax"]
	)
	slip.append(
		"deductions",
		{
			"salary_component": component,
			"abbr": abbr,
			"amount": amount,
			"default_amount": amount,
			"exempted_from_income_tax": exempt,
		},
	)
