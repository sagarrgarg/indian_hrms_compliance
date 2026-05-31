"""Company Salary Components — own tab + sensible defaults.

The standard arrear/hra/basic component fields previously rendered under the
Print Options tab. Give them a dedicated "Salary Components" tab and default
them to the app's seeded components (Basic / House Rent Allowance / Arrear)
where unset.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from indian_hrms_compliance.overrides.company import set_default_salary_components


def get_fields():
	return {
		"Company": [
			{
				"fieldname": "salary_components_tab",
				"fieldtype": "Tab Break",
				"label": "Salary Components",
				"insert_after": "registration_details_for_printing",
			},
		],
	}


def execute():
	create_custom_fields(get_fields(), ignore_validate=True)

	for name in frappe.get_all("Company", pluck="name"):
		doc = frappe.get_doc("Company", name)
		set_default_salary_components(doc)
