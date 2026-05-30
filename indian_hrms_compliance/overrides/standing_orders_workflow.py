# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe


STANDING_ORDERS_WORKFLOW = "Standing Orders Process"


def setup_standing_orders_workflow():
	"""Idempotent — Standing Orders state machine per IR Code Sec 28.

	Draft -> Submitted to Certifying Officer -> Certified -> Active
	(Active can later be Superseded automatically when a newer version
	becomes Active — that transition is set by the controller, not the
	workflow.)
	"""
	state_specs = [
		("Draft", "Primary"),
		("Submitted to Certifying Officer", "Warning"),
		("Certified", "Info"),
		("Active", "Success"),
		("Superseded", "Inverse"),
	]
	for name, style in state_specs:
		if not frappe.db.exists("Workflow State", name):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": name, "style": style}
			).insert(ignore_permissions=True)

	action_specs = [
		"Submit to Certifying Officer",
		"Mark Certified",
		"Activate",
		"Supersede",
	]
	for action in action_specs:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc(
				{"doctype": "Workflow Action Master", "workflow_action_name": action}
			).insert(ignore_permissions=True)

	if frappe.db.exists("Workflow", STANDING_ORDERS_WORKFLOW):
		return

	frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": STANDING_ORDERS_WORKFLOW,
			"document_type": "Standing Orders",
			"workflow_state_field": "workflow_state",
			"is_active": 1,
			"send_email_alert": 0,
			"override_status": 0,
			"states": [
				{"state": "Draft", "doc_status": "0", "allow_edit": "HR Manager"},
				{"state": "Submitted to Certifying Officer", "doc_status": "0", "allow_edit": "HR Manager"},
				{"state": "Certified", "doc_status": "0", "allow_edit": "HR Manager"},
				{"state": "Active", "doc_status": "1", "allow_edit": "HR Manager"},
				{"state": "Superseded", "doc_status": "1", "allow_edit": "HR Manager"},
			],
			"transitions": [
				{
					"state": "Draft",
					"action": "Submit to Certifying Officer",
					"next_state": "Submitted to Certifying Officer",
					"allowed": "HR Manager",
					"allow_self_approval": 1,
				},
				{
					"state": "Submitted to Certifying Officer",
					"action": "Mark Certified",
					"next_state": "Certified",
					"allowed": "HR Manager",
					"allow_self_approval": 1,
				},
				{
					"state": "Certified",
					"action": "Activate",
					"next_state": "Active",
					"allowed": "HR Manager",
					"allow_self_approval": 1,
				},
				{
					"state": "Active",
					"action": "Supersede",
					"next_state": "Superseded",
					"allowed": "HR Manager",
					"allow_self_approval": 1,
				},
			],
		}
	).insert(ignore_permissions=True)
