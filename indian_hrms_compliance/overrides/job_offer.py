# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.utils import add_days, getdate


@frappe.whitelist()
def create_employee_from_job_offer(job_offer, additional_fields=None):
	"""Create an Employee from a Submitted + Accepted Job Offer.

	Pre-fills from Job Applicant (name, email, phone) and Job Offer
	(designation, company, dates). Required HR-supplied fields:
	date_of_birth, gender, date_of_joining. Optional: reports_to,
	bank fields, department, etc.

	On success the existing Employee.after_insert hook
	(update_job_applicant_and_offer) auto-accepts the linked Job Applicant
	and Job Offer.
	"""
	additional_fields = _coerce_dict(additional_fields)

	offer = frappe.get_doc("Job Offer", job_offer)
	if offer.status != "Accepted":
		frappe.throw(
			_("Job Offer must be in 'Accepted' status to promote to Employee. Current: {0}").format(
				offer.status
			)
		)
	if offer.docstatus != 1:
		frappe.throw(_("Job Offer must be Submitted before promoting to Employee."))

	if not offer.job_applicant:
		frappe.throw(_("Job Offer has no linked Job Applicant; cannot derive applicant details."))

	# Idempotency: if an Employee already exists for this Applicant, return it.
	existing = frappe.db.get_value("Employee", {"job_applicant": offer.job_applicant}, "name")
	if existing:
		return existing

	applicant = frappe.db.get_value(
		"Job Applicant",
		offer.job_applicant,
		["applicant_name", "email_id", "phone_number", "country"],
		as_dict=True,
	)
	if not applicant:
		frappe.throw(_("Linked Job Applicant {0} not found.").format(offer.job_applicant))

	first_name, last_name = _split_name(
		applicant.applicant_name,
		fallback_first=additional_fields.get("first_name"),
		fallback_last=additional_fields.get("last_name"),
	)

	joining = additional_fields.get("date_of_joining") or offer.offer_date
	if not joining:
		frappe.throw(_("Date of Joining is required."))

	# Compute scheduled_confirmation_date from joining + probation_days if both present.
	scheduled_conf = additional_fields.pop("scheduled_confirmation_date", None)
	probation_days = additional_fields.pop("probation_days", None)
	if not scheduled_conf and probation_days:
		try:
			scheduled_conf = add_days(getdate(joining), int(probation_days))
		except (TypeError, ValueError):
			pass

	payload = {
		"doctype": "Employee",
		"first_name": first_name,
		"last_name": last_name,
		"personal_email": applicant.email_id,
		"cell_number": applicant.phone_number,
		"company": offer.company,
		"designation": offer.designation,
		"date_of_joining": joining,
		"status": "Active",
		"job_applicant": offer.job_applicant,
	}
	if scheduled_conf:
		payload["scheduled_confirmation_date"] = scheduled_conf
		payload["confirmation_status"] = "Probation"

	# Caller-supplied fields overlay. Identity / company / applicant links not overridable.
	for key in ("doctype", "name", "company", "job_applicant"):
		additional_fields.pop(key, None)
	payload.update(additional_fields)

	if not payload.get("date_of_birth"):
		frappe.throw(_("Date of Birth is required to create an Employee."))
	if not payload.get("gender"):
		frappe.throw(_("Gender is required to create an Employee."))

	emp = frappe.get_doc(payload)
	emp.insert()  # apply caller's permissions normally
	return emp.name


def _coerce_dict(value):
	if value is None:
		return {}
	if isinstance(value, dict):
		return dict(value)
	if isinstance(value, str):
		try:
			parsed = frappe.parse_json(value)
		except Exception:
			frappe.throw(_("additional_fields could not be parsed as JSON."))
		return dict(parsed) if isinstance(parsed, dict) else {}
	frappe.throw(_("additional_fields must be a dict or JSON string."))


def _split_name(full_name, fallback_first=None, fallback_last=None):
	parts = (full_name or "").strip().split()
	if not parts:
		return (fallback_first or "New", fallback_last or "Employee")
	if len(parts) == 1:
		return (parts[0], fallback_last or "")
	return (parts[0], " ".join(parts[1:]))
