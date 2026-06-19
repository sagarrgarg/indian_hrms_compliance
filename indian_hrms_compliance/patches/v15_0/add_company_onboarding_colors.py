# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Per-company brand colours for the public onboarding web form.

Adds two Color custom fields on Company. When a candidate opens the onboarding
form via an HR invite, the form is themed with the *target* company's colours
(resolved server-side in get_invite_prefill). Left blank, the form falls back to
the product's saffron/terracotta brand palette — so this is purely opt-in.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def get_fields():
	return {
		"Company": [
			{
				"fieldname": "onboarding_branding_section",
				"fieldtype": "Section Break",
				"label": "Onboarding Form Branding",
				"description": (
					"Colours used to theme the public employee onboarding web form for "
					"candidates invited to this company. Leave blank to use the default "
					"brand palette."
				),
				"insert_after": "default_salary_structure",
			},
			{
				"fieldname": "onboarding_primary_color",
				"fieldtype": "Color",
				"label": "Onboarding Primary Colour",
				"insert_after": "onboarding_branding_section",
				"description": "Main accent — header band, buttons, active fields.",
			},
			{
				"fieldname": "onboarding_branding_column",
				"fieldtype": "Column Break",
				"insert_after": "onboarding_primary_color",
			},
			{
				"fieldname": "onboarding_secondary_color",
				"fieldtype": "Color",
				"label": "Onboarding Secondary Colour",
				"insert_after": "onboarding_branding_column",
				"description": "Gradient partner for the primary — used in the header sweep.",
			},
		],
	}


def execute():
	create_custom_fields(get_fields(), ignore_validate=True)
	print("  Added Company onboarding_primary_color + onboarding_secondary_color")
