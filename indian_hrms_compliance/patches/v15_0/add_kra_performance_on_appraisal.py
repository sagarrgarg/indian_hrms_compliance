# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	"""Phase 3 Item G: add KRA Performance HTML section to Appraisal,
	auto-fed from Task Instances."""
	create_custom_fields(
		{
			"Appraisal": [
				{
					"fieldname": "kra_performance_section",
					"fieldtype": "Section Break",
					"label": "KRA Performance from Task Instances (Auto)",
					"insert_after": "appraisal_kra",
					"collapsible": 1,
					"description": (
						"Computed from this Employee's Task Instances (Goal records "
						"with goal_type='Task Instance') in the cycle period. "
						"Refreshed on each save of this Appraisal."
					),
				},
				{
					"fieldname": "kra_performance_html",
					"fieldtype": "HTML",
					"label": "KRA Performance HTML",
					"insert_after": "kra_performance_section",
				},
			]
		},
		ignore_validate=True,
	)
