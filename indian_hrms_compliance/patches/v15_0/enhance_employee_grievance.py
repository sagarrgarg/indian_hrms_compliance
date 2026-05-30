# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def get_phase5_grievance_fields():
	"""Phase 5 Stage 1 — extend Employee Grievance with company-scoping,
	severity, SLA, workflow state, and Phase-5 linkages."""
	return {
		"Employee Grievance": [
			{
				"fieldname": "company",
				"fieldtype": "Link",
				"options": "Company",
				"label": "Company",
				"insert_after": "raised_by",
				"reqd": 1,
				"in_list_view": 1,
				"in_standard_filter": 1,
				"fetch_from": "raised_by.company",
				"description": "Per company-scoped-hr-docs — every Grievance lives in one Company.",
			},
			{
				"fieldname": "severity",
				"fieldtype": "Select",
				"label": "Severity",
				"options": "Low\nMedium\nHigh\nCritical",
				"default": "Medium",
				"insert_after": "status",
				"in_list_view": 1,
				"in_standard_filter": 1,
				"description": "Drives SLA defaults + escalation cadence from HR Settings.",
			},
			{
				"fieldname": "workflow_state",
				"fieldtype": "Link",
				"options": "Workflow State",
				"label": "Workflow State",
				"insert_after": "severity",
				"no_copy": 1,
				"read_only": 1,
				"in_list_view": 1,
				"in_standard_filter": 1,
			},
			{
				"fieldname": "sla_due_date",
				"fieldtype": "Date",
				"label": "SLA Due Date",
				"insert_after": "workflow_state",
				"read_only": 1,
				"description": "Auto-set from date + severity SLA days. Past this date, SLA scheduler escalates.",
			},
			{
				"fieldname": "last_reminder_sent_on",
				"fieldtype": "Date",
				"label": "Last Reminder Sent On",
				"insert_after": "sla_due_date",
				"read_only": 1,
				"no_copy": 1,
				"hidden": 1,
			},
			{
				"fieldname": "linked_disciplinary_action",
				"fieldtype": "Link",
				"options": "Disciplinary Action",
				"label": "Linked Disciplinary Action",
				"insert_after": "resolution_detail",
				"read_only": 1,
				"description": "Auto-linked when this grievance leads to a Disciplinary Action.",
			},
		],
		"Grievance Type": [
			{
				"fieldname": "default_severity",
				"fieldtype": "Select",
				"label": "Default Severity",
				"options": "Low\nMedium\nHigh\nCritical",
				"default": "Medium",
				"insert_after": "description",
				"description": "Applied to new Grievances of this type when severity isn't set explicitly.",
			},
			{
				"fieldname": "default_sla_days",
				"fieldtype": "Int",
				"label": "Default SLA (days)",
				"insert_after": "default_severity",
				"non_negative": 1,
				"description": "Days from raised_date by which a grievance of this type must be resolved. Overrides HR Settings severity defaults.",
			},
		],
	}


GRIEVANCE_TYPE_SEEDS = [
	{"name": "Compensation", "default_severity": "Medium", "default_sla_days": 30, "description": "Pay, increments, bonuses, overtime, reimbursements."},
	{"name": "Performance Feedback", "default_severity": "Low", "default_sla_days": 21, "description": "Disputes about performance ratings or PIP."},
	{"name": "Workplace Conditions", "default_severity": "Medium", "default_sla_days": 14, "description": "Safety, ergonomics, infrastructure, sanitation."},
	{"name": "Interpersonal / Bullying", "default_severity": "High", "default_sla_days": 14, "description": "Workplace bullying, hostile behaviour (non-POSH — POSH has its own track)."},
	{"name": "Discrimination", "default_severity": "High", "default_sla_days": 14, "description": "Caste / gender / religion / disability — non-POSH."},
	{"name": "Workload / Hours", "default_severity": "Medium", "default_sla_days": 21, "description": "Overwork, shift fairness, on-call burden."},
	{"name": "Manager Behaviour", "default_severity": "High", "default_sla_days": 14, "description": "Manager misconduct that doesn't rise to POSH."},
	{"name": "Policy Breach (Other)", "default_severity": "Medium", "default_sla_days": 21, "description": "Reported breaches of company policy by others."},
	{"name": "Leave / Attendance", "default_severity": "Low", "default_sla_days": 14, "description": "Leave approval / attendance marking disputes."},
	{"name": "Other", "default_severity": "Low", "default_sla_days": 30, "description": "Generic catch-all."},
]


def execute():
	"""Phase 5 Stage 1 — extend Grievance + Grievance Type, seed types."""
	create_custom_fields(get_phase5_grievance_fields(), ignore_validate=True)
	print("  Added Phase 5 Custom Fields to Employee Grievance + Grievance Type")

	# Backfill company on existing Grievance rows from raised_by Employee.
	rows = frappe.db.sql(
		"""
		SELECT g.name, e.company
		FROM `tabEmployee Grievance` g
		JOIN `tabEmployee` e ON e.name = g.raised_by
		WHERE g.company IS NULL OR g.company = ''
		""",
		as_dict=True,
	)
	for r in rows:
		frappe.db.set_value("Employee Grievance", r.name, "company", r.company, update_modified=False)
	if rows:
		print(f"  Backfilled company on {len(rows)} Employee Grievance rows")

	# Seed Grievance Types if missing.
	for spec in GRIEVANCE_TYPE_SEEDS:
		if frappe.db.exists("Grievance Type", spec["name"]):
			# Update defaults if the row exists but our defaults differ.
			frappe.db.set_value(
				"Grievance Type",
				spec["name"],
				{
					"default_severity": spec["default_severity"],
					"default_sla_days": spec["default_sla_days"],
				},
				update_modified=False,
			)
			continue
		frappe.get_doc(
			{
				"doctype": "Grievance Type",
				"name": spec["name"],
				"description": spec["description"],
				"default_severity": spec["default_severity"],
				"default_sla_days": spec["default_sla_days"],
			}
		).insert(ignore_permissions=True)
	print(f"  Seeded {len(GRIEVANCE_TYPE_SEEDS)} Grievance Types")
