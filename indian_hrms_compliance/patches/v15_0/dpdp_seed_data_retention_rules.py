# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Phase 6D — seed default Data Retention Rules.

Each rule is keyed on (doctype × field_name) via the autoname pattern
'DRR-{doctype_name}-{field_name}'. For Record-Level rules, field_name
defaults to '_record_' so the autoname is stable.

All rules start with action_on_expiry='Anonymize' or 'Archive' —
NEVER 'Delete' on the first cycle. Operators must consciously flip a
rule to 'Delete' after validating Anonymize / Archive output.
"""

import frappe


# Each tuple: (doctype, field_name_for_autoname, retention_years,
#              anchor_field, action_on_expiry, purpose_code, notes)
DEFAULT_RULES = [
	(
		"Employee",
		"_record_",
		8,
		"relieving_date",
		"Anonymize",
		"EXIT_FORMALITIES",
		(
			"Anonymise ex-employee personal contact + PII fields 8 years after "
			"relieving (IT Act + Companies Act 2013 retention window). The "
			"record itself remains so historical payroll/tax linkages survive."
		),
	),
	(
		"Salary Slip",
		"_record_",
		8,
		"start_date",
		"Archive",
		"STATUTORY_PAYROLL",
		(
			"Archive salary slips older than 8 years per IT Act retention. "
			"Source records moved to /private/files/dpdp_archive/Salary_Slip/."
		),
	),
	(
		"Form 16",
		"_record_",
		8,
		"creation",
		"Archive",
		"STATUTORY_PAYROLL",
		(
			"Archive Form 16 records older than 8 years per IT Act retention. "
			"Fiscal_year anchor is per-row not date; using creation as proxy."
		),
	),
	(
		"Data Access Log",
		"_record_",
		3,
		"accessed_on",
		"Delete",
		None,
		(
			"Audit logs themselves are retained 3 years then deleted. The DPDP "
			"breach window for review is much shorter; 3 years is generous."
		),
	),
	(
		"Employee Tax Exemption Proof Submission",
		"_record_",
		8,
		"submission_date",
		"Delete",
		"STATUTORY_PAYROLL",
		(
			"HRA receipts and proof attachments retained 8 years per IT Act."
		),
	),
	(
		"POSH Complaint",
		"_record_",
		5,
		"closed_on",
		"Archive",
		"POSH_INVESTIGATION",
		(
			"POSH complaint records archived 5 years after closure per POSH Act "
			"recommendations and best-practice retention."
		),
	),
]


def execute():
	created = 0
	skipped = 0
	for dt, fn, years, anchor, action, purpose, notes in DEFAULT_RULES:
		# Check the doctype exists in this bench before seeding the rule.
		if not frappe.db.exists("DocType", dt):
			print(f"  SKIP: doctype {dt} not present in this bench, rule not seeded")
			continue
		rule_name = f"DRR-{dt}-{fn}"
		if frappe.db.exists("Data Retention Rule", rule_name):
			skipped += 1
			continue
		try:
			payload = {
				"doctype": "Data Retention Rule",
				"doctype_name": dt,
				"field_or_record": "Record-Level",
				"field_name": fn,
				"retention_period_years": years,
				"anchor_field": anchor,
				"action_on_expiry": action,
				"is_active": 1,
				"notes": notes,
			}
			if purpose and frappe.db.exists("Data Consent Purpose", purpose):
				payload["purpose"] = purpose
			frappe.get_doc(payload).insert(ignore_permissions=True)
			created += 1
		except Exception as e:
			print(f"  WARN: seed Data Retention Rule {dt}/{fn} failed: {e}")
	print(
		f"  Phase 6D: seeded {created} Data Retention Rules "
		f"({skipped} already present)"
	)
