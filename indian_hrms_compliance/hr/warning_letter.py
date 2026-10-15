# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Warning letters to employees.

A warning letter is an Appointment Letter with letter_type "Warning Letter",
linked to the Employee, printed with the "Warning Letter" print format. Issued
from the Employee's Warnings tab, or by a Disciplinary Action outcome."""

import frappe
from frappe import _
from frappe.utils import formatdate, getdate, today

WARNING_TEMPLATE = "Warning Letter Template"
WARNING_LEVELS = ("First Warning", "Second Warning", "Final Warning")
WARNING_CATEGORIES = ("Attendance", "Misconduct", "Performance", "Policy")


def create_warning_letter(
	employee: str,
	letter_date=None,
	warning_level: str | None = None,
	warning_category: str | None = None,
	incident_date=None,
	incident_details: str | None = None,
	ignore_permissions: bool = False,
) -> str:
	"""Create (unsubmitted) the warning letter and return its name."""
	if warning_level and warning_level not in WARNING_LEVELS:
		frappe.throw(_("Invalid Warning Level {0}").format(warning_level))
	if warning_category and warning_category not in WARNING_CATEGORIES:
		frappe.throw(_("Invalid Reason {0}").format(warning_category))
	if not frappe.db.exists("Appointment Letter Template", WARNING_TEMPLATE):
		frappe.throw(_("{0} is missing. Run bench migrate to seed it.").format(WARNING_TEMPLATE))

	emp = frappe.db.get_value("Employee", employee, ["employee_name", "company"], as_dict=True)
	if not emp:
		frappe.throw(_("Employee {0} not found").format(employee))

	template = frappe.get_doc("Appointment Letter Template", WARNING_TEMPLATE)
	letter = frappe.new_doc("Appointment Letter")
	letter.update(
		{
			"letter_type": "Warning Letter",
			"employee": employee,
			"applicant_name": emp.employee_name,
			"company": emp.company,
			"appointment_date": getdate(letter_date or today()),
			"appointment_letter_template": WARNING_TEMPLATE,
			"warning_level": warning_level,
			"warning_category": warning_category,
			"incident_date": getdate(incident_date) if incident_date else None,
			"incident_details": incident_details,
		}
	)
	letter.introduction = _introduction(letter, template)
	letter.closing_notes = frappe.render_template(template.closing_notes or "", {"doc": letter})
	for t in template.terms:
		letter.append("terms", {"title": t.title, "description": t.description})

	# Appointment Letter needs a Job Applicant; a letter to an employee has none.
	letter.flags.ignore_mandatory = True
	letter.insert(ignore_permissions=ignore_permissions)
	return letter.name


def _introduction(letter, template) -> str:
	if not (letter.incident_details or letter.warning_category):
		return frappe.render_template(template.introduction or "", {"doc": letter})
	when = _(" on {0}").format(formatdate(letter.incident_date)) if letter.incident_date else ""
	about = _(" regarding {0}").format(letter.warning_category.lower()) if letter.warning_category else ""
	text = _("Dear {0},").format(letter.applicant_name) + "\n\n"
	text += _("It has come to the notice of the management{0}{1}:").format(about, when)
	if letter.incident_details:
		text += "\n\n" + letter.incident_details.strip()
	text += "\n\n" + _(
		"This is not acceptable under the company's rules of conduct, and this letter is "
		"issued to you as a {0}."
	).format((letter.warning_level or _("Warning")).lower())
	return text


@frappe.whitelist()
def issue_warning_letter(
	employee: str,
	letter_date=None,
	warning_level: str | None = None,
	warning_category: str | None = None,
	incident_date=None,
	incident_details: str | None = None,
) -> str:
	frappe.has_permission("Appointment Letter", "create", throw=True)
	return create_warning_letter(
		employee, letter_date, warning_level, warning_category, incident_date, incident_details
	)


@frappe.whitelist()
def get_employee_warnings(employee: str) -> dict:
	"""Warning letters and open disciplinary actions for the Warnings tab."""
	frappe.has_permission("Employee", "read", doc=employee, throw=True)
	letters = []
	if frappe.has_permission("Appointment Letter", "read"):
		letters = frappe.get_all(
			"Appointment Letter",
			filters={"employee": employee, "letter_type": "Warning Letter"},
			fields=[
				"name",
				"appointment_date",
				"warning_level",
				"warning_category",
				"incident_date",
				"incident_details",
			],
			order_by="appointment_date desc, creation desc",
		)
	actions = []
	if frappe.has_permission("Disciplinary Action", "read"):
		actions = frappe.get_all(
			"Disciplinary Action",
			filters={"employee": employee},
			fields=["name", "action_date", "nature_of_misconduct", "workflow_state", "outcome"],
			order_by="action_date desc, creation desc",
		)
	return {
		"letters": letters,
		"actions": actions,
		"can_issue": bool(frappe.has_permission("Appointment Letter", "create")),
	}
