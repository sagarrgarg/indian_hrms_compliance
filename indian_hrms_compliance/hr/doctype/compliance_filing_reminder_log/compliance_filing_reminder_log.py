# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Compliance Filing Reminder Log — Phase 6C.

Append-only audit trail of every reminder sent for a Compliance Filing
row. Lets HR answer 'did we actually warn the team about this?' after
a missed deadline.
"""

import frappe
from frappe.model.document import Document


class ComplianceFilingReminderLog(Document):
	pass
