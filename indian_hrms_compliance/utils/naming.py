# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Custom naming-series variables.

Frappe's naming series natively supports .YY. / .YYYY. / .MM. / .DD. / .WW. /
.#### and .{fieldname}., but NOT fiscal year. This registers a ``.FY.`` token
(via the ``naming_series_variables`` hook) that renders the 2-digit END year of
the fiscal year — FY 2026-27 -> ``27`` — so ``JV.FY.-.####.`` gives ``JV27-0001``.
"""

import frappe
from frappe.utils import getdate, nowdate

_DATE_FIELDS = (
	"posting_date",
	"start_date",
	"attendance_date",
	"from_date",
	"time",
	"transaction_date",
	"end_date",
	"date",
)


def fy_short(date):
	"""2-digit END year of the fiscal year for ``date`` — FY 2026-27 -> '27'.
	Uses a matching Fiscal Year record if present, else an Apr-March year."""
	date = getdate(date)
	end_date = frappe.db.get_value(
		"Fiscal Year",
		{"year_start_date": ["<=", date], "year_end_date": [">=", date]},
		"year_end_date",
		order_by="year_start_date desc",
	)
	if end_date:
		return getdate(end_date).strftime("%y")
	end_year = date.year + 1 if date.month >= 4 else date.year
	return f"{end_year % 100:02d}"


def _doc_date(doc, preferred=None):
	fields = ([preferred] if preferred else []) + list(_DATE_FIELDS)
	if doc is not None and hasattr(doc, "get"):
		for field in fields:
			val = doc.get(field)
			if val:
				return getdate(val)
	return getdate(nowdate())


def get_fiscal_year(doc=None, key="FY"):
	"""Resolve the ``.FY.`` naming token to the 2-digit END year of the fiscal
	year for the document's date — e.g. FY 2026-2027 -> '27'."""
	return fy_short(_doc_date(doc))


def employee_series_name(doc, date_field):
	"""Build ``{FY2}/{employee}/{MM}/####`` from the doc's employee + the given
	period date field (e.g. attendance_date / from_date / posting_date / time).
	The counter resets per (fiscal year, employee, month)."""
	from frappe.model.naming import make_autoname

	d = _doc_date(doc, preferred=date_field)
	emp = (doc.get("employee") if hasattr(doc, "get") else None) or "NA"
	return make_autoname(f"{fy_short(d)}/{emp}/{d.strftime('%m')}/.#####.")
