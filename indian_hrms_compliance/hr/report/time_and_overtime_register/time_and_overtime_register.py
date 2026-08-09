# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Time & Overtime Register.

Per-employee working time for a period, split so nobody is compensated twice.

For each attendance day (Present / Half Day / WFH):
    net hours = Attendance.working_hours - lunch/break minutes

Each day is ONE of:
  * WORKED WEEKLY-OFF / HOLIDAY — the date is in the employee's Holiday List (or a
    comp-off was already raised for it). Working a rest day is compensated by a
    substitute holiday (comp-off), NOT hourly OT — so it feeds "WO/Holiday Worked"
    and contributes nothing to net hours or OT.
  * ORDINARY working day — feeds net hours and OT:
        daily OT  = max(0, net_day - daily threshold)   (statutory 9h)
        weekly OT = max(0, week_net - weekly threshold)  (statutory 48h)
        OT (payable) per week = GREATER of the two (never both).
    Permitted = net - OT.

Comp-off suggestion:
    Comp-Off Given = comp-offs already raised (Compensatory Leave Request)
    Comp-Off Owed  = max(0, WO/Holiday Worked - Comp-Off Given)  <- HR's to-do

Hours only for now — valuing OT (x multiplier on Basic+DA hourly) comes later.
Reads Attendance.working_hours (from check-ins).
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.get("company"):
		frappe.throw(_("Please select a Company."))
	weekly = bool(filters.get("weekly_breakdown"))
	rows = _attendance_rows(filters)
	holidays = _holiday_dates(list({r.employee for r in rows}), filters)
	compoff = _compoff_dates(filters)
	return get_columns(weekly), _compute(rows, _ot_settings(), holidays, compoff, weekly)


