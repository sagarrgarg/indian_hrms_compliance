# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Custom naming-series variables.

Frappe's naming series natively supports .YY. / .YYYY. / .MM. / .DD. / .WW. /
.#### and .{fieldname}., but NOT fiscal year. This registers a ``.FY.`` token
(via the ``naming_series_variables`` hook) so series like ``JV.FY.-.####.``
render as e.g. ``JV2026-2027-0001`` — the fiscal year of the document's date.
"""

import frappe
from frappe.utils import getdate, nowdate


def get_fiscal_year(doc=None, key="FY"):
	"""Resolve the ``.FY.`` naming token to the fiscal-year name (e.g. '2026-2027')
	for the document's date. Tries the common date fields, then falls back to
	today. Returns the calendar year as a last resort if no Fiscal Year is found.
	"""
	date = None
	if doc is not None and hasattr(doc, "get"):
		for field in ("posting_date", "start_date", "transaction_date", "end_date", "date"):
			val = doc.get(field)
			if val:
				date = val
				break
	date = getdate(date) if date else getdate(nowdate())

	fy = frappe.db.get_value(
		"Fiscal Year",
		{"year_start_date": ["<=", date], "year_end_date": [">=", date]},
		"name",
		order_by="year_start_date desc",
	)
	return fy or str(date.year)
