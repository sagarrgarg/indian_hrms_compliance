# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe


RESIGNATION_REQUEST_WORKFLOW = "Resignation Request Approval"


def setup_resignation_request_workflow():
	"""Idempotent setup — creates the Workflow, its States and Actions if
	missing. Safe to call from after_install AND from a patch.

	State machine:
	  Draft → Pending Manager Acknowledgement → Pending HR Approval → Approved
	                                                                ↘ Rejected
	  Approved → Withdrawn (rare — HR-only)
	  Draft → Withdrawn (employee abandons)

	For Employer-initiated requests (Termination), HR creates directly in
	Pending HR Approval — there's no manager-ack stage when the employer
	is the actor. The workflow allows that route via Draft → Pending HR Approval
	(action 'Forward to HR').
	"""
	# 1. Workflow States
	state_specs = [
		("Draft", "Primary"),
		("Pending Manager Acknowledgement", "Warning"),
		("Pending HR Approval", "Warning"),
		("Approved", "Success"),
		("Rejected", "Danger"),
		("Withdrawn", "Danger"),
	]
	for name, style in state_specs:
		if not frappe.db.exists("Workflow State", name):
			frappe.get_doc(
				{
					"doctype": "Workflow State",
					"workflow_state_name": name,
					"style": style,
				}
			).insert(ignore_permissions=True)

	# 2. Workflow Actions
	action_specs = [
		"Submit Resignation",
		"Acknowledge",
		"Forward to HR",
		"Approve",
		"Reject",
		"Withdraw",
	]
	for action in action_specs:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc(
				{
					"doctype": "Workflow Action Master",
					"workflow_action_name": action,
				}
			).insert(ignore_permissions=True)

	# 3. The Workflow itself
	if frappe.db.exists("Workflow", RESIGNATION_REQUEST_WORKFLOW):
		return

	workflow = frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": RESIGNATION_REQUEST_WORKFLOW,
			"document_type": "Resignation Request",
			"workflow_state_field": "workflow_state",
			"is_active": 1,
			"send_email_alert": 1,
			"override_status": 0,
			"states": [
				{"state": "Draft", "doc_status": "0", "allow_edit": "Employee"},
				{
					"state": "Pending Manager Acknowledgement",
					"doc_status": "0",
					"allow_edit": "Employee",
				},
				{"state": "Pending HR Approval", "doc_status": "0", "allow_edit": "HR User"},
				{"state": "Approved", "doc_status": "0", "allow_edit": "HR Manager"},
				{"state": "Rejected", "doc_status": "0", "allow_edit": "HR Manager"},
				{"state": "Withdrawn", "doc_status": "0", "allow_edit": "HR Manager"},
			],
			"transitions": [
				# Employee path: Draft → manager → HR → Approved/Rejected
				{
					"state": "Draft",
					"action": "Submit Resignation",
					"next_state": "Pending Manager Acknowledgement",
					"allowed": "Employee",
					"allow_self_approval": 1,
				},
				{
					"state": "Pending Manager Acknowledgement",
					"action": "Acknowledge",
					"next_state": "Pending HR Approval",
					"allowed": "Employee",
					"allow_self_approval": 0,
				},
				{
					"state": "Pending HR Approval",
					"action": "Approve",
					"next_state": "Approved",
					"allowed": "HR Manager",
					"allow_self_approval": 0,
				},
				{
					"state": "Pending HR Approval",
					"action": "Reject",
					"next_state": "Rejected",
					"allowed": "HR Manager",
					"allow_self_approval": 0,
				},
				# Employer / HR shortcut path: Draft → Pending HR (skip manager
				# stage for Termination, Death, Retirement)
				{
					"state": "Draft",
					"action": "Forward to HR",
					"next_state": "Pending HR Approval",
					"allowed": "HR User",
					"allow_self_approval": 1,
				},
				# Withdrawals
				{
					"state": "Draft",
					"action": "Withdraw",
					"next_state": "Withdrawn",
					"allowed": "Employee",
					"allow_self_approval": 1,
				},
				{
					"state": "Pending Manager Acknowledgement",
					"action": "Withdraw",
					"next_state": "Withdrawn",
					"allowed": "Employee",
					"allow_self_approval": 1,
				},
				{
					"state": "Approved",
					"action": "Withdraw",
					"next_state": "Withdrawn",
					"allowed": "HR Manager",
					"allow_self_approval": 1,
				},
			],
		}
	)
	workflow.insert(ignore_permissions=True)
