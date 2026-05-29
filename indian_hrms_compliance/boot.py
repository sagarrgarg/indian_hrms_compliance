# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.utils import getdate, today


def extend_bootinfo(bootinfo):
	"""Inject indian_hrms_compliance-specific session context into Frappe bootinfo.

	Today: overdue policy acknowledgements for the current user. Used by the
	Desk-side overdue policy popup. Single query, capped at 50 records.
	"""
	if not bootinfo.get("user") or bootinfo["user"].get("name") in ("Guest", "Administrator"):
		bootinfo.setdefault("indian_hrms_compliance", {})
		bootinfo["indian_hrms_compliance"]["overdue_policy_acks"] = []
		bootinfo["indian_hrms_compliance"]["overdue_task_instances"] = []
		return

	user = bootinfo["user"]["name"]
	employees = frappe.get_all(
		"Employee",
		filters={"user_id": user, "status": "Active"},
		pluck="name",
	)
	if not employees:
		bootinfo.setdefault("indian_hrms_compliance", {})
		bootinfo["indian_hrms_compliance"]["overdue_policy_acks"] = []
		bootinfo["indian_hrms_compliance"]["overdue_task_instances"] = []
		return

	today_d = getdate(today())
	overdue = frappe.get_all(
		"Employee Policy Acknowledgement",
		filters={
			"employee": ("in", employees),
			"status": "Pending",
			"due_date": ("<", today_d),
		},
		fields=[
			"name",
			"employee",
			"employee_name",
			"company",
			"policy",
			"policy_name_fetched",
			"policy_version",
			"policy_category",
			"due_date",
			"signed_text",
		],
		order_by="due_date asc",
		limit=50,
	)

	bootinfo.setdefault("indian_hrms_compliance", {})
	bootinfo["indian_hrms_compliance"]["overdue_policy_acks"] = overdue

	# Also: overdue Task Instances (Goals with goal_type='Task Instance').
	overdue_tasks = frappe.get_all(
		"Goal",
		filters={
			"goal_type": "Task Instance",
			"employee": ("in", employees),
			"status": ("in", ["Pending", "In Progress"]),
			"due_date": ("<", today_d),
		},
		fields=[
			"name",
			"goal_name",
			"task_template",
			"kra",
			"period_label",
			"due_date",
			"company",
		],
		order_by="due_date asc",
		limit=50,
	)
	bootinfo["indian_hrms_compliance"]["overdue_task_instances"] = overdue_tasks
