# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Form 24Q Annexure I Row — Phase 6B-2.

One row per (Salary Slip × challan attribution). Filed every quarter.
PAN is mandatory at RPU validation unless ``reason_for_lower_no_deduction``
explains a non-deduction case."""

from frappe.model.document import Document


class Form24QAnnexureIRow(Document):
	pass
