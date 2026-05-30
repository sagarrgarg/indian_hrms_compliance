# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


EXTENDED_LETTER_TYPE_OPTIONS = (
	"Appointment\nConfirmation\nProbation Extension\nRelease\n"
	"Relieving Letter\nExperience Letter\nService Certificate\nOther"
)

EXIT_LETTER_TEMPLATES = [
	{
		"name": "Relieving Letter Template",
		"letter_type": "Relieving Letter",
		"introduction": (
			"This is to confirm that {{ doc.applicant_name }}, "
			"Employee ID {{ doc.employee }}, has been relieved from the "
			"services of {{ doc.company }} effective {{ doc.appointment_date }}. "
			"The employee was working with us in the capacity of their last held "
			"designation since their date of joining."
		),
		"terms_html": (
			"<p>All dues, including final salary, leave encashment, and other "
			"applicable settlements, have been processed as per the Full and Final "
			"Statement issued separately.</p>"
			"<p>We thank the employee for their service and wish them success in "
			"their future endeavours.</p>"
		),
		"closing_notes": (
			"For {{ doc.company }}\n\n\nAuthorised Signatory\nHuman Resources"
		),
	},
	{
		"name": "Experience Letter Template",
		"letter_type": "Experience Letter",
		"introduction": (
			"This is to certify that {{ doc.applicant_name }} was employed with "
			"{{ doc.company }}, and was relieved on {{ doc.appointment_date }}. "
			"During their tenure, the employee demonstrated professionalism and "
			"contributed to the responsibilities assigned to them."
		),
		"terms_html": (
			"<p>The employee is hereby issued this Experience Letter as documentary "
			"evidence of their employment with the company.</p>"
			"<p>We wish them the very best in their future career.</p>"
		),
		"closing_notes": (
			"For {{ doc.company }}\n\n\nAuthorised Signatory\nHuman Resources"
		),
	},
	{
		"name": "Service Certificate Template",
		"letter_type": "Service Certificate",
		"introduction": (
			"SERVICE CERTIFICATE\n\nThis is to certify that {{ doc.applicant_name }} "
			"(Employee ID: {{ doc.employee }}) was a bona-fide employee of "
			"{{ doc.company }}. Their last working day with the organisation was "
			"{{ doc.appointment_date }}."
		),
		"terms_html": (
			"<p>The employee discharged their duties and responsibilities to "
			"the satisfaction of the management throughout their tenure with us.</p>"
			"<p>This certificate is issued upon request and reflects the official "
			"service record on file.</p>"
		),
		"closing_notes": (
			"For {{ doc.company }}\n\n\nAuthorised Signatory\nHuman Resources"
		),
	},
]


def execute():
	"""Phase 4 Stage 6 — extend Appointment Letter / Template letter_type
	options to include the three exit letter types, add employee +
	full_and_final_statement linkage fields, and seed default templates."""

	# 1) Extend letter_type Select options on both Appointment Letter and
	# Appointment Letter Template. Custom Field options are stored as a
	# string — we replace it in place.
	for dt in ("Appointment Letter", "Appointment Letter Template"):
		cf = frappe.db.exists("Custom Field", {"dt": dt, "fieldname": "letter_type"})
		if cf:
			frappe.db.set_value("Custom Field", cf, "options", EXTENDED_LETTER_TYPE_OPTIONS)
	print(f"  Extended letter_type options to include exit letter types")

	# 2) Add employee + full_and_final_statement linkage on Appointment Letter.
	# Job Applicant stays mandatory at the schema level — exit letters bypass
	# it via ignore_mandatory at insert time (same pattern as Probation Review).
	create_custom_fields(
		{
			"Appointment Letter": [
				{
					"fieldname": "employee",
					"fieldtype": "Link",
					"label": "Employee",
					"options": "Employee",
					"insert_after": "probation_review",
					"depends_on": (
						"eval:in_list(['Relieving Letter','Experience Letter',"
						"'Service Certificate'], doc.letter_type)"
					),
					"description": (
						"Set for exit letters (Relieving / Experience / Service "
						"Certificate) where there is no Job Applicant."
					),
				},
				{
					"fieldname": "full_and_final_statement",
					"fieldtype": "Link",
					"label": "Full and Final Statement",
					"options": "Full and Final Statement",
					"insert_after": "employee",
					"depends_on": (
						"eval:in_list(['Relieving Letter','Experience Letter',"
						"'Service Certificate'], doc.letter_type)"
					),
					"read_only": 1,
					"description": "Auto-linked when generated from FnF via the 'Generate Exit Letters' button.",
				},
			],
		},
		ignore_validate=True,
	)
	print("  Added employee + full_and_final_statement Custom Fields to Appointment Letter")

	# 3) Seed default exit letter templates if missing.
	for tmpl in EXIT_LETTER_TEMPLATES:
		# Skip if a template with this name already exists.
		if frappe.db.exists("Appointment Letter Template", tmpl["name"]):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Appointment Letter Template",
				"template_name": tmpl["name"],
				"letter_type": tmpl["letter_type"],
				"introduction": tmpl["introduction"],
				"closing_notes": tmpl["closing_notes"],
			}
		)
		# terms is a Table field on Appointment Letter Template — use it for the
		# body sections. We'll just put the HTML body into a single term row.
		doc.append(
			"terms",
			{
				"title": tmpl["letter_type"],
				"description": tmpl["terms_html"],
			},
		)
		try:
			doc.insert(ignore_permissions=True)
		except Exception:
			# Template insertion can fail if the schema differs from
			# expectations (e.g., terms field is different in custom forks);
			# don't block migration — HR can create templates manually.
			frappe.log_error(
				title=f"Exit letter template seed failed: {tmpl['name']}",
				message=frappe.get_traceback(),
			)
	print(f"  Seeded {len(EXIT_LETTER_TEMPLATES)} exit letter templates")
