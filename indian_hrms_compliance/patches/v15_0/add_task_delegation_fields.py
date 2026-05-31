"""Task leave-cover delegation fields on Goal (Task Instance).

delegated_from = original assignee when a task is routed to the reporting
manager during leave; performed_by = who actually did it (captured on
completion of a delegated task).
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Goal": [
				{
					"fieldname": "delegated_from",
					"fieldtype": "Link",
					"label": "Delegated From",
					"options": "Employee",
					"insert_after": "status",
					"read_only": 1,
				},
				{
					"fieldname": "performed_by",
					"fieldtype": "Link",
					"label": "Performed By",
					"options": "Employee",
					"insert_after": "delegated_from",
				},
			]
		},
		ignore_validate=True,
	)
