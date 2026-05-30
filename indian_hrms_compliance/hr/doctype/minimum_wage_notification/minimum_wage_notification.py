# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Minimum Wage Notification — Phase 6A.

Per state × designation_category × effective_from. The validator reads
the latest currently-effective row for a given (state, category) when
checking that a Salary Structure clears the floor.

Designation categories follow the typical state notification structure
(Unskilled / Semi-Skilled / Skilled / Highly Skilled, plus Clerical /
Supervisory variants for shops & establishments).
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class MinimumWageNotification(Document):
	def validate(self):
		if not (self.daily_rate or self.monthly_rate):
			frappe.throw(_("At least one of Daily Rate or Monthly Rate must be set."))
		if self.effective_to and getdate(self.effective_to) < getdate(self.effective_from):
			frappe.throw(_("Effective To cannot be before Effective From."))


def get_effective_minimum_wage(state, designation_category, on_date=None):
	"""Returns the dict for the currently-effective Minimum Wage Notification
	for the given (state, category) as of `on_date`, or None.

	Falls back to most recent (by effective_from) if none is currently
	effective on `on_date`."""
	from frappe.utils import nowdate

	on_date = on_date or nowdate()
	row = frappe.db.sql(
		"""
		SELECT name, daily_rate, monthly_rate, effective_from, effective_to,
		       notification_reference
		FROM `tabMinimum Wage Notification`
		WHERE state = %s AND designation_category = %s
		  AND effective_from <= %s
		  AND (effective_to IS NULL OR effective_to = '' OR effective_to >= %s)
		ORDER BY effective_from DESC
		LIMIT 1
		""",
		(state, designation_category, on_date, on_date),
		as_dict=True,
	)
	if row:
		return row[0]
	# Fallback: most recent ever for this (state, category)
	row = frappe.db.sql(
		"""
		SELECT name, daily_rate, monthly_rate, effective_from, effective_to,
		       notification_reference
		FROM `tabMinimum Wage Notification`
		WHERE state = %s AND designation_category = %s
		ORDER BY effective_from DESC
		LIMIT 1
		""",
		(state, designation_category),
		as_dict=True,
	)
	return row[0] if row else None


def derive_effective_monthly_floor(row):
	"""Given a Minimum Wage row, returns the monthly floor in INR.
	Uses monthly_rate if set, else daily_rate × 26."""
	if not row:
		return 0
	monthly = flt(row.get("monthly_rate"))
	if monthly:
		return monthly
	daily = flt(row.get("daily_rate"))
	return daily * 26 if daily else 0
