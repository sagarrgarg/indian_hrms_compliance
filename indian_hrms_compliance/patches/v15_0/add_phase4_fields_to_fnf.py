# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def get_phase4_fnf_fields():
	"""Custom Fields adding the notice-period math + TDS-on-FnF surface to
	Full and Final Statement.

	resignation_request is the bridge from Stage 1; the rest are computed
	in overrides/full_and_final_extension.compute_phase4_lines."""
	return {
		"Full and Final Statement": [
			{
				"fieldname": "phase4_notice_section",
				"fieldtype": "Section Break",
				"label": "Notice Period & TDS",
				"insert_after": "total_receivable_amount",
				"collapsible": 0,
				"description": (
					"Auto-computed from the linked Resignation Request and Employee's "
					"last Salary Slip. Recompute via the 'Recompute Notice + TDS' button."
				),
			},
			{
				"fieldname": "resignation_request",
				"fieldtype": "Link",
				"options": "Resignation Request",
				"label": "Resignation Request",
				"insert_after": "phase4_notice_section",
				"description": "Auto-linked when one exists for this Employee + Company. Drives notice math.",
			},
			{
				"fieldname": "notice_required_days",
				"fieldtype": "Int",
				"label": "Notice Required (days)",
				"insert_after": "resignation_request",
				"read_only": 1,
				"fetch_from": "resignation_request.notice_required_days",
			},
			{
				"fieldname": "notice_served_days",
				"fieldtype": "Int",
				"label": "Notice Served (days)",
				"insert_after": "notice_required_days",
				"read_only": 1,
				"description": "relieving_date − Resignation submission_date.",
			},
			{
				"fieldname": "notice_balance_days",
				"fieldtype": "Int",
				"label": "Notice Balance (days)",
				"insert_after": "notice_served_days",
				"read_only": 1,
				"description": "Required − Served. Positive = short notice. Negative or zero = full served.",
			},
			{
				"fieldname": "column_break_phase4_a",
				"fieldtype": "Column Break",
				"insert_after": "notice_balance_days",
			},
			{
				"fieldname": "per_day_basic_for_recovery",
				"fieldtype": "Currency",
				"label": "Per-day Rate (auto)",
				"insert_after": "column_break_phase4_a",
				"read_only": 1,
				"description": (
					"From last Salary Slip basic ÷ days-in-month divisor. The basis "
					"(Basic / Basic+DA / Gross) and divisor are read from HR Settings."
				),
			},
			{
				"fieldname": "notice_balance_amount",
				"fieldtype": "Currency",
				"label": "Notice Balance Amount (auto)",
				"insert_after": "per_day_basic_for_recovery",
				"read_only": 1,
				"description": (
					"Signed: positive on Short Notice (recovered from employee), "
					"negative on Pay in Lieu (payable to employee)."
				),
			},
			{
				"fieldname": "negotiated_waiver_amount",
				"fieldtype": "Currency",
				"label": "Negotiated Waiver / Override",
				"insert_after": "notice_balance_amount",
				"description": (
					"HR override — replaces the auto-computed Notice Balance "
					"Amount on the FnF line when allow_negotiated_notice_waiver is on."
				),
			},
			{
				"fieldname": "tds_on_final_settlement",
				"fieldtype": "Currency",
				"label": "TDS on Final Settlement (auto)",
				"insert_after": "negotiated_waiver_amount",
				"read_only": 1,
				"description": (
					"Computed = projected annual tax − YTD TDS already deducted. "
					"Added to Receivables. Requires an active Income Tax Slab for the "
					"Employee's Payroll Period."
				),
			},
		],
	}


def execute():
	create_custom_fields(get_phase4_fnf_fields(), ignore_validate=True)
	print("  Added Phase 4 notice/TDS Custom Fields to Full and Final Statement")
