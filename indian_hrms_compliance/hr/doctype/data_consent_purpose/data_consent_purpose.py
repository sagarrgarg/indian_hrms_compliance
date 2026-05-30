# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Data Consent Purpose — DPDP master of processing purposes.

Phase 6D. Sec 5 + 6 of the DPDP Act 2023 require that personal data is
collected only for an identified purpose and that the Data Principal is
notified of that purpose. This master is the catalogue.

Seeded by `patches.v15_0.seed_dpdp_defaults`.
"""

import frappe
from frappe.model.document import Document


class DataConsentPurpose(Document):
	def validate(self):
		# Normalise purpose_code: strip + uppercase + replace spaces.
		if self.purpose_code:
			self.purpose_code = self.purpose_code.strip().upper().replace(" ", "_").replace("-", "_")
