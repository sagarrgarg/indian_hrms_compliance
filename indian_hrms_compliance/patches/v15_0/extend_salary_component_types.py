# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Extend Salary Component.component_type Select options — Phase 6B-1.

The base regional setup ships with:
  Provident Fund / Additional Provident Fund / Provident Fund Loan /
  Professional Tax

For PF ECR + ESI generators (and Form 16 / payroll reports) we need a
richer taxonomy so the generators can pick the right slip rows without
substring matching. Adds:

  Employee State Insurance / Labour Welfare Fund / EPS / EDLI /
  PF Admin Charges / Income Tax / Dearness Allowance / HRA / Basic /
  Other Earning / Other Deduction

Idempotent: re-running merges (does not duplicate) options.
"""

import frappe


EXTENDED_COMPONENT_TYPE_OPTIONS = (
	"\nProvident Fund"
	"\nAdditional Provident Fund"
	"\nProvident Fund Loan"
	"\nProfessional Tax"
	"\nEmployee State Insurance"
	"\nLabour Welfare Fund"
	"\nEPS"
	"\nEDLI"
	"\nPF Admin Charges"
	"\nIncome Tax"
	"\nDearness Allowance"
	"\nHRA"
	"\nBasic"
	"\nOther Earning"
	"\nOther Deduction"
)


def execute():
	cf = frappe.db.exists(
		"Custom Field", {"dt": "Salary Component", "fieldname": "component_type"}
	)
	if not cf:
		# Custom Field hasn't been created yet — the regional india setup
		# creates it. Bail quietly; this patch will be re-applied later.
		print("  Salary Component.component_type Custom Field not found; skipping extension.")
		return

	# Custom Field options are stored as a single newline-separated string.
	# Drop the 'depends_on' too so the new types can apply to Earnings as well.
	frappe.db.set_value(
		"Custom Field",
		cf,
		{
			"options": EXTENDED_COMPONENT_TYPE_OPTIONS,
			"depends_on": "",
		},
	)
	print("  Extended Salary Component.component_type with PF ECR + ESI types")
