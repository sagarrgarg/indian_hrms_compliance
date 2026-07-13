# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Pre-model-sync: these HR Settings fields are now NATIVE docfields declared in
hr_settings.json (we own the doctype). On sites where the old field-creation
patches already ran, a Custom Field of the same fieldname still exists — delete
it BEFORE model sync adds the native docfield, so the two never coexist in the
meta (a duplicate fieldname breaks the form). The persisted value in tabSingles
is NOT touched by deleting the Custom Field, so the native field transparently
inherits whatever was already configured. No-op on sites that never had them
(e.g. a fresh install, or prod where the patch never ran)."""

import frappe

# The fields that moved from patch-created Custom Fields into native
# hr_settings.json. Keep in sync with the block added to the JSON field_order.
FIELDNAMES = (
	# DPDP (was dpdp_add_hr_settings)
	"dpdp_enable_access_logging",
	"dpdp_access_log_throttle_seconds",
	"dpdp_purge_max_per_run",
	"dpdp_breach_notification_recipients_role",
	# Consent / profile change (was add_consent_text_version_setting / add_profile_change_request_settings)
	"employee_consent_text_version",
	"self_editable_employee_fields",
	# Onboarding (was onboarding_compliance_lockdown / relocate_onboarding_hr_settings)
	"onboarding_settings_section",
	"onboarding_invite_validity_days",
	"onboarding_min_employment_age",
	# PF / ESI filing (was add_pf_esi_hr_settings)
	"pf_ecr_filing_window_days",
	"pf_ecr_exclude_employees_with_no_uan",
	"pf_edli_per_member_cap",
	"esi_filing_window_days",
	# Phase 6B-2 (was add_phase6b2_hr_settings)
	"form_24q_filing_window_days",
	"pt_filing_window_days",
	"lwf_filing_window_days",
	"responsible_person_default_designation",
	# Compliance Calendar (was add_compliance_calendar_hr_settings)
	"compliance_calendar_section_break",
	"compliance_calendar_upcoming_days",
	"compliance_calendar_escalation_days_after_due",
	"compliance_calendar_col_break",
	"send_compliance_calendar_daily_digest",
	"compliance_calendar_digest_recipients_role",
	"auto_link_filings_to_calendar",
	# Labour Code (was add_labour_code_hr_settings)
	"labour_code_section_break",
	"standing_orders_threshold_workers",
	"works_committee_threshold_workers",
	"grc_threshold_workers",
	"labour_code_col_break",
	"safety_committee_threshold_workers",
	"posh_ic_threshold_workers",
	"enable_uan_aadhaar_validation",
	"enable_monthly_labour_code_compliance_check",
)


def execute():
	if not frappe.db.exists("DocType", "HR Settings"):
		return
	dropped = 0
	for fieldname in FIELDNAMES:
		name = frappe.db.get_value("Custom Field", {"dt": "HR Settings", "fieldname": fieldname})
		if name:
			frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)
			dropped += 1
	if dropped:
		frappe.clear_cache(doctype="HR Settings")
		print(f"  Nativize HR Settings: dropped {dropped} stale Custom Field(s) → native docfields take over")
