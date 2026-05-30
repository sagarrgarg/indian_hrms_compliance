# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Data Retention Rule — drives the weekly DPDP purge scheduler.

Phase 6D. Per DPDP Sec 8(7) — Data Fiduciary must erase personal data
when the purpose has been served, UNLESS retention is required by law.
The HR-default of 8 years (Companies Act 2013 + Income Tax Act records
retention) is encoded as the global default; per-doctype rules can
override.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class DataRetentionRule(Document):
	def validate(self):
		if self.field_or_record == "Field-Level" and not self.field_name:
			frappe.throw(_("Field Name is required for Field-Level scope."))
		if (self.retention_period_years or 0) <= 0:
			frappe.throw(_("Retention Period (Years) must be positive."))
		if self.applicable_when_condition and ";" in self.applicable_when_condition:
			frappe.throw(_("SQL WHERE fragment must not contain ';'."))
