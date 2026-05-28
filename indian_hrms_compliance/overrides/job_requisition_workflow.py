# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.utils import get_link_to_form

JOB_REQUISITION_WORKFLOW = "Job Requisition Approval"
APPROVED_STATE = "Approved"


def auto_create_opening_on_approval(doc, method=None):
	"""doc_event on Job Requisition.on_update: when workflow_state transitions
	to 'Approved' and no Job Opening yet exists for this requisition,
	auto-create one."""
	if not _was_just_approved(doc):
		return

	# Idempotency: skip if an Opening already linked to this requisition.
	existing = frappe.db.exists("Job Opening", {"job_requisition": doc.name})
	if existing:
		return

	opening = frappe.get_doc(
		{
			"doctype": "Job Opening",
			"job_title": doc.designation,  # Job Opening uses job_title; designation is what HR requested
			"designation": doc.designation,
			"company": doc.company,
			"department": doc.department or doc.requested_by_dept,
			"status": "Open",
			"job_requisition": doc.name,
			"planned_vacancies": doc.no_of_positions,
			"vacancies": doc.no_of_positions,
			"description": doc.description,
			"employment_type": getattr(doc, "employment_type", None),
		}
	)
	opening.insert(ignore_permissions=True)
	frappe.msgprint(
		_("Created Job Opening {0} from approved requisition.").format(
			get_link_to_form("Job Opening", opening.name)
		)
	)


def _was_just_approved(doc):
	"""True iff workflow_state transitioned to 'Approved' on this save."""
	if not getattr(doc, "workflow_state", None):
		return False
	if doc.workflow_state != APPROVED_STATE:
		return False
	before = doc.get_doc_before_save()
	# Fresh insert into Approved (unusual but possible) counts as just-approved.
	if not before:
		return True
	return getattr(before, "workflow_state", None) != APPROVED_STATE


def setup_job_requisition_workflow():
	"""Idempotent setup — creates the Workflow, its States and Actions if missing.
	Safe to call from after_install AND from a patch."""
	# 1. Ensure Workflow States exist
	state_specs = [
		("Draft", "Primary"),
		("Pending HR Review", "Warning"),
		("Pending Final Approval", "Warning"),
		("Approved", "Success"),
		("Cancelled", "Danger"),
		("Rejected", "Danger"),
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

	# 2. Ensure Workflow Actions exist
	action_specs = ["Submit for Review", "Forward to HR Manager", "Approve", "Reject", "Cancel"]
	for action in action_specs:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc(
				{
					"doctype": "Workflow Action Master",
					"workflow_action_name": action,
				}
			).insert(ignore_permissions=True)

	# 3. Create the Workflow if missing
	if frappe.db.exists("Workflow", JOB_REQUISITION_WORKFLOW):
		return

	workflow = frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": JOB_REQUISITION_WORKFLOW,
			"document_type": "Job Requisition",
			"workflow_state_field": "workflow_state",
			"is_active": 1,
			"send_email_alert": 1,
			"override_status": 0,
			"states": [
				{"state": "Draft", "doc_status": "0", "allow_edit": "Employee"},
				{"state": "Pending HR Review", "doc_status": "0", "allow_edit": "HR User"},
				{"state": "Pending Final Approval", "doc_status": "0", "allow_edit": "HR Manager"},
				{"state": "Approved", "doc_status": "0", "allow_edit": "HR Manager"},
				{"state": "Cancelled", "doc_status": "0", "allow_edit": "HR Manager"},
				{"state": "Rejected", "doc_status": "0", "allow_edit": "HR Manager"},
			],
			"transitions": [
				{
					"state": "Draft",
					"action": "Submit for Review",
					"next_state": "Pending HR Review",
					"allowed": "Employee",
					"allow_self_approval": 1,
				},
				{
					"state": "Pending HR Review",
					"action": "Forward to HR Manager",
					"next_state": "Pending Final Approval",
					"allowed": "HR User",
					"allow_self_approval": 0,
				},
				{
					"state": "Pending HR Review",
					"action": "Reject",
					"next_state": "Rejected",
					"allowed": "HR User",
					"allow_self_approval": 0,
				},
				{
					"state": "Pending Final Approval",
					"action": "Approve",
					"next_state": "Approved",
					"allowed": "HR Manager",
					"allow_self_approval": 0,
				},
				{
					"state": "Pending Final Approval",
					"action": "Reject",
					"next_state": "Rejected",
					"allowed": "HR Manager",
					"allow_self_approval": 0,
				},
				{
					"state": "Approved",
					"action": "Cancel",
					"next_state": "Cancelled",
					"allowed": "HR Manager",
					"allow_self_approval": 1,
				},
				{
					"state": "Draft",
					"action": "Cancel",
					"next_state": "Cancelled",
					"allowed": "HR Manager",
					"allow_self_approval": 1,
				},
			],
		}
	)
	workflow.insert(ignore_permissions=True)
