# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Data Erasure Request workflow setup — Phase 6D.

State machine:
  Filed → Under Legal Review → Decision Made → Executed
                            ↘ Rejected
"""

import frappe


ERASURE_WORKFLOW = "Data Erasure Request Workflow"


def setup_data_erasure_workflow():
	"""Idempotent — creates Workflow + States + Actions if missing."""
	state_specs = [
		("Filed", "Primary"),
		("Under Legal Review", "Warning"),
		("Decision Made", "Info"),
		("Executed", "Success"),
		("Rejected", "Danger"),
	]
	for name, style in state_specs:
		if not frappe.db.exists("Workflow State", name):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": name, "style": style}
			).insert(ignore_permissions=True)

	action_specs = [
		"Send for Legal Review",
		"Record Legal Outcome",
		"Reject Request",
		"Execute Erasure",
	]
	for action in action_specs:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc(
				{"doctype": "Workflow Action Master", "workflow_action_name": action}
			).insert(ignore_permissions=True)

	if frappe.db.exists("Workflow", ERASURE_WORKFLOW):
		return

	frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": ERASURE_WORKFLOW,
			"document_type": "Data Erasure Request",
			"workflow_state_field": "workflow_state",
			"is_active": 1,
			"send_email_alert": 1,
			"override_status": 0,
			"states": [
				{"state": "Filed", "doc_status": "0", "allow_edit": "HR Manager"},
				{"state": "Under Legal Review", "doc_status": "0", "allow_edit": "HR Manager"},
				{"state": "Decision Made", "doc_status": "0", "allow_edit": "HR Manager"},
				{"state": "Executed", "doc_status": "0", "allow_edit": "HR Manager"},
				{"state": "Rejected", "doc_status": "0", "allow_edit": "HR Manager"},
			],
			"transitions": [
				{
					"state": "Filed",
					"action": "Send for Legal Review",
					"next_state": "Under Legal Review",
					"allowed": "HR Manager",
					"allow_self_approval": 1,
				},
				{
					"state": "Under Legal Review",
					"action": "Record Legal Outcome",
					"next_state": "Decision Made",
					"allowed": "HR Manager",
					"allow_self_approval": 1,
				},
				{
					"state": "Under Legal Review",
					"action": "Reject Request",
					"next_state": "Rejected",
					"allowed": "HR Manager",
					"allow_self_approval": 1,
				},
				{
					"state": "Decision Made",
					"action": "Execute Erasure",
					"next_state": "Executed",
					"allowed": "HR Manager",
					"allow_self_approval": 1,
				},
				{
					"state": "Decision Made",
					"action": "Reject Request",
					"next_state": "Rejected",
					"allowed": "HR Manager",
					"allow_self_approval": 1,
				},
			],
		}
	).insert(ignore_permissions=True)
