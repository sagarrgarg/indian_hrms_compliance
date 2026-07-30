# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe

_HR_ROLES = {"HR Manager", "HR User", "System Manager"}


def _employees_of(user):
	return frappe.get_all("Employee", filters={"user_id": user, "status": "Active"}, pluck="name")


def get_permission_query_conditions(user):
	"""Goal permission scoping.

	For Task Instances (goal_type='Task Instance'): non-HR users see ONLY
	their own Task Instances. SMART goals follow Goal's standard Frappe
	permissions (unchanged)."""
	if not user:
		user = frappe.session.user
	if _HR_ROLES & set(frappe.get_roles(user)):
		return ""
	employees = _employees_of(user)
	if not employees:
		return "`tabGoal`.goal_type != 'Task Instance'"
	emp_list = "', '".join(employees)
	return (
		f"(`tabGoal`.goal_type != 'Task Instance' "
		f"OR `tabGoal`.employee in ('{emp_list}'))"
	)


def has_permission(doc, ptype=None, user=None):
	"""Row-level gate for Goal — the teeth `get_permission_query_conditions` lacks.

	Query conditions only scope list/report reads; they are never consulted by
	`Document.save()`. Without this, the Employee role's blanket write perm let
	ANY employee load and re-save ANY Task Instance (another person's included) —
	the hole that made the whole approval cycle bypassable via Goal's own
	whitelisted `update_status` / `update_progress`.

	Rule, matching the query conditions exactly: a non-HR user may only touch a
	Task Instance that is their OWN. SMART goals and every other goal_type keep
	Frappe's standard role behaviour (return True → defer to the role perm).
	The document-level governance guard in the controller still enforces WHAT may
	change on an instance you legitimately own; this decides WHOSE you may touch.
	"""
	user = user or frappe.session.user
	if getattr(doc, "goal_type", None) != "Task Instance":
		return True
	if _HR_ROLES & set(frappe.get_roles(user)):
		return True
	return (doc.get("employee") or None) in _employees_of(user)
