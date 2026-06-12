# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Onboarding form: compliance lockdown + UX polish.

(1) Adds Custom Fields to HR Settings for two tunables:
      - onboarding_invite_validity_days (Int, default 30)
      - onboarding_min_employment_age   (Int, default 14)

(2) Backfills Employee Onboarding Application rows created before the consent
    audit fields existed so reports don't show a sea of NULLs:
      - submitted_on   <= creation
      - consent_timestamp <= creation (only where dpdp_consent=1)
      - consent_text_version <= "1.0" where blank

(3) Verifies the schema sync brought the new doctype fields through. If the
    Frappe schema sync hasn't run yet for any reason, this patch is a no-op
    on those columns — `migrate` runs sync before patches anyway.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


HR_SETTINGS_FIELDS = {
	"HR Settings": [
		{
			"fieldname": "onboarding_invite_validity_days",
			"fieldtype": "Int",
			"label": "Onboarding: Invite Link Validity (Days)",
			"insert_after": "dpdp_aadhaar_consent_required",
			"default": "30",
			"description": (
				"How many days an Employee Onboarding invite link stays valid "
				"once generated. Tokens are HMAC-signed with this expiry baked in "
				"so a leaked link self-disables. Default 30."
			),
		},
		{
			"fieldname": "onboarding_min_employment_age",
			"fieldtype": "Int",
			"label": "Onboarding: Minimum Employment Age",
			"insert_after": "onboarding_invite_validity_days",
			"default": "14",
			"description": (
				"Hard lock on the Employee Onboarding Application: candidates "
				"with a DOB implying age below this number are blocked. "
				"Default 14 (Child Labour (Prohibition and Regulation) Act, 1986). "
				"Set to 18 to enforce 'adults only' onboarding."
			),
		},
	]
}


def execute():
	create_custom_fields(HR_SETTINGS_FIELDS, ignore_validate=True)
	_backfill_application_audit_columns()
	print("  Onboarding lockdown: HR Settings tunables added + audit backfill complete")


def _backfill_application_audit_columns():
	if not frappe.db.table_exists("Employee Onboarding Application"):
		return

	# submitted_on — every legacy row submitted itself at creation time.
	if _has_column("Employee Onboarding Application", "submitted_on"):
		frappe.db.sql(
			"""UPDATE `tabEmployee Onboarding Application`
			   SET submitted_on = creation
			 WHERE submitted_on IS NULL"""
		)

	# consent_timestamp — only meaningful when dpdp_consent was ticked.
	if _has_column("Employee Onboarding Application", "consent_timestamp"):
		frappe.db.sql(
			"""UPDATE `tabEmployee Onboarding Application`
			   SET consent_timestamp = creation
			 WHERE consent_timestamp IS NULL
			   AND dpdp_consent = 1"""
		)

	# consent_text_version — every legacy row used v1.0 wording.
	if _has_column("Employee Onboarding Application", "consent_text_version"):
		frappe.db.sql(
			"""UPDATE `tabEmployee Onboarding Application`
			   SET consent_text_version = '1.0'
			 WHERE (consent_text_version IS NULL OR consent_text_version = '')
			   AND dpdp_consent = 1"""
		)

	frappe.db.commit()


def _has_column(doctype: str, column: str) -> bool:
	return column in frappe.db.get_table_columns(doctype)
