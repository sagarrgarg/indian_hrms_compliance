# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Post-model-sync companion to `nativize_hr_settings_drop_stale_custom_fields`.

The HR Settings fields are now native docfields, but a native `default` does NOT
back-fill an existing Single (its one row predates the field) — so seed the
values that used to be seeded inside the now-removed field-creation patches:
`self_editable_employee_fields`, `employee_consent_text_version` and the two
onboarding fields. (The PF/ESI, Phase-6B2, Compliance-Calendar, DPDP and
Labour-Code defaults keep their own dedicated seed_* patches, which now seed
against the native fields.)

Also preserves the Employee Onboarding Application audit backfill that lived in
the retired `onboarding_compliance_lockdown` patch. All steps are idempotent."""

import frappe

# Verbatim from the retired add_profile_change_request_settings patch.
DEFAULT_EDITABLE_TEXT = """# Personal
cell_number
personal_email
current_address
permanent_address
marital_status
blood_group

# Emergency contact
person_to_be_contacted
relation
emergency_phone_number

# Statutory IDs — sensitive; current value is masked in the PWA prefill.
pan_number
aadhaar_number
uan_number
esic_ip_number
provident_fund_account
nps_pran

# Bank
bank_name
bank_ac_no
ifsc_code

# Photo
image
"""


def execute():
	if not frappe.db.exists("DocType", "HR Settings"):
		return
	# Belt-and-braces: make sure the native fields are in the meta before we seed.
	frappe.reload_doc("hr", "doctype", "hr_settings")

	_seed_if_blank("self_editable_employee_fields", DEFAULT_EDITABLE_TEXT)
	_seed_if_blank("employee_consent_text_version", "1.0")
	_seed_if_blank("onboarding_invite_validity_days", 30)
	_seed_if_blank("onboarding_min_employment_age", 14)

	_backfill_application_audit_columns()
	frappe.clear_cache(doctype="HR Settings")


def _seed_if_blank(fieldname, value):
	# §1 guard: has_field before get_single_value so a partial state never raises.
	if not frappe.get_meta("HR Settings").has_field(fieldname):
		return
	if not frappe.db.get_single_value("HR Settings", fieldname):
		frappe.db.set_single_value("HR Settings", fieldname, value)


def _backfill_application_audit_columns():
	"""Preserved from onboarding_compliance_lockdown: stamp legacy Employee
	Onboarding Application rows with audit values. Idempotent (only NULLs)."""
	if not frappe.db.table_exists("Employee Onboarding Application"):
		return

	if _has_column("Employee Onboarding Application", "submitted_on"):
		frappe.db.sql(
			"""UPDATE `tabEmployee Onboarding Application`
			   SET submitted_on = creation
			 WHERE submitted_on IS NULL"""
		)

	if _has_column("Employee Onboarding Application", "consent_timestamp"):
		frappe.db.sql(
			"""UPDATE `tabEmployee Onboarding Application`
			   SET consent_timestamp = creation
			 WHERE consent_timestamp IS NULL
			   AND dpdp_consent = 1"""
		)

	if _has_column("Employee Onboarding Application", "consent_text_version"):
		frappe.db.sql(
			"""UPDATE `tabEmployee Onboarding Application`
			   SET consent_text_version = '1.0'
			 WHERE (consent_text_version IS NULL OR consent_text_version = '')
			   AND dpdp_consent = 1"""
		)

	frappe.db.commit()


def _has_column(doctype, column):
	return column in frappe.db.get_table_columns(doctype)
