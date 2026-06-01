# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Slip-time, state-aware Professional Tax + Labour Welfare Fund.

A single Salary Structure can serve employees across states: at slip time we
resolve the employee's work state and overwrite the mapped PT / LWF deduction
with the amount that state actually mandates (PT from the state's slab, LWF as
the state's flat employee contribution in its filing month).

Opt-in & backward-compatible: nothing happens unless the Company has a
Statutory Component Mapping pointing at the PT / LWF salary components.
"""

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
		return
	state = frappe.get_cached_doc("Indian State", state_code)

	month = getdate(slip.start_date).month
	gender = frappe.db.get_value("Employee", slip.employee, "gender")

	# --- Professional Tax (slab-driven) ---
	if mapping.get("pt_component") and state.pt_applicable:
		from indian_hrms_compliance.overrides.pt_return_generator import _compute_expected_pt

		pt = flt(_compute_expected_pt(state, flt(slip.gross_pay), gender, month))
		_set_deduction(slip, mapping.pt_component, pt)

	# --- LWF employee contribution (flat, only in the state's filing month) ---
	if mapping.get("lwf_employee_component") and state.lwf_applicable and _is_lwf_month(state, month):
		_set_deduction(slip, mapping.lwf_employee_component, flt(state.lwf_employee_amount))


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
	abbr = frappe.db.get_value("Salary Component", component, "salary_component_abbr")
	slip.append(
		"deductions",
		{
			"salary_component": component,
			"abbr": abbr,
			"amount": amount,
			"default_amount": amount,
			"exempted_from_income_tax": 1,
		},
	)
