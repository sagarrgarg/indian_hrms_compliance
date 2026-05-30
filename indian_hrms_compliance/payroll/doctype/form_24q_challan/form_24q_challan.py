# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Form 24Q Challan — Phase 6B-2.

Child row representing one TDS challan paid via OLTAS / e-Payment under
Section 192. Multiple deductee rows (Annexure I) reference this challan
by its serial number. Per CPC TDS, a quarter's statement can carry many
challans (one per tranche of monthly TDS remittance)."""

from frappe.model.document import Document


class Form24QChallan(Document):
	pass
