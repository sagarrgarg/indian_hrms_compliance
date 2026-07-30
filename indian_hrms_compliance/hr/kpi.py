# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Shared KPI rollup (Phase 4).

The KPI-achievement math used to live only inside the Appraisal auto-feed, so a
measure was visible only when an Appraisal was saved. This is the extracted,
reusable core: the same aggregation the Appraisal uses, now also driven weekly
by a scheduler into a KPI Snapshot so numbers are visible mid-quarter.
"""

import frappe
from frappe.utils import flt


def aggregate(values, method: str) -> float:
	"""Roll a period's numeric readings into one figure, per the task's method."""
	if not values:
		return 0.0
	if method == "Average":
		return sum(values) / len(values)
	if method == "Max":
		return max(values)
	if method == "Min":
		return min(values)
	if method == "Latest":
		return values[-1]
	return sum(values)  # Sum (default)


def compute_task_kpi(employee: str, task_template: str, start, end) -> dict | None:
	"""The KPI achievement for one employee × task over a window.

	Reads the employee's Numeric-Entry Task Instances for the template in the
	window, aggregates their numeric_value per the task's rollup method, and
	compares to the target. Returns None for a task with no target (nothing to
	measure) or no readings.
	"""
	tmpl = frappe.db.get_value(
		"HRMS Task",
		task_template,
		["task_name", "kra", "company", "target_value", "kpi_rollup_method", "measurement_unit"],
		as_dict=True,
	)
	if not tmpl or not tmpl.target_value:
		return None

	values = frappe.db.sql(
		"""
		SELECT g.numeric_value
		FROM `tabGoal` g
		WHERE g.goal_type = 'Task Instance'
		  AND g.employee = %s AND g.task_template = %s
		  AND g.completion_type = 'Numeric Entry' AND g.numeric_value IS NOT NULL
		  AND g.due_date BETWEEN %s AND %s
		ORDER BY g.due_date ASC
		""",
		(employee, task_template, start, end),
		as_list=True,
	)
	readings = [flt(v[0]) for v in values]
	return _kpi_from_readings(tmpl, task_template, readings)


def _kpi_from_readings(tmpl, task_template: str, readings: list) -> dict | None:
	if not readings:
		return None
	method = tmpl.kpi_rollup_method or "Sum"
	actual = aggregate(readings, method)
	target = flt(tmpl.target_value)
	achievement = (actual / target * 100.0) if target else 0.0
	return {
		"task_template": task_template,
		"task_name": tmpl.task_name,
		"kra": tmpl.kra,
		"company": tmpl.company,
		"rollup_method": method,
		"measurement_unit": tmpl.measurement_unit,
		"target_value": target,
		"actual_value": actual,
		"achievement_pct": round(achievement, 1),
		"readings": len(readings),
	}


def compute_task_kpi_bulk(task_template: str, employees, start, end) -> dict:
	"""compute_task_kpi for MANY employees in ONE query (weekly scheduler path).

	Returns {employee: kpi_dict} only for employees with readings (and only when
	the task has a target). Avoids the N-queries-per-task fan-out that would grow
	with headcount.
	"""
	employees = [e for e in (employees or []) if e]
	if not employees:
		return {}
	tmpl = frappe.db.get_value(
		"HRMS Task",
		task_template,
		["task_name", "kra", "company", "target_value", "kpi_rollup_method", "measurement_unit"],
		as_dict=True,
	)
	if not tmpl or not tmpl.target_value:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT g.employee, g.numeric_value
		FROM `tabGoal` g
		WHERE g.goal_type = 'Task Instance'
		  AND g.task_template = %s AND g.employee IN %s
		  AND g.completion_type = 'Numeric Entry' AND g.numeric_value IS NOT NULL
		  AND g.due_date BETWEEN %s AND %s
		ORDER BY g.due_date ASC
		""",
		(task_template, tuple(employees), start, end),
		as_dict=True,
	)
	from collections import defaultdict

	per_emp = defaultdict(list)
	for r in rows:
		per_emp[r.employee].append(flt(r.numeric_value))
	out = {}
	for emp, readings in per_emp.items():
		kpi = _kpi_from_readings(tmpl, task_template, readings)
		if kpi:
			out[emp] = kpi
	return out
