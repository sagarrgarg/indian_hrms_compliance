# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""PF ECR Row — child of PF ECR Filing.

One row per Employee × Wage Month in the EPFO Electronic Challan-cum-Return
(ECR) text file. Per EPFO ECR 2.0 spec, each row carries 11 pipe-delimited
fields ending in Refund of Advances (almost always 0).
"""

from frappe.model.document import Document


class PFECRRow(Document):
	pass
