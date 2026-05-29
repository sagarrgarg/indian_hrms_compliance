# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.utils import add_days, getdate, today


def execute(filters=None):
	filters = filters or {}
	columns = _get_columns()
	data = _get_data(filters)
	return columns, data


def _get_columns():
	return [
		{
			"label": _("Employee"),
			"fieldname": "employee",
			"fieldtype": "Link",
			"options": "Employee",
			"width": 130,
		},
		{
			"label": _("Employee Name"),
			"fieldname": "employee_name",
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"label": _("Company"),
			"fieldname": "company",
			"fieldtype": "Link",
			"options": "Company",
			"width": 180,
		},
		{
			"label": _("KRA"),
			"fieldname": "kra",
			"fieldtype": "Link",
			"options": "KRA",
			"width": 130,
		},
		{"label": _("Total"), "fieldname": "total", "fieldtype": "Int", "width": 80},
		{"label": _("Completed"), "fieldname": "completed", "fieldtype": "Int", "width": 100},
		{"label": _("Pending"), "fieldname": "pending", "fieldtype": "Int", "width": 100},
		{"label": _("Overdue"), "fieldname": "overdue", "fieldtype": "Int", "width": 100},
		{
			"label": _("Compliance %"),
			"fieldname": "compliance_pct",
			"fieldtype": "Percent",
			"width": 130,
		},
	]


def _get_data(filters):
	from_date = filters.get("from_date") or add_days(getdate(today()), -30)
	to_date = filters.get("to_date") or getdate(today())

	# Thresholds drive the colour formatter in task_compliance.js — surface them
	# per-row so the JS doesn't need its own frappe.call.
	warn_pct = float(
		frappe.db.get_single_value("HR Settings", "task_compliance_warning_threshold_pct") or 80
	)
	crit_pct = float(
		frappe.db.get_single_value("HR Settings", "task_compliance_critical_threshold_pct") or 50
	)

	conditions = ["goal_type = 'Task Instance'"]
	params = {"from_date": from_date, "to_date": to_date}
	conditions.append("(due_date BETWEEN %(from_date)s AND %(to_date)s)")

	for f, col in (("company", "company"), ("kra", "kra"), ("employee", "employee")):
		if filters.get(f):
			conditions.append(f"{col} = %({f})s")
			params[f] = filters[f]

	where_sql = " AND ".join(conditions)
	today_d = getdate(today())
	params["today_d"] = today_d

	rows = frappe.db.sql(
		f"""
		SELECT
			employee,
			employee_name,
			company,
			kra,
			COUNT(*) AS total,
			SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) AS completed,
			SUM(CASE WHEN status IN ('Pending', 'In Progress') AND
				(due_date IS NULL OR due_date >= %(today_d)s) THEN 1 ELSE 0 END) AS pending,
			SUM(CASE WHEN status IN ('Pending', 'In Progress') AND
				due_date IS NOT NULL AND due_date < %(today_d)s THEN 1 ELSE 0 END) AS overdue
		FROM `tabGoal`
		WHERE {where_sql}
		GROUP BY employee, kra
		ORDER BY employee, kra
		""",
		params,
		as_dict=True,
	)

	for r in rows:
		r["compliance_pct"] = (
			(r["completed"] / r["total"] * 100.0) if r["total"] else 0.0
		)
		r["_warn_pct"] = warn_pct
		r["_crit_pct"] = crit_pct

	return rows
