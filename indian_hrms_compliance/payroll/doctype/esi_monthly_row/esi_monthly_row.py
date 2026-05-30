# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""ESI Monthly Row — child of ESI Monthly Contribution.

One row per Insured Person × Wage Month. Maps directly to the ESIC
portal Monthly Contribution upload columns: IP Number | IP Name |
No of Days | Total Monthly Wages | Reason Code | Last Working Day.
"""

from frappe.model.document import Document


class ESIMonthlyRow(Document):
	pass
