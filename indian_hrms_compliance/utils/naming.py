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


def get_fiscal_year(doc=None, key="FY"):
	"""Resolve the ``.FY.`` naming token to the 2-digit END year of the fiscal
	year for the document's date — e.g. FY 2026-2027 -> '27', FY 2027-2028 -> '28'.
	Tries the common date fields, then falls back to today; if no Fiscal Year
	record matches, assumes an April-March year.
	"""
	date = None
	if doc is not None and hasattr(doc, "get"):
		for field in ("posting_date", "start_date", "transaction_date", "end_date", "date"):
			val = doc.get(field)
			if val:
				date = val
				break
	date = getdate(date) if date else getdate(nowdate())

	end_date = frappe.db.get_value(
		"Fiscal Year",
		{"year_start_date": ["<=", date], "year_end_date": [">=", date]},
		"year_end_date",
		order_by="year_start_date desc",
	)
	if end_date:
		return getdate(end_date).strftime("%y")
	# Fallback: Indian April-March fiscal year (ends the next calendar year for
	# Apr-Dec dates, this calendar year for Jan-Mar).
	end_year = date.year + 1 if date.month >= 4 else date.year
	return f"{end_year % 100:02d}"
