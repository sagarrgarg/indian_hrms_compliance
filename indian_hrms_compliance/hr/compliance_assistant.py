# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""HR Settings → Compliance Assistant tab.

Two operator actions:
  * apply_indian_statutory_defaults — re-applies the app's India-law-aligned
    defaults (statutory HR Settings, States/PT slabs, notification templates) by
    re-running the idempotent seeders.
  * run_ai_compliance_analysis — asks the AI Interface app to review the current
    HR configuration against Indian labour law and suggest retention measures,
    writing the result into HR Settings.ai_remarks / last_ran.
"""

import json

import frappe
from frappe import _
from frappe.utils import now, today

# Idempotent seeders re-run to (re)apply India-aligned defaults. Order mirrors
# the patch sequence; each is wrapped so one failure doesn't abort the rest.
STATUTORY_SEEDERS = (
	("Statutory HR Settings", "indian_hrms_compliance.patches.v15_0.seed_statutory_defaults"),
	("PF / ESI defaults", "indian_hrms_compliance.patches.v15_0.seed_pf_esi_hr_settings_defaults"),
	("Labour Code defaults", "indian_hrms_compliance.patches.v15_0.seed_labour_code_defaults"),
	("Exit & Gratuity defaults", "indian_hrms_compliance.patches.v15_0.seed_exit_settlement_defaults"),
	("Statutory return defaults", "indian_hrms_compliance.patches.v15_0.seed_phase6b2_defaults"),
	("Compliance calendar defaults", "indian_hrms_compliance.patches.v15_0.seed_compliance_calendar_defaults"),
	("General HR Settings defaults", "indian_hrms_compliance.patches.v15_0.seed_hr_settings_defaults"),
	("Indian States & PT slabs", "indian_hrms_compliance.patches.v15_0.seed_indian_states"),
	("Default notification templates", "indian_hrms_compliance.patches.v15_0.update_leave_notification_templates"),
)


@frappe.whitelist()
def apply_indian_statutory_defaults():
	"""Re-apply India-law-aligned HR defaults as of today. Idempotent."""
	frappe.only_for(("HR Manager", "System Manager"))

	results = []
	for label, module in STATUTORY_SEEDERS:
		try:
			frappe.get_attr(module + ".execute")()
			results.append({"step": label, "ok": True})
		except Exception:
			frappe.log_error(
				title=f"Apply statutory defaults: {label} failed",
				message=frappe.get_traceback(),
			)
			results.append({"step": label, "ok": False})

	applied_on = today()
	frappe.db.set_single_value("HR Settings", "statutory_defaults_applied_on", applied_on)
	frappe.db.commit()
	return {"applied_on": applied_on, "results": results}


# Governance "necessity" toggles and their recommended (compliant) values.
# These guard approval integrity and back-dating, so the baseline is ON.
RECOMMENDED_POLICY_SETTINGS = {
	"leave_approver_mandatory_in_leave_application": 1,
	"expense_approver_mandatory_in_expense_claim": 1,
	"restrict_backdated_leave_application": 1,
	"prevent_self_leave_approval": 1,
	"prevent_self_expense_approval": 1,
	"auto_assign_leave_policy_on_activation": 1,
}


@frappe.whitelist()
def apply_recommended_policy_settings():
	"""Hard-set the governance toggles to their recommended (ON) baseline."""
	frappe.only_for(("HR Manager", "System Manager"))

	hr = frappe.get_single("HR Settings")
	changed = []
	for field, value in RECOMMENDED_POLICY_SETTINGS.items():
		if not hr.meta.get_field(field):
			continue
		if hr.get(field) != value:
			changed.append(field)
		frappe.db.set_single_value("HR Settings", field, value)

	applied_on = today()
	frappe.db.set_single_value("HR Settings", "policy_settings_applied_on", applied_on)
	frappe.db.commit()
	return {"applied_on": applied_on, "changed": changed, "total": len(RECOMMENDED_POLICY_SETTINGS)}


@frappe.whitelist()
def run_ai_compliance_analysis():
	"""Ask the AI Interface app to review HR compliance + retention.

	Writes the response to HR Settings.ai_remarks and stamps last_ran.
	"""
	frappe.only_for(("HR Manager", "System Manager"))

	if "ai_interface" not in frappe.get_installed_apps():
		frappe.throw(_("The AI Interface app is not installed on this site."))

	from ai_interface.services.ai_client import call_ai

	prompt = _build_analysis_prompt()
	response = call_ai(
		prompt=prompt,
		calling_app="indian_hrms_compliance",
		function_type="Generation",
		sync=True,
	)

	ran_at = now()
	frappe.db.set_single_value("HR Settings", {"ai_remarks": response, "last_ran": ran_at})
	frappe.db.commit()
	return {"last_ran": ran_at}


def _build_analysis_prompt() -> str:
	"""Compact, grounded prompt: current config snapshot + instructions."""
	snapshot = _config_snapshot()
	as_of = today()
	return f"""You are a senior Indian HR & labour-law compliance advisor. Today's date is {as_of}.

If you have web access, research the latest applicable Indian central and state labour laws and statutory requirements as of {as_of} — including the Code on Wages 2019, the four Labour Codes, EPF, ESI, Professional Tax, Payment of Gratuity Act, Maternity Benefit Act, POSH Act, Shops & Establishments rules, and the DPDP Act 2023. If you do not have live web access, rely on your most current knowledge and say so.

Below is a JSON snapshot of an organisation's current HR configuration in this HRMS:

{json.dumps(snapshot, indent=2, default=str)}

Produce a concise Markdown report with exactly these two sections:

## Compliance Gaps
Bullet points. For each gap: what is missing or non-compliant, the specific law/section it relates to, and the concrete fix in this HRMS.

## Employee Retention
Bullet points with practical, India-context retention measures this organisation could adopt, prioritised by impact.

Be specific and actionable. Do not invent data that is not in the snapshot; if something cannot be determined from the snapshot, note it as "unknown / verify". Keep the whole report under 500 words."""


def _config_snapshot() -> dict:
	"""Bounded snapshot of statutory-relevant HR config for the AI prompt."""
	hr = frappe.get_single("HR Settings")
	statutory_fields = (
		"default_pt_state",
		"auto_create_gratuity_on_fnf",
		"auto_create_leave_encashment_on_fnf",
		"prevent_self_leave_approval",
		"restrict_backdated_leave_application",
		"dpdp_aadhaar_consent_required",
		"dpdp_data_retention_years",
		"default_probation_period_days",
		"leave_approver_mandatory_in_leave_application",
		"send_leave_notification",
		"leave_approval_notification_template",
		"leave_status_notification_template",
		"auto_assign_leave_policy_on_activation",
	)

	def count(doctype, filters=None):
		try:
			return frappe.db.count(doctype, filters or {})
		except Exception:
			return None

	companies = frappe.get_all("Company", fields=["name", "country"], limit_page_length=20)

	return {
		"as_of_date": today(),
		"companies": companies,
		"hr_settings": {f: hr.get(f) for f in statutory_fields if hr.meta.get_field(f)},
		"counts": {
			"active_employees": count("Employee", {"status": "Active"}),
			"leave_types": count("Leave Type"),
			"leave_policies": count("Leave Policy"),
			"leave_policy_assignments": count("Leave Policy Assignment", {"docstatus": 1}),
			"salary_structures": count("Salary Structure", {"docstatus": 1}),
			"indian_state_pt_slabs": count("Indian State PT Slab"),
			"gratuity_rules": count("Gratuity Rule"),
			"posh_internal_committees": count("POSH Internal Committee"),
		},
	}
