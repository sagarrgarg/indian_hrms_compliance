# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Org graph for the 3D org chart.

Returns the reporting hierarchy (reports_to) with each node's level (depth),
sibling breadth index, and the KRA / Task (SOP) items that hang off it on the
Z axis. HR-only; company-scoped to the caller's company by default.
"""

import frappe

COCKPIT_ROLES = ("HR Manager", "HR User", "System Manager")


@frappe.whitelist()
def get_org_graph(company: str | None = None) -> dict:
	frappe.only_for(COCKPIT_ROLES)

	if not company:
		user = frappe.session.user
		if user != "Administrator":
			company = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "company")

	emp_filters = {"status": "Active"}
	if company:
		emp_filters["company"] = company

	employees = frappe.get_all(
		"Employee",
		filters=emp_filters,
		fields=["name", "employee_name", "designation", "department", "reports_to", "image"],
	)
	emp_set = {e.name for e in employees}

	# Open/overdue task counts per employee (Z-axis health).
	today = frappe.utils.nowdate()
	open_tasks = {}
	overdue_tasks = {}
	kra_titles = {}
	for e in employees:
		open_tasks[e.name] = frappe.db.count(
			"Goal", {"goal_type": "Task Instance", "employee": e.name, "status": ("in", ("Pending", "In Progress"))}
		)
		overdue_tasks[e.name] = frappe.db.count(
			"Goal",
			{"goal_type": "Task Instance", "employee": e.name, "status": ("in", ("Pending", "In Progress")), "due_date": ("<", today)},
		)

	# KRAs / HRMS Tasks (SOPs) that apply to each employee, via designation or all-active.
	tasks = frappe.get_all(
		"HRMS Task",
		filters={"status": "Active"} | ({"company": company} if company else {}),
		fields=["name", "task_name", "kra", "task_kind", "assigned_to_designation", "applicable_to_all_active"],
	)

	def tasks_for(emp):
		out = []
		for t in tasks:
			if t.applicable_to_all_active or (t.assigned_to_designation and t.assigned_to_designation == emp.designation):
				out.append({"name": t.name, "label": t.task_name, "kra": t.kra, "kind": t.task_kind})
		return out

	# Compute level (depth) by walking reports_to within the set.
	parent_of = {e.name: (e.reports_to if e.reports_to in emp_set else None) for e in employees}

	def depth(name, _seen=None):
		_seen = _seen or set()
		p = parent_of.get(name)
		if not p or p in _seen:
			return 0
		_seen.add(name)
		return 1 + depth(p, _seen)

	nodes = []
	for e in employees:
		z_items = tasks_for(e)
		nodes.append(
			{
				"id": e.name,
				"label": e.employee_name or e.name,
				"designation": e.designation,
				"department": e.department,
				"parent": parent_of.get(e.name),
				"level": depth(e.name),
				"image": e.image,
				"open_tasks": open_tasks.get(e.name, 0),
				"overdue_tasks": overdue_tasks.get(e.name, 0),
				"kras": sorted({t["kra"] for t in z_items if t["kra"]}),
				"sops": z_items,  # KRA/SOP/KPI items on the Z axis
			}
		)

	# Sibling breadth index per (parent, level) for X positioning.
	by_parent = {}
	for n in sorted(nodes, key=lambda x: x["label"]):
		by_parent.setdefault(n["parent"], []).append(n)
	for _parent, sibs in by_parent.items():
		for i, n in enumerate(sibs):
			n["sibling_index"] = i
			n["sibling_count"] = len(sibs)

	return {"company": company, "nodes": nodes, "count": len(nodes)}
