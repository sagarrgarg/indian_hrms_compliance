# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Control Register — the auto-generated Risk-Control Matrix (RCM).

A view over what execution already captured: every Critical / Standard task with
its tier, DRI, segregation-of-duties pair, cadence and last evidence. The Phase-5
Regulated payoff — zero extra data entry; the same rows as
`api.governance.get_control_register`.
"""

import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	from indian_hrms_compliance.api.cockpit import _scope_company
	from indian_hrms_compliance.api.governance import _assert_company_in_scope, _control_register_rows

	# Scope like the whitelisted API: default to the HR user's company and never
	# let an explicit company reach a sibling company's control matrix.
	company = filters.get("company") or _scope_company()
	_assert_company_in_scope(company)
	rows = _control_register_rows(company)
	if filters.get("statutory_only"):
		rows = [r for r in rows if r.get("statutory")]

	columns = [
		{"label": _("Task"), "fieldname": "task_name", "fieldtype": "Data", "width": 220},
		{"label": _("KRA"), "fieldname": "kra", "fieldtype": "Link", "options": "KRA", "width": 140},
		{"label": _("Tier"), "fieldname": "risk_tier", "fieldtype": "Data", "width": 80},
		{"label": _("Statutory"), "fieldname": "statutory", "fieldtype": "Check", "width": 70},
		{"label": _("DRI"), "fieldname": "dri", "fieldtype": "Link", "options": "User", "width": 150},
		{"label": _("Cadence"), "fieldname": "cadence", "fieldtype": "Data", "width": 90},
		{"label": _("Control"), "fieldname": "control", "fieldtype": "Data", "width": 130},
		{"label": _("SoD"), "fieldname": "sod_pair", "fieldtype": "Data", "width": 150},
		{"label": _("Last Evidence"), "fieldname": "last_evidence_on", "fieldtype": "Data", "width": 150},
		{"label": _("Last Approved By"), "fieldname": "last_approved_by", "fieldtype": "Link", "options": "User", "width": 150},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 140},
	]
	return columns, rows
