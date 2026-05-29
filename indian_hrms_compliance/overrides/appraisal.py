# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import escape_html


def populate_kra_performance(doc, method=None):
	"""doc_event Appraisal.validate: compute and inject the KRA Performance
	HTML from this Employee's Task Instances within the Appraisal Cycle
	period.

	Aggregates Goal rows (goal_type='Task Instance') grouped by KRA.
	Computes Total / Completed / Overdue / Compliance % per KRA, plus a
	KPI achievement % per Task that has a target_value.

	Output is a single read-only HTML field — the Appraisal scoring
	logic remains HR's call; this just surfaces the underlying evidence.

	Gated by HR Settings.appraisal_auto_populate_kra_performance: when off,
	the field is left untouched so HR can manage it manually for special
	appraisal cycles."""
	if not int(
		frappe.db.get_single_value("HR Settings", "appraisal_auto_populate_kra_performance") or 0
	):
		return
	if not (doc.employee and doc.appraisal_cycle):
		doc.kra_performance_html = (
			"<p style='color:#888'>Set Employee and Appraisal Cycle to see KRA Performance.</p>"
		)
		return

	cycle = frappe.db.get_value(
		"Appraisal Cycle", doc.appraisal_cycle, ["start_date", "end_date"], as_dict=True
	)
	if not (cycle and cycle.start_date and cycle.end_date):
		doc.kra_performance_html = (
			"<p style='color:#888'>Appraisal Cycle is missing start/end dates.</p>"
		)
		return

	rows = frappe.db.sql(
		"""
		SELECT g.kra, g.task_template, g.status, g.due_date, g.numeric_value,
		       t.task_name, t.target_value, t.kpi_rollup_method, t.completion_type
		FROM `tabGoal` g
		LEFT JOIN `tabHRMS Task` t ON t.name = g.task_template
		WHERE g.goal_type = 'Task Instance'
		  AND g.employee = %s
		  AND g.due_date BETWEEN %s AND %s
		""",
		(doc.employee, cycle.start_date, cycle.end_date),
		as_dict=True,
	)

	if not rows:
		doc.kra_performance_html = (
			"<p style='color:#888'>No Task Instances found for this Employee in the cycle period "
			f"({cycle.start_date} to {cycle.end_date}).</p>"
		)
		return

	# Group by KRA → stats; group by (KRA, Task) → KPI rollup
	kra_stats = defaultdict(lambda: {"total": 0, "completed": 0, "overdue": 0})
	task_values = defaultdict(list)  # (kra, task_template) -> list of (numeric_value, rollup_method, target_value, task_name, completion_type)

	from frappe.utils import getdate, today

	today_d = getdate(today())
	for r in rows:
		s = kra_stats[r.kra or "(unspecified KRA)"]
		s["total"] += 1
		if r.status == "Completed":
			s["completed"] += 1
		elif r.status in ("Pending", "In Progress") and r.due_date and getdate(r.due_date) < today_d:
			s["overdue"] += 1

		if r.completion_type == "Numeric Entry" and r.numeric_value is not None:
			task_values[(r.kra, r.task_template)].append(
				(r.numeric_value, r.kpi_rollup_method or "Sum", r.target_value, r.task_name)
			)

	# Render
	out = []
	out.append(
		f"<p style='font-size:12px;color:#777;margin-bottom:8px'>"
		f"Cycle period: {cycle.start_date} → {cycle.end_date}. "
		f"Auto-computed from {len(rows)} Task Instance(s).</p>"
	)
	out.append("<h4 style='margin-top:8px'>KRA Compliance</h4>")
	out.append(
		"<table border='1' cellpadding='6' cellspacing='0' "
		"style='border-collapse:collapse;font-size:13px;width:100%'>"
		"<thead><tr style='background:#f5f5f5'>"
		"<th>KRA</th><th>Total</th><th>Completed</th><th>Overdue</th>"
		"<th>Compliance %</th></tr></thead><tbody>"
	)
	for kra, s in sorted(kra_stats.items()):
		pct = (s["completed"] / s["total"] * 100.0) if s["total"] else 0.0
		color = "#27ae60" if pct >= 90 else ("#e67e22" if pct >= 70 else "#c0392b")
		out.append(
			f"<tr><td>{escape_html(kra)}</td>"
			f"<td>{s['total']}</td>"
			f"<td>{s['completed']}</td>"
			f"<td style='color:#c0392b'>{s['overdue']}</td>"
			f"<td style='color:{color};font-weight:600'>{pct:.1f}%</td></tr>"
		)
	out.append("</tbody></table>")

	# KPI rollup per Task
	if task_values:
		out.append("<h4 style='margin-top:16px'>KPI Achievement (per Task)</h4>")
		out.append(
			"<table border='1' cellpadding='6' cellspacing='0' "
			"style='border-collapse:collapse;font-size:13px;width:100%'>"
			"<thead><tr style='background:#f5f5f5'>"
			"<th>KRA</th><th>Task</th><th>Rollup</th><th>Aggregate</th>"
			"<th>Target</th><th>Achievement %</th></tr></thead><tbody>"
		)
		for (kra, _task_name_unused), entries in sorted(task_values.items()):
			values = [e[0] for e in entries]
			method = entries[0][1]
			target = entries[0][2]
			task_name = entries[0][3]
			agg = _aggregate(values, method)
			achievement_pct = (
				(agg / target * 100.0) if (target and target != 0) else 0.0
			)
			ach_color = (
				"#27ae60"
				if achievement_pct >= 90
				else ("#e67e22" if achievement_pct >= 70 else "#c0392b")
			)
			out.append(
				f"<tr><td>{escape_html(kra)}</td>"
				f"<td>{escape_html(task_name or '')}</td>"
				f"<td>{escape_html(method)}</td>"
				f"<td>{agg:.2f}</td>"
				f"<td>{(target if target is not None else '—')}</td>"
				f"<td style='color:{ach_color};font-weight:600'>"
				f"{achievement_pct:.1f}%</td></tr>"
			)
		out.append("</tbody></table>")

	doc.kra_performance_html = "".join(out)


def _aggregate(values, method):
	if not values:
		return 0.0
	if method == "Sum":
		return sum(values)
	if method == "Average":
		return sum(values) / len(values)
	if method == "Max":
		return max(values)
	if method == "Min":
		return min(values)
	if method == "Latest":
		return values[-1]
	return sum(values)
