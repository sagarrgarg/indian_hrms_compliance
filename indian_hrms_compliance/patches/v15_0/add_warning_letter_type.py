# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe


# Adds Warning Letter to the existing letter_type Select on Appointment
# Letter + Template. Same in-place update pattern as add_exit_letter_types.
EXTENDED_LETTER_TYPE_OPTIONS = (
	"Appointment\nConfirmation\nProbation Extension\nRelease\n"
	"Relieving Letter\nExperience Letter\nService Certificate\n"
	"Warning Letter\nOther"
)


WARNING_LETTER_TEMPLATE = {
	"name": "Warning Letter Template",
	"letter_type": "Warning Letter",
	"introduction": (
		"Dear {{ doc.applicant_name }},\n\n"
		"This letter is in reference to the disciplinary proceedings initiated "
		"against you by {{ doc.company }}. Following the inquiry, the "
		"management has decided to issue you a formal Warning Letter."
	),
	"terms_html": (
		"<p><strong>The findings against you have been recorded in the "
		"corresponding Disciplinary Action record.</strong></p>"
		"<p>You are hereby advised to ensure that no such incident is repeated "
		"in the future. Any further misconduct may attract stricter disciplinary "
		"action up to and including termination of employment as per the "
		"company's Standing Orders and Code of Conduct.</p>"
		"<p>You are required to acknowledge this letter in writing within 7 days "
		"of issuance.</p>"
	),
	"closing_notes": (
		"For {{ doc.company }}\n\n\nAuthorised Signatory\nHuman Resources"
	),
}


def execute():
	"""Phase 5 Stage 4 — Warning Letter type + seeded template."""
	# Update letter_type options on both doctypes' Custom Fields.
	for dt in ("Appointment Letter", "Appointment Letter Template"):
		cf = frappe.db.exists("Custom Field", {"dt": dt, "fieldname": "letter_type"})
		if cf:
			frappe.db.set_value("Custom Field", cf, "options", EXTENDED_LETTER_TYPE_OPTIONS)
	print("  Extended letter_type options with 'Warning Letter'")

	# Seed the template.
	if frappe.db.exists("Appointment Letter Template", WARNING_LETTER_TEMPLATE["name"]):
		print("  Warning Letter Template already exists — skipped")
		return
	doc = frappe.get_doc(
		{
			"doctype": "Appointment Letter Template",
			"template_name": WARNING_LETTER_TEMPLATE["name"],
			"letter_type": WARNING_LETTER_TEMPLATE["letter_type"],
			"introduction": WARNING_LETTER_TEMPLATE["introduction"],
			"closing_notes": WARNING_LETTER_TEMPLATE["closing_notes"],
		}
	)
	doc.append(
		"terms",
		{
			"title": WARNING_LETTER_TEMPLATE["letter_type"],
			"description": WARNING_LETTER_TEMPLATE["terms_html"],
		},
	)
	try:
		doc.insert(ignore_permissions=True)
		print("  Seeded Warning Letter Template")
	except Exception:
		frappe.log_error(
			title="Warning Letter Template seed failed",
			message=frappe.get_traceback(),
		)
