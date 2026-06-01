# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Self-service onboarding intake.

A candidate fills the public/invite Web Form (guest), which lands here as an
Employee Onboarding Application in 'Pending Verification'. HR verifies, then
'Convert to Employee' pre-fills the New Employee Setup page (reusing the
setup_new_employee orchestration) and stamps this application 'Converted'.
"""

import hmac
import re
from hashlib import sha256

import frappe
from frappe import _
from frappe.model.document import Document

HR_ROLES = ("HR Manager", "HR User", "System Manager")

# Fields safe to hand to the New Employee Setup page (no HR-review/internal fields).
SETUP_FIELDS = (
	"first_name", "middle_name", "last_name", "date_of_birth", "gender",
	"pan_number", "aadhaar_last_4", "uan_number", "bank_name", "bank_ac_no",
	"ifsc_code",
)


class EmployeeOnboardingApplication(Document):
	def validate(self):
		self._apply_invite_token()
		self._normalise()

	def before_insert(self):
		# Guest submissions must carry consent; HR-created drafts may skip it.
		if self.status != "Draft" and not self.dpdp_consent:
			frappe.throw(_("Please tick the consent box to submit your details."))

	def _normalise(self):
		if self.pan_number:
			self.pan_number = self.pan_number.strip().upper()
		if self.aadhaar_last_4:
			digits = re.sub(r"\D", "", self.aadhaar_last_4)
			# Never store more than the last 4 — defensive against a full Aadhaar paste.
			self.aadhaar_last_4 = digits[-4:]
		if self.ifsc_code:
			self.ifsc_code = self.ifsc_code.strip().upper()

	def _apply_invite_token(self):
		"""If the submission carried a valid signed invite token, flag it as
		invited and record the email HR issued it to. An invalid/absent token
		just means this is a plain public submission — not an error."""
		if not self.invite_token or self.invited:
			return
		email = _verify_invite_token(self.invite_token)
		if email:
			self.invited = 1
			self.invite_email = email


# --------------------------------------------------------------- invite tokens
def _invite_secret() -> str:
	conf = frappe.local.conf
	return conf.get("onboarding_invite_secret") or conf.get("encryption_key") or "indian_hrms_compliance"


def _sign(email: str) -> str:
	return hmac.new(_invite_secret().encode(), email.lower().encode(), sha256).hexdigest()[:32]


def _verify_invite_token(token: str):
	"""Token format 'email|sig'. Returns the email if the signature matches."""
	try:
		email, sig = token.rsplit("|", 1)
	except (ValueError, AttributeError):
		return None
	return email if hmac.compare_digest(sig, _sign(email)) else None


@frappe.whitelist()
def generate_invite_link(email: str) -> dict:
	"""HR-only: produce a signed, shareable onboarding link for a candidate."""
	frappe.only_for(HR_ROLES)
	email = (email or "").strip().lower()
	if not email:
		frappe.throw(_("Candidate email is required to generate an invite link."))
	token = f"{email}|{_sign(email)}"
	url = frappe.utils.get_url(f"/onboarding/new?invite_token={frappe.utils.quote(token)}")
	return {"email": email, "url": url}


# --------------------------------------------------------------- convert glue
@frappe.whitelist()
def get_application_for_setup(name: str) -> dict:
	"""HR-only: payload the New Employee Setup page pre-fills from."""
	frappe.only_for(HR_ROLES)
	doc = frappe.get_doc("Employee Onboarding Application", name)
	if doc.status == "Converted":
		frappe.throw(_("This application has already been converted to Employee {0}.").format(doc.linked_employee))

	data = {f: doc.get(f) for f in SETUP_FIELDS}
	data["onboarding_application"] = doc.name
	data["company"] = doc.target_company
	data["department"] = doc.target_department
	data["designation"] = doc.target_designation
	data["employment_type"] = doc.employment_type
	data["user_email"] = doc.personal_email
	return data


def mark_converted(application: str, employee: str):
	"""Stamp the application Converted, link the created Employee, and carry over
	the application-only fields the setup page doesn't show (emergency contact).
	Called by setup_new_employee when launched from an application."""
	if not application:
		return
	if not frappe.db.exists("Employee Onboarding Application", application):
		return

	app = frappe.db.get_value(
		"Employee Onboarding Application",
		application,
		["emergency_contact_name", "emergency_contact_relation", "emergency_contact_phone", "current_address"],
		as_dict=True,
	)
	emp_updates = {}
	if app.emergency_contact_name:
		emp_updates["person_to_be_contacted"] = app.emergency_contact_name
	if app.emergency_contact_relation:
		emp_updates["relation"] = app.emergency_contact_relation
	if app.emergency_contact_phone:
		emp_updates["emergency_phone_number"] = app.emergency_contact_phone
	if app.current_address:
		emp_updates["current_address"] = app.current_address
	if emp_updates:
		frappe.db.set_value("Employee", employee, emp_updates)

	frappe.db.set_value(
		"Employee Onboarding Application",
		application,
		{
			"status": "Converted",
			"linked_employee": employee,
			"verified_by": frappe.session.user,
		},
	)
