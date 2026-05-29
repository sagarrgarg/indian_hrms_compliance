# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe


def get_permission_query_conditions(user):
	"""Goal permission scoping.

	For Task Instances (goal_type='Task Instance'): non-HR users see ONLY
	their own Task Instances. SMART goals follow Goal's standard Frappe
	permissions (unchanged)."""
	if not user:
		user = frappe.session.user
	roles = set(frappe.get_roles(user))
	if {"HR Manager", "HR User", "System Manager"} & roles:
		return ""
	employees = frappe.get_all(
		"Employee", filters={"user_id": user, "status": "Active"}, pluck="name"
	)
	if not employees:
		return "`tabGoal`.goal_type != 'Task Instance'"
	emp_list = "', '".join(employees)
	return (
		f"(`tabGoal`.goal_type != 'Task Instance' "
		f"OR `tabGoal`.employee in ('{emp_list}'))"
	)
