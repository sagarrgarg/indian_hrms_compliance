# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""ESI Half Yearly Filing Reference — child of ESI Half Yearly Return.

Lightweight link table — each row points at one of the six ESI Monthly
Contribution docs that comprise the half-yearly Return of Contributions
(RoC) under Reg 26 of the ESI (General) Regulations 1950.
"""

from frappe.model.document import Document


class ESIHalfYearlyFilingReference(Document):
	pass
