# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Statutory Component Mapping — Phase 6A.

Per-Company canonical reference of which Salary Components map to which
statutory line. The Salary Structure Validator reads from here to:

  - check that PF Employee/Employer/EPS/EDLI/Admin rows exist when PF
    applies,
  - check that ESI Employee/Employer rows exist when ESI applies,
  - check that PT / LWF rows exist when the state mandates them,
  - check that Basic/DA components are present so the Wage Code §2(y)
    50% rule can be computed correctly.

Validation here is intentionally lenient (warnings only) — a Company may
genuinely lack ESI applicability if all employees earn > ₹21,000/mo. The
real enforcement lives in the validator that consumes this mapping.
"""

import frappe
from frappe import _
from frappe.model.document import Document


# Components considered essential for any minimally compliant Indian
# salary structure. Warned (not blocked) if missing.
RECOMMENDED_COMPONENTS = (
	"basic_component",
	"pf_employee_component",
	"pf_employer_component",
	"pt_component",
	"income_tax_component",
)


class StatutoryComponentMapping(Document):
	def validate(self):
		missing = [
			self.meta.get_field(f).label
			for f in RECOMMENDED_COMPONENTS
			if not self.get(f)
		]
		if missing:
			frappe.msgprint(
				_(
					"Statutory Component Mapping for {0} is missing recommended components: {1}. "
					"Salary Structure validation may flag these as warnings until set."
				).format(self.company, ", ".join(missing)),
				indicator="orange",
				alert=True,
			)


def get_mapping_for_company(company):
	"""Return the Statutory Component Mapping doc for a Company, or None."""
	name = frappe.db.exists("Statutory Component Mapping", {"company": company})
	if not name:
		return None
	return frappe.get_cached_doc("Statutory Component Mapping", name)
