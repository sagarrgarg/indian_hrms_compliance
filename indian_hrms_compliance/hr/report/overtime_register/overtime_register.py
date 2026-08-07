# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Overtime Register.

Per-employee overtime for a period, computed from Attendance working hours and the
Overtime settings in HR Settings:

    net hours/day  = Attendance.working_hours - lunch/break minutes
    daily OT       = max(0, net_day - daily threshold)      (statutory 9h)
    weekly OT      = max(0, weekly_net - weekly threshold)  (statutory 48h)
    OT for a week  = GREATER of the day-basis and week-basis excess (no double count)
    OT (payable)   = sum of weekly OT across the period

Hours only for now — valuing OT (x2 on the Basic+DA hourly rate) comes when OT is
wired into payroll. Relies on Attendance.working_hours being populated (from
check-ins); days with no working_hours contribute 0.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.get("company"):
		frappe.throw(_("Please select a Company."))
	weekly = bool(filters.get("weekly_breakdown"))
	return get_columns(weekly), _compute(_attendance_rows(filters), _ot_settings(), weekly)


def get_columns(weekly=False):
	cols = [
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 120},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 170},
		{"label": _("Department"), "fieldname": "department", "fieldtype": "Data", "width": 140},
	]
	if weekly:
		cols.append({"label": _("Week Starting"), "fieldname": "week", "fieldtype": "Date", "width": 110})
	cols += [
		{"label": _("Days"), "fieldname": "days", "fieldtype": "Int", "width": 60},
		{"label": _("Net Hours"), "fieldname": "net_hours", "fieldtype": "Float", "width": 95},
		{"label": _("Permitted Hours"), "fieldname": "permitted_hours", "fieldtype": "Float", "width": 120},
		{"label": _("Daily-basis OT"), "fieldname": "daily_ot", "fieldtype": "Float", "width": 110},
		{"label": _("Weekly-basis OT"), "fieldname": "weekly_ot", "fieldtype": "Float", "width": 120},
		{"label": _("OT Hours (payable)"), "fieldname": "ot_hours", "fieldtype": "Float", "width": 130},
	]
	return cols


def _ot_settings():
	meta = frappe.get_meta("HR Settings")

	def g(fieldname, default):
		if meta.has_field(fieldname):
			val = frappe.db.get_single_value("HR Settings", fieldname)
			return flt(val) if val not in (None, "") else default
		return default

	return frappe._dict(
		lunch_hours=g("ot_lunch_break_minutes", 60) / 60.0,
		daily=g("ot_daily_threshold_hours", 9) or 9,
		weekly=g("ot_weekly_threshold_hours", 48) or 48,
		multiplier=g("ot_rate_multiplier", 2) or 2,
	)


def _attendance_rows(filters):
	conds = [
		["docstatus", "<", 2],
		["company", "=", filters.company],
		["status", "in", ["Present", "Half Day", "Work From Home"]],
	]
	if filters.get("from_date"):
		conds.append(["attendance_date", ">=", filters.from_date])
	if filters.get("to_date"):
		conds.append(["attendance_date", "<=", filters.to_date])
	if filters.get("employee"):
		conds.append(["employee", "=", filters.employee])
	if filters.get("department"):
		conds.append(["department", "=", filters.department])
	return frappe.get_all(
		"Attendance",
		filters=conds,
		fields=["employee", "employee_name", "department", "attendance_date", "working_hours"],
		order_by="employee asc, attendance_date asc",
	)


def _compute(rows, s, weekly=False):
	from datetime import date

	# Aggregate net hours + day-basis OT per (employee, iso-week).
	emp_meta = {}
	wk_data = defaultdict(lambda: {"net": 0.0, "dot": 0.0, "days": 0})
	for r in rows:
		emp_meta[r.employee] = (r.employee_name, r.department)
		net = max(0.0, flt(r.working_hours) - s.lunch_hours)
		iso = getdate(r.attendance_date).isocalendar()
		wk = (iso[0], iso[1])
		d = wk_data[(r.employee, wk)]
		d["net"] += net
		d["dot"] += max(0.0, net - s.daily)
		d["days"] += 1

	def week_split(d):
		"""(ot payable, day-basis ot, week-basis ot) for one employee-week."""
		wot = max(0.0, d["net"] - s.weekly)
		return max(d["dot"], wot), d["dot"], wot

	if weekly:
		data = []
		for (emp, wk), d in sorted(wk_data.items(), key=lambda kv: (kv[0][0], kv[0][1])):
			ot, dot, wot = week_split(d)
			name, dept = emp_meta[emp]
			data.append(
				{
					"employee": emp,
					"employee_name": name,
					"department": dept,
					"week": date.fromisocalendar(wk[0], wk[1], 1),  # Monday of the ISO week
					"days": d["days"],
					"net_hours": round(d["net"], 2),
					"permitted_hours": round(d["net"] - ot, 2),
					"daily_ot": round(dot, 2),
					"weekly_ot": round(wot, 2),
					"ot_hours": round(ot, 2),
				}
			)
		return data

	# Employee summary across the period.
	agg = defaultdict(lambda: {"days": 0, "net": 0.0, "dot": 0.0, "wot": 0.0, "ot": 0.0})
	for (emp, wk), d in wk_data.items():
		ot, dot, wot = week_split(d)
		a = agg[emp]
		a["days"] += d["days"]
		a["net"] += d["net"]
		a["dot"] += dot
		a["wot"] += wot
		a["ot"] += ot

	data = []
	for emp, a in agg.items():
		name, dept = emp_meta[emp]
		data.append(
			{
				"employee": emp,
				"employee_name": name,
				"department": dept,
				"days": a["days"],
				"net_hours": round(a["net"], 2),
				"permitted_hours": round(a["net"] - a["ot"], 2),
				"daily_ot": round(a["dot"], 2),
				"weekly_ot": round(a["wot"], 2),
				"ot_hours": round(a["ot"], 2),
			}
		)
	data.sort(key=lambda x: -x["ot_hours"])
	return data
