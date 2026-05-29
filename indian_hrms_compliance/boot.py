# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.utils import getdate, today


def extend_bootinfo(bootinfo):
	"""Inject indian_hrms_compliance-specific session context into Frappe bootinfo.

	Today: overdue policy acknowledgements + overdue Task Instances for the
	current user. Each popup is independently gated by an HR Settings toggle
	(show_overdue_policy_popup_on_login / show_overdue_task_popup_on_login).
	When a toggle is off, the corresponding list ships back empty — JS popups
	check the length and stay silent.
	"""
	bootinfo.setdefault("indian_hrms_compliance", {})
	bootinfo["indian_hrms_compliance"]["overdue_policy_acks"] = []
	bootinfo["indian_hrms_compliance"]["overdue_task_instances"] = []

	if not bootinfo.get("user") or bootinfo["user"].get("name") in ("Guest", "Administrator"):
		return

	user = bootinfo["user"]["name"]
	employees = frappe.get_all(
		"Employee",
		filters={"user_id": user, "status": "Active"},
		pluck="name",
	)
	if not employees:
		return

	today_d = getdate(today())

	# Cache the two toggles in one round-trip — both are on HR Settings (Single).
	show_policy_popup = int(
		frappe.db.get_single_value("HR Settings", "show_overdue_policy_popup_on_login") or 0
	)
	show_task_popup = int(
		frappe.db.get_single_value("HR Settings", "show_overdue_task_popup_on_login") or 0
	)

	if show_policy_popup:
		bootinfo["indian_hrms_compliance"]["overdue_policy_acks"] = frappe.get_all(
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

	if show_task_popup:
		bootinfo["indian_hrms_compliance"]["overdue_task_instances"] = frappe.get_all(
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
