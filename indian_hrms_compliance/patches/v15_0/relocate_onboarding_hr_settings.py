# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Re-home the Employee Onboarding tunables in HR Settings.

onboarding_compliance_lockdown (#2026-06-04) created two onboarding controls —
onboarding_invite_validity_days and onboarding_min_employment_age — anchored
after ``dpdp_aadhaar_consent_required``. That dropped them inside the Statutory
tab's "Digital Personal Data Protection (DPDP)" section, where nobody looks for
an onboarding age limit, so HR reported the setting as "missing in HR Settings".

This patch is SELF-CONTAINED and DEFENSIVE — it must not assume the earlier
lockdown patch ran (on some sites the fields don't exist yet, and a hard
``get_single_value`` on a missing field aborts the whole migration):

  1. Upserts a clearly labelled "Employee Onboarding" section plus both tunables
     into the "Probation & Confirmation" tab. ``create_custom_fields`` creates
     them when absent and updates insert_after/label when present, so this is the
     single source of truth for their placement.
  2. Detaches the DPDP/profile tail (self_editable_employee_fields ->
     employee_consent_text_version) that add_profile_change_request_settings
     chained onto onboarding_min_employment_age, so it stays in the DPDP section.
  3. Seeds the intended defaults (invite 30 days, min age 14) where the Single
     still holds the column-default 0 — create_custom_fields sets a field default
     but never back-fills an existing Single.

Idempotent and re-runnable: a failed migrate leaves the patch unlogged, so it
re-runs from the top next time.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

SECTION = "onboarding_settings_section"

HR_SETTINGS_FIELDS = {
	"HR Settings": [
		{
			"fieldname": SECTION,
			"fieldtype": "Section Break",
			"label": "Employee Onboarding",
			"insert_after": "probation_review_reminder_window_days",
		},
		{
			"fieldname": "onboarding_invite_validity_days",
			"fieldtype": "Int",
			"label": "Invite Link Validity (Days)",
			"insert_after": SECTION,
			"default": "30",
			"description": (
				"How many days an Employee Onboarding invite link stays valid once "
				"generated. Tokens self-disable past this. Default 30."
			),
		},
		{
			"fieldname": "onboarding_min_employment_age",
			"fieldtype": "Int",
			"label": "Minimum Employment Age",
			"insert_after": "onboarding_invite_validity_days",
			"default": "14",
			"description": (
				"Candidates whose DOB implies an age below this are blocked on the "
				"Employee Onboarding Application. Default 14 (Child Labour "
				"(Prohibition and Regulation) Act, 1986). Set 18 for adults-only."
			),
		},
	]
}


def execute():
	if not frappe.db.exists("DocType", "HR Settings"):
		return

	# 1. Upsert the section + both tunables in their proper home. Idempotent:
	#    creates when missing (fresh sites / sites where lockdown never made them)
	#    and moves + relabels them when present (sites where they sat in DPDP).
	create_custom_fields(HR_SETTINGS_FIELDS, ignore_validate=True)

	# 2. Detach the DPDP/profile tail add_profile_change_request_settings
	#    (#2026-06-04) chained onto onboarding_min_employment_age, so it doesn't
	#    follow the onboarding fields out of the DPDP section. No-op if absent.
	_reanchor("self_editable_employee_fields", "dpdp_aadhaar_consent_required")

	# 3. Seed intended defaults where the Single still holds 0.
	_seed_if_blank("onboarding_invite_validity_days", 30)
	_seed_if_blank("onboarding_min_employment_age", 14)

	frappe.clear_cache(doctype="HR Settings")
	print("  Relocated onboarding tunables into the 'Employee Onboarding' HR Settings section")


def _reanchor(fieldname: str, insert_after: str):
	"""Move an EXISTING Custom Field. Never create here — a missing field is a
	silent no-op so it can't abort the migration."""
	name = frappe.db.get_value("Custom Field", {"dt": "HR Settings", "fieldname": fieldname})
	if name and frappe.db.get_value("Custom Field", name, "insert_after") != insert_after:
		frappe.db.set_value("Custom Field", name, "insert_after", insert_after)


def _seed_if_blank(fieldname: str, value):
	"""Seed a Single value, guarding the read. frappe.db.get_single_value RAISES
	when the field is absent from the meta — which would abort the whole migrate —
	so confirm it exists first."""
	if not frappe.get_meta("HR Settings").has_field(fieldname):
		return
	if not frappe.db.get_single_value("HR Settings", fieldname):
		frappe.db.set_single_value("HR Settings", fieldname, value)
