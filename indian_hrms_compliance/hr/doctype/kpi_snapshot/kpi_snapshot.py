# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""KPI Snapshot — a weekly cache of KPI rollups per employee × task (Phase 4).

So a measure is visible mid-quarter, not only when an Appraisal is saved. The
scheduler recomputes the CURRENT period's snapshot each week (idempotent per
employee::task::period via dedup_key) and the PWA scorecard reads the latest.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime, today


class KPISnapshot(Document):
	pass


def _dedup_key(employee: str, task_template: str, period_label: str) -> str:
	return f"{employee}::{task_template}::{period_label}"


def _upsert_snapshot(employee: str, employee_name: str, period_label: str, kpi: dict) -> None:
	key = _dedup_key(employee, kpi["task_template"], period_label)
	# Match by dedup_key first; fall back to the natural key so a stale dedup_key
	# (after an Employee / HRMS Task rename) doesn't create a duplicate row.
	name = frappe.db.get_value("KPI Snapshot", {"dedup_key": key}) or frappe.db.get_value(
		"KPI Snapshot",
		{"employee": employee, "task_template": kpi["task_template"], "period_label": period_label},
	)
	fields = {
		"employee": employee,
		"employee_name": employee_name,
		"task_template": kpi["task_template"],
		"task_name": kpi["task_name"],
		"kra": kpi.get("kra"),
		"company": kpi.get("company"),
		"period_label": period_label,
		"snapshot_date": today(),
		"target_value": kpi["target_value"],
		"actual_value": kpi["actual_value"],
		"achievement_pct": kpi["achievement_pct"],
		"measurement_unit": kpi.get("measurement_unit"),
		"rollup_method": kpi.get("rollup_method"),
	}
	if name:
		# Refresh the dedup_key too, so a rename self-heals the stored key.
		frappe.db.set_value("KPI Snapshot", name, {"dedup_key": key, **fields}, update_modified=False)
	else:
		doc = frappe.get_doc({"doctype": "KPI Snapshot", "dedup_key": key, **fields})
		doc.insert(ignore_permissions=True)


def snapshot_kpis() -> dict:
	"""Scheduler (weekly): refresh the current period's KPI snapshot for every
	active KPI-measuring task × assigned employee. Self-contained + idempotent.
	"""
	if not frappe.db.table_exists("KPI Snapshot"):
		return {"skipped": "doctype missing"}
	from indian_hrms_compliance.hr.doctype.hrms_task.hrms_task import (
		compute_period_for_today,
		resolve_assigned_employees,
	)
	from indian_hrms_compliance.hr.kpi import compute_task_kpi_bulk

	# KPI-measuring tasks: a target to measure against.
	tasks = frappe.get_all(
		"HRMS Task",
		filters={"status": "Active", "target_value": (">", 0)},
		fields=["name", "frequency", "company", "effective_from", "effective_to"],
	)
	written = 0
	for t in tasks:
		try:
			start, end, label = _window_for(t)
			employees = resolve_assigned_employees(frappe.get_doc("HRMS Task", t.name))
			if not employees:
				continue
			# One SQL for all employees, one name preload — not N per employee.
			kpis = compute_task_kpi_bulk(t.name, employees, start, end)
			if not kpis:
				continue
			names = {
				e.name: e.employee_name
				for e in frappe.get_all(
					"Employee", filters={"name": ("in", list(kpis))}, fields=["name", "employee_name"]
				)
			}
			for emp, kpi in kpis.items():
				_upsert_snapshot(emp, names.get(emp), label, kpi)
				written += 1
		except Exception:
			frappe.log_error(title=f"KPI snapshot failed for task {t.name}")
	frappe.db.commit()
	return {"snapshots": written, "tasks": len(tasks)}


def _window_for(task) -> tuple:
	"""The measurement window + label for a task's current snapshot.

	Cadenced tasks use their current period; a One-time task uses its own
	effective span; anything else (On-demand) falls back to a rolling 12 months.
	"""
	from indian_hrms_compliance.hr.doctype.hrms_task.hrms_task import compute_period_for_today
	from frappe.utils import add_days

	period = compute_period_for_today(task.frequency)
	if period:
		return period["start"], period["end"], period["label"]
	if task.frequency == "One-time" and task.get("effective_from"):
		start = getdate(task.effective_from)
		end = getdate(task.effective_to) if task.get("effective_to") else getdate(today())
		return start, end, _("One-time")
	end = getdate(today())
	return add_days(end, -365), end, _("Last 12 months")
