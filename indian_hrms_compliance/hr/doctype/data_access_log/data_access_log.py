# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Data Access Log — append-only audit of sensitive field access.

Phase 6D. Per DPDP Sec 8 (Data Fiduciary duties — reasonable security
safeguards) and Sec 11 (Data Principal right to know about processing),
we log who accessed which sensitive PII field on which record.

CRITICAL: never log the VALUE — only the field NAME + record ref.
"""

import frappe
from frappe.model.document import Document


class DataAccessLog(Document):
	"""No business logic — append-only. Manual UI creation is blocked
	at the permission layer (HR Manager has read-only)."""

	pass
