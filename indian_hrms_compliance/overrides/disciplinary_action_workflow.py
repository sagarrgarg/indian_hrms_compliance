# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe


DISCIPLINARY_WORKFLOW = "Disciplinary Action Process"


def setup_disciplinary_action_workflow():
	"""Idempotent — Disciplinary state machine.

	Initiated → Show-Cause Issued → Response Received → Under Inquiry →
	Outcome Decided → Closed

	Each state has a HR Manager edit lock; HR User can read.
	"""
	state_specs = [
		("Initiated", "Primary"),
		("Show-Cause Issued", "Warning"),
		("Response Received", "Warning"),
		("Under Inquiry", "Warning"),
		("Outcome Decided", "Danger"),
		("Closed", "Success"),
	]
	for name, style in state_specs:
		if not frappe.db.exists("Workflow State", name):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": name, "style": style}
			).insert(ignore_permissions=True)

	action_specs = [
		"Issue Show-Cause",
		"Record Response",
		"Begin Inquiry",
		"Decide Outcome",
		"Close",
	]
	for action in action_specs:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc(
				{"doctype": "Workflow Action Master", "workflow_action_name": action}
			).insert(ignore_permissions=True)

	if frappe.db.exists("Workflow", DISCIPLINARY_WORKFLOW):
		return
	frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": DISCIPLINARY_WORKFLOW,
			"document_type": "Disciplinary Action",
			"workflow_state_field": "workflow_state",
			"is_active": 1,
			"send_email_alert": 1,
			"override_status": 0,
			"states": [
				{"state": "Initiated", "doc_status": "0", "allow_edit": "HR Manager"},
				{"state": "Show-Cause Issued", "doc_status": "0", "allow_edit": "HR Manager"},
				{"state": "Response Received", "doc_status": "0", "allow_edit": "HR Manager"},
				{"state": "Under Inquiry", "doc_status": "0", "allow_edit": "HR Manager"},
				{"state": "Outcome Decided", "doc_status": "0", "allow_edit": "HR Manager"},
				{"state": "Closed", "doc_status": "0", "allow_edit": "HR Manager"},
			],
			"transitions": [
				{"state": "Initiated", "action": "Issue Show-Cause", "next_state": "Show-Cause Issued", "allowed": "HR Manager", "allow_self_approval": 1},
				{"state": "Show-Cause Issued", "action": "Record Response", "next_state": "Response Received", "allowed": "HR Manager", "allow_self_approval": 1},
				{"state": "Response Received", "action": "Begin Inquiry", "next_state": "Under Inquiry", "allowed": "HR Manager", "allow_self_approval": 1},
				{"state": "Under Inquiry", "action": "Decide Outcome", "next_state": "Outcome Decided", "allowed": "HR Manager", "allow_self_approval": 1},
				{"state": "Outcome Decided", "action": "Close", "next_state": "Closed", "allowed": "HR Manager", "allow_self_approval": 1},
			],
		}
	).insert(ignore_permissions=True)
