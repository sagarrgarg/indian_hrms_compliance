# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Phase 6D — seed HR Settings DPDP defaults + 8 Data Consent Purposes.

HR Settings is a Single; JSON `default:` only fires on initial row insert,
so explicit set_single_value calls are required for upgrades.

The 8 seeded Data Consent Purposes are the bare minimum for an Indian
HR rollout. HR can add more via the master.
"""

import frappe


DPDP_HR_SETTINGS_DEFAULTS = {
	"dpdp_enable_access_logging": 1,
	"dpdp_access_log_throttle_seconds": 3600,
	"dpdp_purge_max_per_run": 50,
	"dpdp_breach_notification_recipients_role": "HR Manager",
}


DEFAULT_NOTICE_TEMPLATE = (
	"### Personal Data Processing Notice\n\n"
	"**Employee:** {{ employee_name }}  \n"
	"**Company:** {{ company }}  \n"
	"**Purpose:** {{ purpose_name }}\n\n"
	"By giving your consent, you authorise the Company to collect, store, "
	"and process your personal data for the purpose stated above, in "
	"accordance with the Digital Personal Data Protection Act, 2023.\n\n"
	"You have the right to:\n"
	"- Access a summary of your personal data and how it is processed\n"
	"- Request correction or completion of inaccurate data\n"
	"- Withdraw this consent at any time (subject to statutory retention)\n"
	"- Nominate a person to exercise these rights on your behalf\n"
	"- File a grievance with the Data Protection Board of India\n"
)


DPDP_PURPOSES = [
	{
		"purpose_code": "STATUTORY_PAYROLL",
		"purpose_name": "Statutory Payroll Processing",
		"lawful_basis": "Statutory Obligation",
		"retention_period_years": 8,
		"requires_explicit_consent": 0,
		"description": "PF/ESI/PT/TDS calculations and statutory filings.",
		"data_categories": "salary, pan_number, uan_number, esic_ip_number, bank_ac_no, ifsc_code",
		"withdrawal_consequences": (
			"Payroll cannot be processed without statutory IDs. Withdrawal would "
			"breach the Company's obligations under the EPF & MP Act, ESI Act, "
			"and Income Tax Act."
		),
	},
	{
		"purpose_code": "HEALTH_INSURANCE_ENROL",
		"purpose_name": "Health Insurance Enrolment",
		"lawful_basis": "Consent",
		"retention_period_years": 3,
		"requires_explicit_consent": 1,
		"description": "Enrolment of employee + dependants in group medical insurance.",
		"data_categories": "name, dob, dependants, pre_existing_conditions, blood_group",
		"withdrawal_consequences": "Insurance cover lapses on next renewal cycle.",
	},
	{
		"purpose_code": "BACKGROUND_CHECK",
		"purpose_name": "Background Verification",
		"lawful_basis": "Consent",
		"retention_period_years": 3,
		"requires_explicit_consent": 1,
		"description": "Pre/post-hire BGV — employment, education, criminal record.",
		"data_categories": "prior_employers, education_certificates, address_history, identity_documents",
		"withdrawal_consequences": (
			"Withdrawal during BGV terminates the verification; offer may be rescinded."
		),
	},
	{
		"purpose_code": "PERFORMANCE_MGMT",
		"purpose_name": "Performance Management",
		"lawful_basis": "Legitimate Interest",
		"retention_period_years": 7,
		"requires_explicit_consent": 0,
		"description": "Appraisals, goals, KRA tracking, 360-degree reviews.",
		"data_categories": "appraisal_ratings, goals, feedback, KRA_scores",
		"withdrawal_consequences": (
			"Performance management is a legitimate-interest basis; explicit "
			"consent withdrawal does not stop processing for fairness of HR decisions."
		),
	},
	{
		"purpose_code": "POSH_INVESTIGATION",
		"purpose_name": "POSH Investigation",
		"lawful_basis": "Statutory Obligation",
		"retention_period_years": 5,
		"requires_explicit_consent": 0,
		"description": "Sexual harassment complaint investigation under POSH Act 2013.",
		"data_categories": "complaint_text, witness_statements, evidence_files, IC_findings",
		"withdrawal_consequences": (
			"POSH investigations proceed under statutory obligation; withdrawal "
			"does not stop the inquiry. Records retained 5 years after closure."
		),
	},
	{
		"purpose_code": "EXIT_FORMALITIES",
		"purpose_name": "Exit & Full-and-Final Settlement",
		"lawful_basis": "Statutory Obligation",
		"retention_period_years": 8,
		"requires_explicit_consent": 0,
		"description": "Resignation, no-dues, FnF, Form 16, exit letters.",
		"data_categories": "relieving_date, fnf_components, tds_on_fnf, bank_ac_no",
		"withdrawal_consequences": (
			"Exit processing under contract + statutory obligations; cannot be "
			"withdrawn until 8-year IT/Companies Act window expires."
		),
	},
	{
		"purpose_code": "PAYROLL_BANK_DETAILS",
		"purpose_name": "Payroll Bank Account Details",
		"lawful_basis": "Contract Performance",
		"retention_period_years": 8,
		"requires_explicit_consent": 0,
		"description": "Bank account for direct salary credit per employment contract.",
		"data_categories": "bank_ac_no, ifsc_code, bank_name",
		"withdrawal_consequences": (
			"Salary cannot be credited without an active bank account on file. "
			"Withdrawal requires you to provide an alternative payout mechanism."
		),
	},
	{
		"purpose_code": "AADHAAR_VERIFICATION",
		"purpose_name": "Aadhaar Verification (UIDAI)",
		"lawful_basis": "Consent",
		"retention_period_years": 3,
		"requires_explicit_consent": 1,
		"description": (
			"Verification of identity via UIDAI. Only the last 4 digits of "
			"Aadhaar are stored; full Aadhaar is never persisted."
		),
		"data_categories": "aadhaar_last_4, name_per_uidai, dob_per_uidai",
		"withdrawal_consequences": (
			"PF / EPS / NPS / income-tax linkages that require Aadhaar will be "
			"suspended on withdrawal until alternative documentation is provided."
		),
	},
]


def execute():
	# 1. HR Settings defaults.
	for field, value in DPDP_HR_SETTINGS_DEFAULTS.items():
		try:
			frappe.db.set_single_value("HR Settings", field, value)
		except Exception as e:
			print(f"  WARN: HR Settings {field} seed failed: {e}")
	print(f"  Phase 6D: seeded {len(DPDP_HR_SETTINGS_DEFAULTS)} HR Settings defaults")

	# 2. Data Consent Purposes — idempotent, only insert if missing.
	created = 0
	skipped = 0
	for p in DPDP_PURPOSES:
		if frappe.db.exists("Data Consent Purpose", p["purpose_code"]):
			skipped += 1
			continue
		try:
			payload = dict(p)
			payload["doctype"] = "Data Consent Purpose"
			payload["is_active"] = 1
			if not payload.get("notice_template"):
				payload["notice_template"] = DEFAULT_NOTICE_TEMPLATE
			doc = frappe.get_doc(payload)
			doc.insert(ignore_permissions=True)
			created += 1
		except Exception as e:
			print(f"  WARN: seed Data Consent Purpose {p['purpose_code']} failed: {e}")
	print(
		f"  Phase 6D: seeded {created} Data Consent Purposes "
		f"({skipped} already present)"
	)
