# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Re-home the Employee Onboarding tunables in HR Settings.

onboarding_compliance_lockdown (#2026-06-04) created two onboarding controls —
onboarding_invite_validity_days and onboarding_min_employment_age — anchored
after ``dpdp_aadhaar_consent_required``. That dropped them inside the Statutory
tab's "Digital Personal Data Protection (DPDP)" section, where nobody looks for
an onboarding age limit, so HR reported the setting as "missing in HR Settings".

This patch:
  1. Adds a clearly labelled "Employee Onboarding" section at the end of the
     "Probation & Confirmation" tab (the joining-lifecycle tab).
  2. Moves both onboarding controls out of the DPDP section into it. Only
     invite_validity is re-anchored explicitly; min_employment_age already
     trails it, so it follows automatically.
  3. Seeds the stored values to their intended defaults (invite 30 days,
     min age 14) where the Single still holds the column-default 0 — the
     original create_custom_fields default never back-fills an existing Single,
     so the form was showing a misleading 0.

Idempotent: re-anchoring to the same parent and seeding only-when-falsy are both
safe to repeat.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

SECTION = "onboarding_settings_section"


def execute():
	if not frappe.db.exists("DocType", "HR Settings"):
		return

	# 1. The new home: a section at the end of the Probation & Confirmation tab.
	create_custom_fields(
		{
			"HR Settings": [
				{
					"fieldname": SECTION,
					"fieldtype": "Section Break",
					"label": "Employee Onboarding",
					"insert_after": "probation_review_reminder_window_days",
				}
			]
		},
		ignore_validate=True,
	)

	# 2. Relocate the two tunables out of the DPDP section. min_employment_age
	#    is anchored to invite_validity_days, so moving the latter carries both.
	_reanchor("onboarding_invite_validity_days", SECTION)
	_reanchor("onboarding_min_employment_age", "onboarding_invite_validity_days")

	# 2b. Detach the DPDP/profile tail that add_profile_change_request_settings
	#     (#2026-06-04) chained onto onboarding_min_employment_age. Without this,
	#     self_editable_employee_fields -> employee_consent_text_version would
	#     follow the onboarding fields out of the DPDP section. Re-anchor the tail
	#     back onto the DPDP Aadhaar-consent field so it stays put.
	_reanchor("self_editable_employee_fields", "dpdp_aadhaar_consent_required")

	# 3. Back-fill the intended defaults where the Single still shows 0.
	if not frappe.db.get_single_value("HR Settings", "onboarding_invite_validity_days"):
		frappe.db.set_single_value("HR Settings", "onboarding_invite_validity_days", 30)
	if not frappe.db.get_single_value("HR Settings", "onboarding_min_employment_age"):
		frappe.db.set_single_value("HR Settings", "onboarding_min_employment_age", 14)

	frappe.clear_cache(doctype="HR Settings")
	print("  Relocated onboarding tunables into the 'Employee Onboarding' HR Settings section")


def _reanchor(fieldname: str, insert_after: str):
	name = frappe.db.get_value("Custom Field", {"dt": "HR Settings", "fieldname": fieldname})
	if name and frappe.db.get_value("Custom Field", name, "insert_after") != insert_after:
		frappe.db.set_value("Custom Field", name, "insert_after", insert_after)