def get_columns(weekly=False):
	cols = [
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 120},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 160},
		{"label": _("Department"), "fieldname": "department", "fieldtype": "Data", "width": 130},
	]
	if weekly:
		cols.append({"label": _("Week Starting"), "fieldname": "week", "fieldtype": "Date", "width": 105})
	cols += [
		{"label": _("Days"), "fieldname": "days", "fieldtype": "Int", "width": 55},
		{"label": _("Net Hours"), "fieldname": "net_hours", "fieldtype": "Float", "width": 90},
		{"label": _("Permitted Hours"), "fieldname": "permitted_hours", "fieldtype": "Float", "width": 110},
		{"label": _("Daily-basis OT"), "fieldname": "daily_ot", "fieldtype": "Float", "width": 105},
		{"label": _("Weekly-basis OT"), "fieldname": "weekly_ot", "fieldtype": "Float", "width": 110},
		{"label": _("OT Hours (payable)"), "fieldname": "ot_hours", "fieldtype": "Float", "width": 120},
		{"label": _("WO/Holiday Worked"), "fieldname": "wo_worked", "fieldtype": "Int", "width": 125},
		{"label": _("Comp-Off Given"), "fieldname": "compoff_given", "fieldtype": "Int", "width": 105},
		{"label": _("Comp-Off Owed"), "fieldname": "compoff_owed", "fieldtype": "Int", "width": 105},
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


def _holiday_dates(employees, filters):
	"""{employee: set('YYYY-MM-DD') holidays / weekly-offs in the period}, from each
	employee's Holiday List (falling back to the Company default)."""
	if not employees:
		return {}
	emp_hl, company_default = {}, {}
	for e in employees:
		rec = frappe.db.get_value("Employee", e, ["holiday_list", "company"], as_dict=True) or {}
		hl = rec.get("holiday_list")
		if not hl and rec.get("company"):
			if rec.company not in company_default:
				company_default[rec.company] = frappe.db.get_value(
					"Company", rec.company, "default_holiday_list"
				)
			hl = company_default[rec.company]
		emp_hl[e] = hl

	lists = list({v for v in emp_hl.values() if v})
	by_list = defaultdict(set)
	if lists:
		conds = [["parent", "in", lists], ["parenttype", "=", "Holiday List"]]
		if filters.get("from_date"):
			conds.append(["holiday_date", ">=", filters.from_date])
		if filters.get("to_date"):
			conds.append(["holiday_date", "<=", filters.to_date])
		for h in frappe.get_all("Holiday", filters=conds, fields=["parent", "holiday_date"]):
			by_list[h.parent].add(str(h.holiday_date))
	return {e: by_list.get(hl, set()) for e, hl in emp_hl.items()}


def _compoff_dates(filters):
	"""set of (employee, 'YYYY-MM-DD') covered by a submitted Compensatory Leave
	Request — the comp-off already granted."""
	conds = [["docstatus", "=", 1]]
	if filters.get("employee"):
		conds.append(["employee", "=", filters.employee])
	if filters.get("from_date"):
		conds.append(["work_end_date", ">=", filters.from_date])
	if filters.get("to_date"):
		conds.append(["work_from_date", "<=", filters.to_date])

	out = set()
	for r in frappe.get_all(
		"Compensatory Leave Request",
		filters=conds,
		fields=["employee", "work_from_date", "work_end_date"],
	):
		if not r.work_from_date:
			continue
		d, end = getdate(r.work_from_date), getdate(r.work_end_date or r.work_from_date)
		while d <= end:
			out.add((r.employee, d.isoformat()))
			d = add_days(d, 1)
	return out


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


def _compute(rows, s, holidays, compoff, weekly=False):
	from datetime import date

	# Comp-offs already granted — count per employee and per (employee, ISO week).
	comp_emp = defaultdict(int)
	comp_emp_week = defaultdict(int)
	for emp, dstr in compoff:
		comp_emp[emp] += 1
		iso = getdate(dstr).isocalendar()
		comp_emp_week[(emp, (iso[0], iso[1]))] += 1

	emp_meta = {}
	wk = defaultdict(lambda: {"net": 0.0, "dot": 0.0, "days": 0, "wo": 0})
	for r in rows:
		emp_meta[r.employee] = (r.employee_name, r.department)
		dstr = str(r.attendance_date)
		iso = getdate(r.attendance_date).isocalendar()
		bucket = wk[(r.employee, (iso[0], iso[1]))]
		# Worked a weekly-off / holiday (or already comp-off'd) -> comp-off, not OT.
		if dstr in holidays.get(r.employee, ()) or (r.employee, dstr) in compoff:
			bucket["wo"] += 1
			continue
		net = max(0.0, flt(r.working_hours) - s.lunch_hours)
		bucket["net"] += net
		bucket["dot"] += max(0.0, net - s.daily)
		bucket["days"] += 1

	def split(b):
		w_ot = max(0.0, b["net"] - s.weekly)
		return max(b["dot"], w_ot), b["dot"], w_ot

	def row(emp, days, net, dot, wot, ot, wo, given, week=None):
		d = {
			"employee": emp,
			"employee_name": emp_meta[emp][0],
			"department": emp_meta[emp][1],
			"days": days,
			"net_hours": round(net, 2),
			"permitted_hours": round(net - ot, 2),
			"daily_ot": round(dot, 2),
			"weekly_ot": round(wot, 2),
			"ot_hours": round(ot, 2),
			"wo_worked": wo,
			"compoff_given": given,
			"compoff_owed": max(0, wo - given),
		}
		if week is not None:
			d["week"] = week
		return d

	if weekly:
		data = []
		for (emp, w), b in sorted(wk.items(), key=lambda kv: (kv[0][0], kv[0][1])):
			ot, dot, wot = split(b)
			data.append(
				row(emp, b["days"], b["net"], dot, wot, ot, b["wo"], comp_emp_week.get((emp, w), 0), date.fromisocalendar(w[0], w[1], 1))
			)
		return data

	agg = defaultdict(lambda: {"days": 0, "net": 0.0, "dot": 0.0, "wot": 0.0, "ot": 0.0, "wo": 0})
	for (emp, w), b in wk.items():
		ot, dot, wot = split(b)
		a = agg[emp]
		a["days"] += b["days"]
		a["net"] += b["net"]
		a["dot"] += dot
		a["wot"] += wot
		a["ot"] += ot
		a["wo"] += b["wo"]

	data = [
		row(emp, a["days"], a["net"], a["dot"], a["wot"], a["ot"], a["wo"], comp_emp.get(emp, 0))
		for emp, a in agg.items()
	]
	data.sort(key=lambda x: (-x["ot_hours"], -x["compoff_owed"]))
	return data
