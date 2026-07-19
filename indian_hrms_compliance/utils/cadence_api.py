# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Whitelisted wrappers around the pure ``utils.cadence`` engine.

Kept separate so ``cadence.py`` stays import-clean and unit-testable without
Frappe. These are what the form buttons (Generate rows / Preview dates) call.
"""

import frappe
from frappe.utils import getdate

from indian_hrms_compliance.utils import cadence as C


@frappe.whitelist()
def generate_schedule_rows(cadence, due_day=0, due_month_offset=1, months=None, label_prefix=""):
    """Return a starter set of Cadence Schedule rows for a standard cadence.

    The form appends these to the child table; the author then tweaks the one or
    two irregular occurrences (e.g. TDS Q4 -> 31 May) by hand.
    """
    if isinstance(months, str) and months.strip():
        months = frappe.parse_json(months)
    return C.generate_rows(
        cadence,
        due_day=int(due_day or 0),
        due_month_offset=int(due_month_offset or 1),
        months=months or None,
        label_prefix=label_prefix or "",
    )


@frappe.whitelist()
def preview_schedule(rows, fy_start_year=None):
    """Resolve schedule rows into concrete dates for a FY — a 'what will this
    actually produce?' preview, shown in a dialog before the author commits."""
    rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
    fy = int(fy_start_year) if fy_start_year else C.fy_start_year_for(getdate())
    return {
        "fy_label": C.fy_label(fy),
        "occurrences": [
            {
                "label": o["label"],
                "period_start": str(o["period_start"]),
                "period_end": str(o["period_end"]),
                "due_date": str(o["due_date"]),
            }
            for o in C.resolve_schedule(rows, fy)
        ],
    }
