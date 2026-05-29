# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	"""Phase 3 Item B: extend Goal so it can serve as a Task Instance
	(per-Employee per-period occurrence of an HRMS Task) alongside
	traditional SMART goals. All existing Goals are backfilled to
	goal_type='SMART'."""

	create_custom_fields(
		{
			"Goal": [
				{
					"fieldname": "goal_type",
					"fieldtype": "Select",
					"label": "Goal Type",
					"options": "SMART\nTask Instance",
					"default": "SMART",
					"insert_after": "status",
					"in_list_view": 1,
					"in_standard_filter": 1,
				},
				{
					"fieldname": "task_template",
					"fieldtype": "Link",
					"label": "Task Template",
					"options": "HRMS Task",
					"insert_after": "goal_type",
					"depends_on": "eval:doc.goal_type=='Task Instance'",
					"in_standard_filter": 1,
				},
				{
					"fieldname": "period_label",
					"fieldtype": "Data",
					"label": "Period Label",
					"insert_after": "task_template",
					"depends_on": "eval:doc.goal_type=='Task Instance'",
				},
				{
					"fieldname": "due_date",
					"fieldtype": "Date",
					"label": "Due Date",
					"insert_after": "period_label",
					"depends_on": "eval:doc.goal_type=='Task Instance'",
				},
				{
					"fieldname": "completion_type",
					"fieldtype": "Data",
					"label": "Completion Type",
					"fetch_from": "task_template.completion_type",
					"read_only": 1,
					"insert_after": "due_date",
					"depends_on": "eval:doc.goal_type=='Task Instance'",
				},
				{
					"fieldname": "task_attachment",
					"fieldtype": "Attach",
					"label": "Attachment",
					"insert_after": "completion_type",
					"depends_on": "eval:doc.goal_type=='Task Instance'",
				},
				{
					"fieldname": "numeric_value",
					"fieldtype": "Float",
					"label": "Numeric Value (for KPI)",
					"insert_after": "task_attachment",
					"depends_on": "eval:doc.goal_type=='Task Instance' && doc.completion_type=='Numeric Entry'",
				},
				{
					"fieldname": "task_notes",
					"fieldtype": "Small Text",
					"label": "Notes",
					"insert_after": "numeric_value",
					"depends_on": "eval:doc.goal_type=='Task Instance'",
				},
				{
					"fieldname": "approver_user",
					"fieldtype": "Link",
					"label": "Approver",
					"options": "User",
					"insert_after": "task_notes",
					"depends_on": "eval:doc.goal_type=='Task Instance'",
				},
				{
					"fieldname": "submitted_at",
					"fieldtype": "Datetime",
					"label": "Submitted At",
					"read_only": 1,
					"insert_after": "approver_user",
					"depends_on": "eval:doc.goal_type=='Task Instance'",
				},
				{
					"fieldname": "submitted_by",
					"fieldtype": "Link",
					"label": "Submitted By",
					"options": "User",
					"read_only": 1,
					"insert_after": "submitted_at",
					"depends_on": "eval:doc.goal_type=='Task Instance'",
				},
				{
					"fieldname": "approved_at",
					"fieldtype": "Datetime",
					"label": "Approved At",
					"read_only": 1,
					"insert_after": "submitted_by",
					"depends_on": "eval:doc.goal_type=='Task Instance'",
				},
				{
					"fieldname": "approved_by",
					"fieldtype": "Link",
					"label": "Approved By",
					"options": "User",
					"read_only": 1,
					"insert_after": "approved_at",
					"depends_on": "eval:doc.goal_type=='Task Instance'",
				},
				{
					"fieldname": "approval_notes",
					"fieldtype": "Small Text",
					"label": "Approval Notes",
					"insert_after": "approved_by",
					"depends_on": "eval:doc.goal_type=='Task Instance'",
				},
				{
					"fieldname": "last_reminder_sent_on",
					"fieldtype": "Date",
					"label": "Last Overdue Reminder Sent On",
					"read_only": 1,
					"insert_after": "approval_notes",
					"depends_on": "eval:doc.goal_type=='Task Instance'",
				},
			]
		},
		ignore_validate=True,
	)

	# Backfill: every pre-existing Goal is a SMART goal.
	frappe.db.sql(
		"""UPDATE `tabGoal`
		   SET goal_type = 'SMART'
		   WHERE goal_type IS NULL OR goal_type = ''"""
	)
