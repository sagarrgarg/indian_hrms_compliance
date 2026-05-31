"""Add the 'Setup Status' tab + HTML holder to the Employee form.

The tab is rendered client-side (public/js/erpnext/employee.js) from
overrides.employee_master.get_employee_readiness.
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Employee": [
				{
					"fieldname": "setup_status_tab",
					"fieldtype": "Tab Break",
					"label": "Setup Status",
					"insert_after": "connections_tab",
				},
				{
					"fieldname": "employee_readiness_html",
					"fieldtype": "HTML",
					"insert_after": "setup_status_tab",
				},
			]
		},
		ignore_validate=True,
	)
