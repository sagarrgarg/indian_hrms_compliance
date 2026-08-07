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
	settings = _ot_settings()
	return get_columns(), _compute(_attendance_rows(filters), settings)


def get_columns():
	return [
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 120},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
		{"label": _("Department"), "fieldname": "department", "fieldtype": "Data", "width": 150},
		{"label": _("Days"), "fieldname": "days", "fieldtype": "Int", "width": 70},
		{"label": _("Net Hours"), "fieldname": "net_hours", "fieldtype": "Float", "width": 100},
		{"label": _("Daily-basis OT"), "fieldname": "daily_ot", "fieldtype": "Float", "width": 120},
		{"label": _("Weekly-basis OT"), "fieldname": "weekly_ot", "fieldtype": "Float", "width": 130},
		{"label": _("OT Hours (payable)"), "fieldname": "ot_hours", "fieldtype": "Float", "width": 140},
	]


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


def _compute(rows, s):
	per_emp = {}
	for r in rows:
		e = per_emp.setdefault(
			r.employee,
			{"name": r.employee_name, "dept": r.department, "days": 0, "net": 0.0, "weeks": defaultdict(lambda: {"net": 0.0, "dot": 0.0})},
		)
		net = max(0.0, flt(r.working_hours) - s.lunch_hours)
		e["days"] += 1
		e["net"] += net
		wk = getdate(r.attendance_date).isocalendar()[:2]  # (iso year, iso week)
		e["weeks"][wk]["net"] += net
		e["weeks"][wk]["dot"] += max(0.0, net - s.daily)

	data = []
	for emp, e in per_emp.items():
		daily_ot = weekly_ot = ot = 0.0
		for wk in e["weeks"].values():
			w_ot = max(0.0, wk["net"] - s.weekly)
			daily_ot += wk["dot"]
			weekly_ot += w_ot
			ot += max(wk["dot"], w_ot)  # greater of the two — never both
		data.append(
			{
				"employee": emp,
				"employee_name": e["name"],
				"department": e["dept"],
				"days": e["days"],
				"net_hours": round(e["net"], 2),
				"daily_ot": round(daily_ot, 2),
				"weekly_ot": round(weekly_ot, 2),
				"ot_hours": round(ot, 2),
			}
		)
	data.sort(key=lambda x: -x["ot_hours"])
	return data
