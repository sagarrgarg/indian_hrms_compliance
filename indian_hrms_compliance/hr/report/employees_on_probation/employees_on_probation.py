# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Employees on Probation — HR tracker.

Lists every Active employee whose confirmation_status is 'Probation' (the state
the New Employee Setup page and the probation-schedule hook set), and works out
how far through probation each one is. The probation window runs from
date_of_joining to scheduled_confirmation_date (the app's probation-end field),
so HR can see at a glance who is due — or overdue — for a confirmation decision.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

# Within this many days of the scheduled end, flag the row as "due soon" so HR
# acts before the probation window closes.
DUE_SOON_DAYS = 14


def execute(filters=None):
	filters = filters or {}
	return _get_columns(), _get_data(filters)


def _get_columns():
	return [
		{
			"label": _("Employee"),
			"fieldname": "employee",
			"fieldtype": "Link",
			"options": "Employee",
			"width": 130,
		},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
		{
			"label": _("Company"),
			"fieldname": "company",
			"fieldtype": "Link",
			"options": "Company",
			"width": 160,
		},
		{
			"label": _("Department"),
			"fieldname": "department",
			"fieldtype": "Link",
			"options": "Department",
			"width": 150,
		},
		{"label": _("Date of Joining"), "fieldname": "date_of_joining", "fieldtype": "Date", "width": 120},
		{"label": _("Probation Ends"), "fieldname": "probation_end", "fieldtype": "Date", "width": 120},
		{"label": _("Weeks Done"), "fieldname": "weeks_completed", "fieldtype": "Float", "width": 100},
		{"label": _("Weeks Left"), "fieldname": "weeks_remaining", "fieldtype": "Float", "width": 100},
		{"label": _("% Elapsed"), "fieldname": "elapsed_pct", "fieldtype": "Percent", "width": 110},
	]


def _get_data(filters):
	conditions = {"status": "Active", "confirmation_status": "Probation"}
	for f in ("company", "department"):
		if filters.get(f):
			conditions[f] = filters[f]

	employees = frappe.get_all(
		"Employee",
		filters=conditions,
		fields=[
			"name AS employee",
			"employee_name",
			"company",
			"department",
			"date_of_joining",
			"scheduled_confirmation_date AS probation_end",
		],
		order_by="scheduled_confirmation_date asc, date_of_joining asc",
	)

	today_d = getdate(today())
	rows = []
	for e in employees:
		doj = getdate(e.date_of_joining) if e.date_of_joining else None
		end = getdate(e.probation_end) if e.probation_end else None

		e["weeks_completed"] = round(max((today_d - doj).days, 0) / 7.0, 1) if doj else None
		e["weeks_remaining"] = round((end - today_d).days / 7.0, 1) if end else None

		if doj and end and end > doj:
			pct = (today_d - doj).days / (end - doj).days * 100.0
			e["elapsed_pct"] = flt(min(max(pct, 0.0), 100.0), 1)
		else:
			e["elapsed_pct"] = None

		# Surfaced for the colour formatter in employees_on_probation.js.
		e["_overdue"] = bool(end and end < today_d)
		e["_due_soon"] = bool(end and not e["_overdue"] and (end - today_d).days <= DUE_SOON_DAYS)
		rows.append(e)

	return rows
