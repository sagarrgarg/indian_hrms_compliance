# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe


POSH_WORKFLOW = "POSH Complaint Process"


def setup_posh_workflow():
	"""Idempotent — POSH complaint state machine per Sec 11 of POSH Act 2013.

	Filed → Acknowledged → Inquiry → Findings Recorded → Action Recommended → Closed
	(no parallel happy-path branches — every complaint must go through every
	stage on the record, even No-Action complaints.)
	"""
	state_specs = [
		("Filed", "Danger"),
		("Acknowledged", "Warning"),
		("Inquiry", "Warning"),
		("Findings Recorded", "Warning"),
		("Action Recommended", "Warning"),
		("Closed", "Success"),
	]
	for name, style in state_specs:
		if not frappe.db.exists("Workflow State", name):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": name, "style": style}
			).insert(ignore_permissions=True)

	action_specs = [
		"Acknowledge Receipt",
		"Begin Inquiry",
		"Record Findings",
		"Recommend Action",
		"Close Complaint",
	]
	for action in action_specs:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc(
				{"doctype": "Workflow Action Master", "workflow_action_name": action}
			).insert(ignore_permissions=True)

	if frappe.db.exists("Workflow", POSH_WORKFLOW):
		return

	# Workflow is allowed by "HR Manager" + "HR User" roles — but the
	# permission_query_conditions still gates *visibility* to IC members,
	# so non-IC HR Managers can't actually act on complaints they can't see.
	# This is intentional belt-and-braces: workflow_state has the role
	# check, permission has the visibility check.
	frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": POSH_WORKFLOW,
			"document_type": "POSH Complaint",
			"workflow_state_field": "workflow_state",
			"is_active": 1,
			"send_email_alert": 0,  # POSH uses PWA alerts only — keep email off
			"override_status": 0,
			"states": [
				{"state": "Filed", "doc_status": "0", "allow_edit": "Employee"},
				{"state": "Acknowledged", "doc_status": "0", "allow_edit": "HR Manager"},
				{"state": "Inquiry", "doc_status": "0", "allow_edit": "HR Manager"},
				{"state": "Findings Recorded", "doc_status": "0", "allow_edit": "HR Manager"},
				{"state": "Action Recommended", "doc_status": "0", "allow_edit": "HR Manager"},
				{"state": "Closed", "doc_status": "0", "allow_edit": "HR Manager"},
			],
			"transitions": [
				{"state": "Filed", "action": "Acknowledge Receipt", "next_state": "Acknowledged", "allowed": "HR Manager", "allow_self_approval": 1},
				{"state": "Acknowledged", "action": "Begin Inquiry", "next_state": "Inquiry", "allowed": "HR Manager", "allow_self_approval": 1},
				{"state": "Inquiry", "action": "Record Findings", "next_state": "Findings Recorded", "allowed": "HR Manager", "allow_self_approval": 1},
				{"state": "Findings Recorded", "action": "Recommend Action", "next_state": "Action Recommended", "allowed": "HR Manager", "allow_self_approval": 1},
				{"state": "Action Recommended", "action": "Close Complaint", "next_state": "Closed", "allowed": "HR Manager", "allow_self_approval": 1},
			],
		}
	).insert(ignore_permissions=True)
