# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Cadence Schedule — one occurrence per fiscal year of a recurring thing.

A child row (istable) attached to any parent that recurs on explicit dates
(Compliance Return Definition, HRMS Task, …). The heavy lifting — turning a row
into absolute dates for a given FY — lives in ``utils.cadence`` so it stays pure
and testable. This controller only guards a single row's sanity; cross-row rules
(label uniqueness) belong to the parent, which owns the whole table.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class CadenceSchedule(Document):
    def validate(self):
        # due_day: 0 (last day) or 1..31. The engine clamps overflow, but reject
        # clearly bad input at the source so the author sees it immediately.
        if self.due_day is not None:
            try:
                day = int(self.due_day)
            except (TypeError, ValueError):
                frappe.throw(_("Row {0}: Due Day must be a whole number.").format(self.idx))
            if day < 0 or day > 31:
                frappe.throw(
                    _("Row {0}: Due Day must be between 0 (last day) and 31.").format(self.idx)
                )
