# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Self-service onboarding intake.

A candidate fills the public/invite Web Form (guest), which lands here as an
Employee Onboarding Application in 'Pending Verification'. HR verifies, then
'Convert to Employee' pre-fills the New Employee Setup page (reusing the
setup_new_employee orchestration) and stamps this application 'Converted'.

This module is the compliance-lock surface for onboarding:
  * Statutory IDs are format-validated at insert (PAN, IFSC, UAN, Aadhaar last-4).
  * Date-of-birth is range-checked against the minimum employment age.
  * DPDP consent is mandatory for guest submissions and the timestamp + source
    IP + consent-text version are stamped on insert (audit trail).
  * Invite tokens are HMAC-signed AND time-bound (default 30 days).
  * Duplicates are caught before insert; guest endpoint is rate-limited.
  * Convert-to-Employee writes a Data Consent record, re-attaches uploaded docs
    to the Employee and lifts the photo to Employee.image — closing the loop.
"""

import base64
import hmac
import json
import re
from hashlib import sha256

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import (
	add_days,
	cint,
	date_diff,
	get_datetime,
	getdate,
	now_datetime,
)

HR_ROLES = ("HR Manager", "HR User", "System Manager")

# Reuse the canonical regexes that the Employee master enforces so the
# onboarding intake and the Employee doctype can never disagree.
from indian_hrms_compliance.overrides.employee_master import (
	AADHAAR_FULL_RE,
	AADHAAR_LAST4_RE,
	IFSC_RE,
	PAN_RE,
	UAN_RE,
	verhoeff_check_aadhaar,
)

MOBILE_RE = re.compile(r"^(\+?91)?[6-9]\d{9}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

INVITE_DEFAULT_VALIDITY_DAYS = 30
MIN_EMPLOYMENT_AGE_DEFAULT = 14  # Child Labour (Prohibition and Regulation) Act, 1986
MAX_EMPLOYMENT_AGE = 100

# Default brand palette for the public onboarding form — saffron -> terracotta,
# matching the product's app icon / splash (frontend/branding). A company may
# override these via Company.onboarding_primary_color / _secondary_color.
ONBOARDING_DEFAULT_PRIMARY = "#E16A2C"  # terracotta
ONBOARDING_DEFAULT_SECONDARY = "#F4A04A"  # saffron


def _onboarding_theme(company: str | None) -> dict:
	"""Resolve the onboarding form palette for a company, falling back to the
	brand default when the company is blank or hasn't set custom colours."""
	primary = secondary = None
	if company and frappe.db.exists("Company", company):
		primary, secondary = frappe.db.get_value(
			"Company", company, ["onboarding_primary_color", "onboarding_secondary_color"]
		) or (None, None)
	return {
		"primary_color": primary or ONBOARDING_DEFAULT_PRIMARY,
		"secondary_color": secondary or ONBOARDING_DEFAULT_SECONDARY,
	}

# Documents every candidate MUST upload before an onboarding submission is
# accepted. "Previous Payslip" is additionally required unless is_fresher.
REQUIRED_DOCUMENT_TYPES = ("PAN Card", "Aadhaar Card")
PAYSLIP_DOCUMENT_TYPE = "Previous Payslip"
# Required ONLY when HR attached an offer letter for this candidate to download +
# sign via the invite link (self.offer_letter is set) — if they were sent a letter
# to sign, they must return the signed copy. Plain/open submissions skip it.
SIGNED_OFFER_LETTER_DOCUMENT_TYPE = "Signed Offer Letter"

# Fields safe to hand to the New Employee Setup page (no HR-review/internal fields).
SETUP_FIELDS = (
	"first_name", "middle_name", "last_name", "date_of_birth", "gender",
	"pan_number", "aadhaar_number", "aadhaar_last_4", "uan_number",
	"bank_name", "bank_ac_no", "ifsc_code",
)


class EmployeeOnboardingApplication(Document):
	def validate(self):
		self._apply_invite_token()
		self._normalise()
		self._validate_statutory_ids()
		self._validate_dob()
		self._validate_required_documents()
		self._validate_status_transitions()

	def on_update(self):
		self._link_document_files()

	def _link_document_files(self):
		"""Anchor each uploaded document File to THIS application.

		Candidate/web-form uploads land as PRIVATE files, and some arrive with no
		attached_to link (orphans) — typically the PAN/Aadhaar a guest uploads
		into the documents grid. A private orphan file is readable only by its
		owner + System Manager, so an HR User/Manager verifying the application
		gets a permission error opening it. Linking the file to the application
		makes it inherit the application's read permission.

		Only orphans are claimed: a file already attached elsewhere (e.g. cloned
		onto the Employee on conversion, or still held by an invite Draft that
		after_insert will move) is left untouched."""
		if not self.name:
			return
		for row in self.documents or []:
			if not row.document:
				continue
			for f in frappe.get_all(
				"File",
				filters={"file_url": row.document},
				fields=["name", "attached_to_doctype", "attached_to_name"],
			):
				if f.attached_to_doctype or f.attached_to_name:
					continue  # already linked somewhere — don't steal it
				frappe.db.set_value(
					"File",
					f.name,
					{"attached_to_doctype": self.doctype, "attached_to_name": self.name},
					update_modified=False,
				)

	def before_insert(self):
		# Guest submissions must carry consent; HR-created drafts may skip it.
		if self.status != "Draft" and not self.dpdp_consent:
			frappe.throw(_("Please tick the consent box to submit your details."))

		if self.dpdp_consent and not self.consent_timestamp:
			self.consent_timestamp = now_datetime()
			# frappe.local.request_ip is set on web requests; falls back to empty on console-created docs.
			self.consent_ip = getattr(frappe.local, "request_ip", None) or ""
			# DPDP evidence trail: IP + User-Agent + timestamp + consent version.
			# (A browser can never expose the device MAC address — UA is the
			# strongest device signature legitimately available to a website.)
			self.consent_user_agent = _request_user_agent()

		# Pin the consent text version that was shown — bumping HR Settings later
		# does NOT retroactively change what this row was captured under.
		if not self.consent_text_version:
			self.consent_text_version = (
				frappe.db.get_single_value("HR Settings", "employee_consent_text_version")
				or "1.0"
			)

		self.submitted_on = self.submitted_on or now_datetime()
		self._check_duplicates()

	def _normalise(self):
		if self.pan_number:
			self.pan_number = self.pan_number.strip().upper()
		if self.aadhaar_number:
			# Strip spaces/dashes/etc — UIDAI prints it as 4-4-4 with spaces.
			self.aadhaar_number = re.sub(r"\D", "", self.aadhaar_number)
			# The legacy last-4 column is auto-derived from the full number, so
			# audits and existing reports keep working without rewiring.
			self.aadhaar_last_4 = self.aadhaar_number[-4:]
		elif self.aadhaar_last_4:
			digits = re.sub(r"\D", "", self.aadhaar_last_4)
			self.aadhaar_last_4 = digits[-4:]
		if self.ifsc_code:
			self.ifsc_code = self.ifsc_code.strip().upper()
		if self.uan_number:
			self.uan_number = re.sub(r"\D", "", self.uan_number)
		if self.mobile_no:
			# strip spaces/dashes but keep a leading +
			self.mobile_no = re.sub(r"[^\d+]", "", self.mobile_no)
		if self.personal_email:
			self.personal_email = self.personal_email.strip().lower()
		# Permanent address mirrors current when the candidate opts in. Enforced
		# server-side so it stays correct even if the client toggle was bypassed.
		if self.same_as_current_address:
			self.permanent_address = self.current_address

		# The explicit "Fresher / Already an Employee" choice drives the internal
		# is_fresher flag (which gates the Previous Payslip requirement). Only
		# override when a choice was actually made, so HR drafts and direct
		# programmatic sets keep whatever is_fresher value they were given.
		if self.prior_employment:
			self.is_fresher = 1 if self.prior_employment == "Fresher" else 0

	def _validate_statutory_ids(self):
		# These are HARD locks: the data flows directly into Employee + payroll
		# filings, so we mirror what Employee.validate would enforce post-conversion.
		if self.pan_number and not PAN_RE.match(self.pan_number):
			frappe.throw(_("PAN must match format ABCDE1234F (5 letters, 4 digits, 1 letter)."))
		if self.uan_number and not UAN_RE.match(self.uan_number):
			frappe.throw(_("UAN must be exactly 12 digits."))
		if self.ifsc_code and not IFSC_RE.match(self.ifsc_code):
			frappe.throw(_("IFSC must be 4 letters + '0' + 6 alphanumeric (e.g., HDFC0001234)."))
		# Full Aadhaar takes precedence; last-4 is auto-derived from it.
		if self.aadhaar_number:
			if not AADHAAR_FULL_RE.match(self.aadhaar_number):
				frappe.throw(_("Aadhaar must be exactly 12 digits and start with 2-9."))
			if not verhoeff_check_aadhaar(self.aadhaar_number):
				frappe.throw(_("Aadhaar checksum failed — please re-check the number on the card."))
		elif self.aadhaar_last_4 and not AADHAAR_LAST4_RE.match(self.aadhaar_last_4):
			frappe.throw(_("Aadhaar (last 4 digits) must be exactly 4 digits."))
		if self.mobile_no and not MOBILE_RE.match(self.mobile_no):
			frappe.throw(_("Mobile must be a 10-digit Indian number (starting 6/7/8/9), optionally prefixed +91."))
		if self.personal_email and not EMAIL_RE.match(self.personal_email):
			frappe.throw(_("Email format looks invalid."))
		if self.emergency_contact_phone and not MOBILE_RE.match(re.sub(r"[^\d+]", "", self.emergency_contact_phone)):
			frappe.msgprint(
				_("Emergency contact phone doesn't look like a 10-digit Indian mobile — please double-check."),
				indicator="orange",
				title=_("Emergency Contact"),
			)

	def _validate_dob(self):
		if not self.date_of_birth:
			return
		dob = getdate(self.date_of_birth)
		today = getdate()
		if dob > today:
			frappe.throw(_("Date of Birth cannot be in the future."))
		age_years = date_diff(today, dob) // 365
		min_age = cint(frappe.db.get_single_value("HR Settings", "onboarding_min_employment_age")) or MIN_EMPLOYMENT_AGE_DEFAULT
		if age_years < min_age:
			frappe.throw(
				_("Candidate appears to be under {0} years old — onboarding is blocked (Child Labour Act).").format(min_age)
			)
		if age_years < 18:
			frappe.msgprint(
				_("Candidate is under 18 — verify the engagement complies with the Adolescent Labour rules before converting."),
				indicator="orange",
				title=_("Minor Candidate"),
			)
		if age_years > MAX_EMPLOYMENT_AGE:
			frappe.throw(_("Date of Birth implies an age over {0} years — please re-check.").format(MAX_EMPLOYMENT_AGE))

	def _validate_required_documents(self):
		"""Block a candidate submission unless the mandatory documents are
		attached. HR-created drafts (status='Draft') are exempt so HR can stage
		a record before the candidate uploads.

		- PAN Card + Aadhaar Card: always required.
		- Previous Payslip: required unless the candidate flags themselves a fresher.
		- Signed Offer Letter: required ONLY when an offer letter was attached for
		  this candidate to download + sign via the invite (self.offer_letter set).
		"""
		if self.status == "Draft":
			return

		attached = {
			(row.document_type or "").strip()
			for row in (self.documents or [])
			if row.document and row.document_type
		}

		missing = [d for d in REQUIRED_DOCUMENT_TYPES if d not in attached]
		if not self.is_fresher and PAYSLIP_DOCUMENT_TYPE not in attached:
			missing.append(PAYSLIP_DOCUMENT_TYPE)
		if self.offer_letter and SIGNED_OFFER_LETTER_DOCUMENT_TYPE not in attached:
			missing.append(SIGNED_OFFER_LETTER_DOCUMENT_TYPE)

		if not missing:
			return

		hints = []
		if not self.is_fresher and PAYSLIP_DOCUMENT_TYPE in missing:
			hints.append(
				_("Select 'Fresher' under Employment Background if you have no previous employment to skip the payslip.")
			)
		if SIGNED_OFFER_LETTER_DOCUMENT_TYPE in missing:
			hints.append(
				_("Download the offer letter from the banner at the top, sign it, and upload the signed copy as 'Signed Offer Letter'.")
			)

		frappe.throw(
			_("Please attach the following required document(s): {0}.").format(", ".join(missing))
			+ ("<br>" + "<br>".join(hints) if hints else ""),
			title=_("Documents Required"),
		)

	def _validate_status_transitions(self):
		# Block 'Verified' unless every checklist box is ticked. Keeps HR honest
		# and gives Admins a single audit story: when status=Verified, all four
		# checks were green at that moment.
		if self.status == "Verified":
			missing = [
				label
				for field, label in (
					("pan_verified", _("PAN")),
					("aadhaar_verified", _("Aadhaar last-4")),
					("bank_verified", _("Bank A/C + IFSC")),
					("photo_verified", _("Photo")),
				)
				if not self.get(field)
			]
			if missing:
				frappe.throw(
					_("Cannot mark Verified — tick all verification checklist items first. Missing: {0}").format(", ".join(missing)),
					title=_("Verification Checklist Incomplete"),
				)
			if not self.verified_by:
				self.verified_by = frappe.session.user
			if not self.verified_on:
				self.verified_on = now_datetime()

		if self.status == "Rejected" and not self.rejection_reason:
			frappe.throw(_("Provide a Rejection Reason before rejecting an application."))

	def _check_duplicates(self):
		# PAN must be unique to a person, so an Active Employee already holding
		# this PAN is almost always a duplicate intake — stop the bleed at the door.
		# EXCEPTION: if this application is linked to the same Employee that
		# holds the PAN (existing-employee update scenario), the "duplicate" is
		# the employee themselves, not a separate person.
		if self.pan_number:
			existing_emp = frappe.db.exists(
				"Employee",
				{"pan_number": self.pan_number, "status": ("!=", "Left")},
			)
			if existing_emp and existing_emp != self.linked_employee:
				frappe.throw(
					_("PAN {0} is already used by Employee {1}. If this is a re-hire, please uninstall the old record or use a different PAN.").format(
						self.pan_number, existing_emp
					)
				)

		# An email with an open application for the same target company should
		# block re-submission — typical when a candidate hits 'Submit' twice.
		# Again, applications already linked to the same Employee are an update
		# flow and are not duplicates of each other.
		if self.personal_email:
			open_dup = frappe.db.exists(
				"Employee Onboarding Application",
				{
					"personal_email": self.personal_email,
					"status": ("in", ("Pending Verification", "Verified")),
					"target_company": self.target_company or "",
					"name": ("!=", self.name or ""),
					"linked_employee": ("in", ("", None)),
				},
			)
			if open_dup and not self.linked_employee:
				frappe.throw(
					_("An onboarding application from {0} is already awaiting review ({1}). Please wait for HR to revert.").format(
						self.personal_email, open_dup
					)
				)

	def _apply_invite_token(self):
		"""If the submission carried a valid invite token, flag it as invited
		and apply the HR-locked role fields server-side.

		Token resolution order:
		  1. Draft-backed opaque token (current) — the token is a random
		     48-char secret pointing at a Draft application that HR created
		     while generating the invite. ZERO data lives in the token/URL;
		     everything (names, email, company, designation, offer letter)
		     comes from the Draft row. The Draft is absorbed + deleted in
		     after_insert.
		  2. Legacy signed v2 / pipe tokens — links issued before the draft
		     flow keep working until they expire.

		The candidate can't tamper with role fields: in the draft flow they
		never leave the server; in the legacy flow the signature would break.

		An invalid/absent token just means this is a plain public submission —
		not an error."""
		if self.invited:
			return

		# (1) Draft-backed opaque token (the current invite flow).
		draft = (
			_resolve_invite_draft(self.invite_token, throw_on_expired=True)
			if self.invite_token
			else None
		)

		# (1b) Transport-independent fallback. The opaque token lives in a HIDDEN
		# web-form field, and anonymous submissions do NOT reliably round-trip
		# hidden controls — web_form.accept() blanks any field missing from the
		# POST (data.get(fieldname, "")). When the token is lost the Draft would
		# never get absorbed (HR sees two records) AND the submission would shed
		# its HR-locked company/designation. Matching the candidate's own email
		# to the HR-staged Draft recovers both: one record, role fields intact.
		if not draft and self.status != "Draft" and self.personal_email:
			draft = _resolve_invite_draft_by_email(self.personal_email)

		if draft and draft.name != self.name:
			self.invited = 1
			# Keep the audit trail even when the email fallback (not the token in
			# hand) is what matched the draft.
			if not self.invite_token and draft.invite_token:
				self.invite_token = draft.invite_token
			self.invite_email = draft.invite_email or draft.personal_email
			self.invite_expires_on = draft.invite_expires_on
			for f in ("target_company", "target_designation", "employment_type", "offer_letter"):
				if draft.get(f):
					self.set(f, draft.get(f))
			for f in ("first_name", "middle_name", "last_name"):
				if draft.get(f) and not self.get(f):
					self.set(f, draft.get(f))
			# Absorb the draft after WE are safely inserted (see after_insert).
			self._invite_draft_name = draft.name
			return

		# (2) Legacy signed tokens.
		if not self.invite_token:
			return
		parsed = _verify_invite_token(self.invite_token)
		if not parsed:
			return

		self.invited = 1
		self.invite_email = parsed.get("email") or self.invite_email
		self.invite_expires_on = parsed.get("expires_on") or self.invite_expires_on

		for src, attr in (
			("target_company", "target_company"),
			("target_designation", "target_designation"),
			("employment_type", "employment_type"),
		):
			val = parsed.get(src)
			if val:
				setattr(self, attr, val)

		# Names from the invite are used only as fallbacks — if the candidate
		# corrected them on the form (e.g. legal vs preferred name), respect that.
		for src, attr in (
			("first_name", "first_name"),
			("middle_name", "middle_name"),
			("last_name", "last_name"),
		):
			if parsed.get(src) and not self.get(attr):
				setattr(self, attr, parsed[src])

	def after_insert(self):
		"""Post-insert duties:
		  1. Count this SUCCESSFUL guest submission toward the daily rate
		     limits — counting here (not before_insert) means failed
		     validation attempts never burn the candidate's allowance.
		  2. If this came from a draft-backed invite, absorb the draft:
		     re-point its File attachments (offer letter) at this row, then
		     delete the placeholder so HR's list shows ONE live record."""
		_count_guest_submission(self)

		draft_name = getattr(self, "_invite_draft_name", None)
		if not draft_name or not frappe.db.exists("Employee Onboarding Application", draft_name):
			return
		try:
			# Files first — frappe.delete_doc would otherwise take the offer
			# letter File down with the draft.
			for file_name in frappe.get_all(
				"File",
				filters={
					"attached_to_doctype": "Employee Onboarding Application",
					"attached_to_name": draft_name,
				},
				pluck="name",
			):
				frappe.db.set_value(
					"File",
					file_name,
					{"attached_to_doctype": self.doctype, "attached_to_name": self.name},
					update_modified=False,
				)
			frappe.delete_doc(
				"Employee Onboarding Application",
				draft_name,
				ignore_permissions=True,
				force=True,
			)
		except Exception:
			frappe.log_error(
				title="Onboarding: invite draft absorption failed",
				message=frappe.get_traceback(),
			)


def _request_user_agent() -> str:
	"""Browser User-Agent of the current request, '' outside web context.
	Truncated defensively — UA strings are attacker-controlled input."""
	try:
		req = getattr(frappe.local, "request", None)
		if req is None:
			return ""
		return (req.headers.get("User-Agent") or "")[:500]
	except Exception:
		return ""


def _resolve_invite_draft(token: str, throw_on_expired: bool = False):
	"""Resolve an opaque invite token to its Draft application, or None.

	Tokens are 48-char random secrets (`frappe.generate_hash`) — unguessable,
	carry no data, and die with the draft. Expiry is checked against the
	draft's invite_expires_on; an expired-but-valid token throws (the
	candidate deserves a clear message) when throw_on_expired is set.
	"""
	if not token or len(token) < 32 or "|" in token or token.startswith("v2:"):
		return None
	name = frappe.db.get_value(
		"Employee Onboarding Application",
		{"invite_token": token, "status": "Draft"},
		"name",
	)
	if not name:
		return None
	draft = frappe.get_doc("Employee Onboarding Application", name)
	if draft.invite_expires_on and getdate(draft.invite_expires_on) < getdate():
		if throw_on_expired:
			frappe.throw(_("This invite link has expired. Please request a fresh link from HR."))
		return None
	return draft


def _resolve_invite_draft_by_email(email: str):
	"""Find a candidate's outstanding HR-staged Draft by email.

	This is the transport-independent fallback for when the opaque invite token
	didn't survive the anonymous web-form POST (hidden controls are dropped).
	generate_invite_link_full keeps at most one Draft per email ("refresh, don't
	stack"), so there's never ambiguity about which draft to absorb. Only
	NON-expired Drafts qualify — an expired invite must not silently auto-absorb.
	"""
	email = (email or "").strip().lower()
	if not email:
		return None
	name = frappe.db.get_value(
		"Employee Onboarding Application",
		{"personal_email": email, "status": "Draft"},
		"name",
	)
	if not name:
		return None
	draft = frappe.get_doc("Employee Onboarding Application", name)
	if draft.invite_expires_on and getdate(draft.invite_expires_on) < getdate():
		return None
	return draft


# --------------------------------------------------------------- invite tokens
def _invite_secret() -> str:
	"""HMAC secret for LEGACY (v2 / pipe) invite tokens.

	Fail CLOSED: prefer an explicit ``onboarding_invite_secret``, else the
	site's ``encryption_key`` (always present on a real Frappe site). We do
	NOT fall back to a hardcoded constant — signing auth-bearing tokens under
	a publicly-known key would let anyone forge an "invited" submission
	(bypassing the per-email rate limit and setting HR-locked role fields).
	The v3 draft-backed tokens are random secrets resolved via the DB and do
	not use this at all, so this only guards the deprecated legacy path."""
	conf = frappe.local.conf
	secret = conf.get("onboarding_invite_secret") or conf.get("encryption_key")
	if not secret:
		frappe.throw(_("Onboarding invite signing secret is not configured for this site."))
	return secret


def _sign(payload: str) -> str:
	return hmac.new(_invite_secret().encode(), payload.encode(), sha256).hexdigest()[:32]


def _validity_days() -> int:
	configured = cint(frappe.db.get_single_value("HR Settings", "onboarding_invite_validity_days"))
	return configured or INVITE_DEFAULT_VALIDITY_DAYS


def _build_v2_token(payload: dict) -> str:
	"""Build a v2 invite token carrying the full HR-set prefill.

	Format: ``v2:<base64url(json)>.<sig>`` where sig = HMAC over the base64
	body. Compact JSON keys keep the URL short:
	  e=email, x=expires_on, f/m/l=first/middle/last name,
	  c=target_company, d=target_designation, et=employment_type.
	"""
	body_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
	body_b64 = base64.urlsafe_b64encode(body_json.encode("utf-8")).decode("ascii").rstrip("=")
	return f"v2:{body_b64}.{_sign(body_b64)}"


def _verify_v2_token(token: str):
	"""Verify a v2 invite token and return the JSON payload dict.
	Raises on expiry; returns None on any tamper / parse failure."""
	if not token or not token.startswith("v2:"):
		return None
	try:
		body_b64, sig = token[3:].rsplit(".", 1)
	except ValueError:
		return None
	if not hmac.compare_digest(sig, _sign(body_b64)):
		return None
	# Re-pad the base64 body before decoding (we stripped trailing '=').
	padded = body_b64 + ("=" * ((4 - len(body_b64) % 4) % 4))
	try:
		payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
	except (ValueError, json.JSONDecodeError):
		return None
	expires_on = payload.get("x")
	if expires_on and getdate(expires_on) < getdate():
		frappe.throw(_("This invite link has expired. Please request a fresh link from HR."))
	return payload


def _verify_invite_token(token: str):
	"""Return {email, expires_on, ...} on success. Recognises three token
	shapes, in order of preference:

	  1. v2:<b64>.<sig>      — new format, carries HR prefill
	  2. email|expiry|sig    — current format, just email + expiry
	  3. email|sig           — legacy, no expiry

	An invalid signature / parse failure returns None (silently — public
	submissions without a token are valid). An EXPIRED but otherwise
	well-formed token throws so the candidate sees a clear message.
	"""
	if not token:
		return None

	# v2 format
	if token.startswith("v2:"):
		payload = _verify_v2_token(token)
		if not payload:
			return None
		return {
			"email": (payload.get("e") or "").lower(),
			"expires_on": payload.get("x"),
			"first_name": payload.get("f"),
			"middle_name": payload.get("m"),
			"last_name": payload.get("l"),
			"target_company": payload.get("c"),
			"target_designation": payload.get("d"),
			"employment_type": payload.get("et"),
		}

	# legacy pipe formats
	parts = token.split("|")
	try:
		if len(parts) == 3:
			email, expires_on, sig = parts
			if not hmac.compare_digest(sig, _sign(f"{email}|{expires_on}")):
				return None
			if getdate(expires_on) < getdate():
				frappe.throw(_("This invite link has expired. Please request a fresh link from HR."))
			return {"email": email.lower(), "expires_on": expires_on}
		if len(parts) == 2:
			email, sig = parts
			if hmac.compare_digest(sig, _sign(email.lower())):
				return {"email": email.lower(), "expires_on": None}
	except (ValueError, AttributeError):
		return None
	return None


@frappe.whitelist()
def generate_invite_link(email: str, validity_days: int | None = None) -> dict:
	"""HR-only: produce a signed, time-bound, shareable onboarding link."""
	frappe.only_for(HR_ROLES)
	email = (email or "").strip().lower()
	if not email or not EMAIL_RE.match(email):
		frappe.throw(_("A valid candidate email is required to generate an invite link."))

	days = cint(validity_days) or _validity_days()
	expires_on = add_days(getdate(), days).isoformat()
	token = f"{email}|{expires_on}|{_sign(f'{email}|{expires_on}')}"
	url = frappe.utils.get_url(f"/onboarding/new?invite_token={frappe.utils.quote(token)}")
	return {"email": email, "url": url, "expires_on": expires_on, "validity_days": days}


@frappe.whitelist()
def get_applicant_onboarding_prefill(job_applicant: str) -> dict:
	"""HR-only: resolve an Accepted Job Applicant into the fields the onboarding
	invite needs. Company / designation / employment type are pulled from the
	linked Job Opening; the designation on the applicant takes precedence if set.

	Returns a dict the Desk dialog pre-fills — HR can still edit before sending,
	which matters when the applicant has no Job Opening linked (company blank).
	"""
	frappe.only_for(HR_ROLES)
	ja = frappe.db.get_value(
		"Job Applicant",
		job_applicant,
		["applicant_name", "email_id", "designation", "job_title", "status"],
		as_dict=True,
	)
	if not ja:
		frappe.throw(_("Job Applicant {0} not found.").format(job_applicant))

	company = None
	designation = ja.designation
	employment_type = None
	if ja.job_title and frappe.db.exists("Job Opening", ja.job_title):
		opening = frappe.db.get_value(
			"Job Opening",
			ja.job_title,
			["company", "designation", "employment_type"],
			as_dict=True,
		)
		if opening:
			company = opening.company
			designation = designation or opening.designation
			employment_type = opening.employment_type

	# Split the applicant's full name into first / last for the Employee record.
	name = (ja.applicant_name or "").strip()
	parts = name.split()
	first_name = parts[0] if parts else ""
	last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

	# Has an onboarding application already been created from this applicant /
	# this email? Surface it so HR doesn't double-invite.
	existing = frappe.db.get_value(
		"Employee Onboarding Application",
		{"personal_email": (ja.email_id or "").strip().lower(), "status": ("!=", "Rejected")},
		"name",
	)

	return {
		"first_name": first_name,
		"last_name": last_name,
		"personal_email": ja.email_id,
		"target_company": company,
		"target_designation": designation,
		"employment_type": employment_type,
		"applicant_status": ja.status,
		"existing_application": existing,
	}


@frappe.whitelist()
def generate_invite_link_full(
	first_name: str,
	personal_email: str,
	target_company: str,
	target_designation: str,
	middle_name: str | None = None,
	last_name: str | None = None,
	employment_type: str | None = None,
	validity_days: int | None = None,
	send_email: int | bool = 0,
	offer_letter: str | None = None,
	job_applicant: str | None = None,
) -> dict:
	"""HR-only: create (or refresh) a DRAFT Employee Onboarding Application and
	hand back an opaque invite link for the candidate.

	Privacy model (v3):
	  * The URL carries ONLY a random 48-char token — no names, no email, no
	    role. All prefill lives server-side on the Draft row, so browser
	    history / proxy logs / forwarded messages never leak candidate PII.
	  * HR-locked fields (company / designation / employment type / offer
	    letter) never leave the server at all; they're merged from the Draft
	    when the candidate submits.
	  * Regenerating for the same email REFRESHES the existing Draft (new
	    token, new expiry, updated fields) instead of stacking duplicates —
	    and instantly invalidates the previously-shared link.

	`offer_letter` is an optional /files URL (uploaded via the Desk dialog):
	the candidate downloads it through a token-gated endpoint, signs it, and
	uploads the signed copy under Documents (enforced by
	_validate_required_documents).
	"""
	frappe.only_for(HR_ROLES)
	first_name = (first_name or "").strip()
	personal_email = (personal_email or "").strip().lower()
	target_company = (target_company or "").strip()
	target_designation = (target_designation or "").strip()

	if not first_name:
		frappe.throw(_("First name is required to generate an invite."))
	if not personal_email or not EMAIL_RE.match(personal_email):
		frappe.throw(_("A valid candidate email is required."))
	if not target_company or not frappe.db.exists("Company", target_company):
		frappe.throw(_("Target Company is required and must exist."))
	if not target_designation or not frappe.db.exists("Designation", target_designation):
		frappe.throw(_("Target Designation is required and must exist."))
	if employment_type and not frappe.db.exists("Employment Type", employment_type):
		frappe.throw(_("Employment Type {0} does not exist.").format(employment_type))

	days = cint(validity_days) or _validity_days()
	expires_on = add_days(getdate(), days).isoformat()
	token = frappe.generate_hash(length=48)

	# One outstanding Draft per candidate email — refresh, don't stack.
	existing = frappe.db.get_value(
		"Employee Onboarding Application",
		{"personal_email": personal_email, "status": "Draft"},
		"name",
	)
	draft = (
		frappe.get_doc("Employee Onboarding Application", existing)
		if existing
		else frappe.new_doc("Employee Onboarding Application")
	)
	draft.update(
		{
			"status": "Draft",
			"first_name": first_name,
			"middle_name": (middle_name or "").strip(),
			"last_name": (last_name or "").strip(),
			"personal_email": personal_email,
			"target_company": target_company,
			"target_designation": target_designation,
			"employment_type": employment_type or "",
			"invited": 1,
			"invite_email": personal_email,
			"invite_token": token,
			"invite_expires_on": expires_on,
		}
	)
	if offer_letter:
		draft.offer_letter = offer_letter
	# Remember the originating applicant so conversion can link the Employee back
	# to the Job Applicant (and trigger the Applicant/Offer -> Accepted cascade).
	if job_applicant and frappe.db.exists("Job Applicant", job_applicant):
		draft.job_applicant = job_applicant
	draft.save(ignore_permissions=True)

	# Bind the uploaded offer-letter File to the draft (keeps it private +
	# findable; after_insert re-points it to the live row on submission).
	if offer_letter:
		file_name = frappe.db.get_value(
			"File", {"file_url": offer_letter, "attached_to_name": ("in", ("", None))}, "name"
		)
		if file_name:
			frappe.db.set_value(
				"File",
				file_name,
				{
					"attached_to_doctype": "Employee Onboarding Application",
					"attached_to_name": draft.name,
					"is_private": 1,
				},
				update_modified=False,
			)

	# Opaque URL — the param name matches the web form's hidden field so it
	# auto-populates; the value is meaningless without our database.
	url = frappe.utils.get_url(f"/onboarding/new?invite_token={frappe.utils.quote(token)}")

	result = {
		"email": personal_email,
		"url": url,
		"expires_on": expires_on,
		"validity_days": days,
		"first_name": first_name,
		"middle_name": middle_name or "",
		"last_name": last_name or "",
		"target_company": target_company,
		"target_designation": target_designation,
		"employment_type": employment_type or "",
		"has_offer_letter": bool(offer_letter),
		"draft": draft.name,
		"sent": False,
	}

	if cint(send_email):
		_send_invite_email(result)
		result["sent"] = True

	return result


@frappe.whitelist(allow_guest=True)
def get_invite_prefill(token: str) -> dict:
	"""Guest endpoint for the public onboarding form: exchange a valid invite
	token for the candidate's prefill. Only the token holder can call this —
	equivalent trust to holding the emailed link itself — and the response is
	limited to what the candidate already knows about themselves plus the role
	labels HR chose. Sensitive role wiring stays server-side."""
	draft = _resolve_invite_draft(token, throw_on_expired=True)
	if not draft:
		frappe.throw(_("This invite link is invalid or has already been used."))
	return {
		"first_name": draft.first_name or "",
		"middle_name": draft.middle_name or "",
		"last_name": draft.last_name or "",
		"personal_email": draft.personal_email or "",
		"target_company": draft.target_company or "",
		"target_designation": draft.target_designation or "",
		"has_offer_letter": bool(draft.offer_letter),
		"expires_on": str(draft.invite_expires_on or ""),
		**_onboarding_theme(draft.target_company),
	}


@frappe.whitelist(allow_guest=True)
def download_offer_letter(token: str):
	"""Guest, token-gated download of the offer letter HR attached to the
	invite draft. The File stays private; this endpoint is the only guest
	path to it, and it dies with the draft (i.e., once the candidate submits
	or the invite expires)."""
	draft = _resolve_invite_draft(token, throw_on_expired=True)
	if not draft or not draft.offer_letter:
		frappe.throw(_("No offer letter is available for this invite."))
	file_doc = frappe.get_doc("File", {"file_url": draft.offer_letter})
	frappe.local.response.filename = file_doc.file_name or "offer-letter.pdf"
	frappe.local.response.filecontent = file_doc.get_content()
	frappe.local.response.type = "download"


def _send_invite_email(payload: dict):
	"""Compose + queue the candidate-facing invite email. Pulled out so both
	generate_invite_link_full(send_email=1) and resend_invite_link share it."""
	candidate_name = " ".join(p for p in (payload.get("first_name"), payload.get("last_name")) if p) or _("Candidate")
	subject = _("Onboarding invitation — {0}").format(payload.get("target_company") or "")
	role_line = (
		_("Role: <b>{0}</b> at <b>{1}</b>.").format(
			payload.get("target_designation") or _("the role offered"),
			payload.get("target_company") or _("the company"),
		)
	)
	offer_line = (
		_("Your offer letter is available on the form — please download it, sign it, and upload the signed copy along with your documents.")
		if payload.get("has_offer_letter")
		else ""
	)
	message = _("""
		<p>Hello {name},</p>
		<p>Welcome! Please complete your onboarding form using the link below. {role_line}</p>
		<p>The link is valid through <b>{expires_on}</b>. Most fields are pre-filled — you only need to fill in your personal details, IDs and bank account. {offer_line}</p>
		<p><a href="{url}">{url}</a></p>
		<p>If you didn't expect this email, please ignore it.</p>
	""").format(
		name=candidate_name,
		role_line=role_line,
		expires_on=payload["expires_on"],
		url=payload["url"],
		offer_line=offer_line,
	)
	frappe.sendmail(recipients=[payload["email"]], subject=subject, message=message, now=False)


@frappe.whitelist()
def email_invite_link(email: str, url: str, expires_on: str | None = None) -> dict:
	"""HR-only: email an ALREADY-generated invite link (the exact URL shown in
	the result dialog) without minting a new token. Used by the "Email to
	Candidate" action so the copied link and the emailed link are identical."""
	frappe.only_for(HR_ROLES)
	email = (email or "").strip().lower()
	if not email or not EMAIL_RE.match(email):
		frappe.throw(_("A valid candidate email is required."))
	if not url:
		frappe.throw(_("No link to email."))
	_send_invite_email(
		{
			"email": email,
			"url": url,
			"expires_on": expires_on or "",
			"first_name": "",
			"last_name": "",
			"target_company": "",
			"target_designation": "",
		}
	)
	return {"sent": True, "email": email}


@frappe.whitelist()
def resend_invite_link(email: str, validity_days: int | None = None) -> dict:
	"""HR-only: regenerate the link and email it directly to the candidate."""
	frappe.only_for(HR_ROLES)
	link = generate_invite_link(email, validity_days)
	subject = _("Complete your onboarding form")
	message = _("""
		<p>Hello,</p>
		<p>Please use the link below to fill in your onboarding details. The link is valid through <b>{0}</b>.</p>
		<p><a href="{1}">{1}</a></p>
		<p>If you have already submitted, you can ignore this email.</p>
	""").format(link["expires_on"], link["url"])
	frappe.sendmail(recipients=[link["email"]], subject=subject, message=message, now=False)
	link["sent"] = True
	return link


# --------------------------------------------------------------- convert glue
@frappe.whitelist()
def get_application_for_setup(name: str) -> dict:
	"""HR-only: payload the New Employee Setup page pre-fills from."""
	frappe.only_for(HR_ROLES)
	doc = frappe.get_doc("Employee Onboarding Application", name)
	if doc.status == "Converted":
		frappe.throw(_("This application has already been converted to Employee {0}.").format(doc.linked_employee))
	if doc.status == "Rejected":
		frappe.throw(_("This application has been Rejected and cannot be converted."))
	if doc.status == "Pending Verification":
		frappe.msgprint(
			_("Heads-up: this application has not been Verified yet. Verify before converting if your policy requires it."),
			indicator="orange",
			title=_("Not Verified"),
		)

	data = {f: doc.get(f) for f in SETUP_FIELDS}
	data["onboarding_application"] = doc.name
	data["company"] = doc.target_company
	data["department"] = doc.target_department
	data["designation"] = doc.target_designation
	data["employment_type"] = doc.employment_type
	data["user_email"] = doc.personal_email
	# Carry the originating applicant (links the Employee back to it on create).
	data["job_applicant"] = doc.job_applicant
	# Default the Employee's Confirmation Date to when the candidate submitted —
	# HR can still place them on probation instead on the setup page.
	data["final_confirmation_date"] = getdate(doc.submitted_on) if doc.submitted_on else None
	return data


def mark_converted(application: str, employee: str):
	"""Stamp the application Converted, link the created Employee, carry over
	application-only fields the setup page doesn't show (emergency contact,
	address, photo), re-attach uploaded documents to the Employee, and write
	the DPDP consent row that closes the audit loop.

	Called by setup_new_employee when launched from an application.
	"""
	if not application or not frappe.db.exists("Employee Onboarding Application", application):
		return

	app = frappe.get_doc("Employee Onboarding Application", application)

	emp_updates = {}
	if app.emergency_contact_name:
		emp_updates["person_to_be_contacted"] = app.emergency_contact_name
	if app.emergency_contact_relation:
		emp_updates["relation"] = app.emergency_contact_relation
	if app.emergency_contact_phone:
		emp_updates["emergency_phone_number"] = app.emergency_contact_phone
	if app.current_address:
		emp_updates["current_address"] = app.current_address
	# Permanent address + the "same as current" convenience toggle. When the
	# candidate ticked it, _normalise already mirrored current->permanent on the
	# application; carry both so the Employee shows the same state. set_value
	# bypasses the validate hook (apply_address_copy_rules), so mirror explicitly.
	if app.get("same_as_current_address"):
		emp_updates["permanent_address_same_as_current"] = 1
		emp_updates["permanent_address"] = app.current_address
	elif app.permanent_address:
		emp_updates["permanent_address"] = app.permanent_address
	if app.photo:
		emp_updates["image"] = app.photo
	if emp_updates:
		frappe.db.set_value("Employee", employee, emp_updates)

	# Re-attach uploaded documents to the Employee as File records, so HR can
	# find them on the Employee form rather than chasing back to the application.
	_attach_documents_to_employee(app, employee)

	# Copy the candidate's documents child table onto the Employee's matching
	# table as-is (same type + file + notes), so the structured list survives on
	# the Employee form alongside the loose File attachments above.
	_copy_documents_table_to_employee(app, employee)

	# Stamp the application before writing the consent row so the consent row
	# can reference the linked_employee in its audit trail.
	frappe.db.set_value(
		"Employee Onboarding Application",
		application,
		{
			"status": "Converted",
			"linked_employee": employee,
			"verified_by": app.verified_by or frappe.session.user,
			"verified_on": app.verified_on or now_datetime(),
		},
	)

	_record_dpdp_consent(app, employee)


def _attach_documents_to_employee(app, employee: str):
	"""Each row in app.documents points at a File. Clone the File against the
	Employee so the candidate's uploads survive even if the application is
	purged (DPDP retention) and so HR sees them on the Employee form."""
	for row in app.get("documents") or []:
		if not row.document:
			continue
		try:
			source = frappe.db.get_value(
				"File",
				{"file_url": row.document},
				["name", "file_name", "is_private"],
				as_dict=True,
			)
			if not source:
				continue
			# A second File row attached to Employee (Frappe doesn't enforce uniqueness on file_url).
			if frappe.db.exists(
				"File",
				{
					"attached_to_doctype": "Employee",
					"attached_to_name": employee,
					"file_url": row.document,
				},
			):
				continue
			frappe.get_doc(
				{
					"doctype": "File",
					"file_url": row.document,
					"file_name": source.file_name or (row.document.rsplit("/", 1)[-1]),
					"attached_to_doctype": "Employee",
					"attached_to_name": employee,
					"is_private": source.is_private or 0,
					"folder": "Home/Attachments",
				}
			).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(
				title="Onboarding: attach document to Employee failed",
				message=frappe.get_traceback(),
			)


def _copy_documents_table_to_employee(app, employee: str):
	"""Mirror app.documents onto Employee.employee_documents row-for-row.

	Uses low-level child-row inserts rather than a full emp.save(): by the time
	mark_converted runs the in_new_employee_setup flag is already cleared, so a
	save would re-fire the Employee activation hooks (leave setup, policy acks).
	Idempotent — a (document_type, document) pair already present is skipped, so
	re-running conversion never duplicates rows."""
	if not frappe.get_meta("Employee").has_field("employee_documents"):
		return  # add_employee_documents_table patch hasn't run on this site yet
	src_rows = app.get("documents") or []
	if not src_rows:
		return

	table_filters = {
		"parent": employee,
		"parenttype": "Employee",
		"parentfield": "employee_documents",
	}
	existing = {
		(r.document_type, r.document)
		for r in frappe.get_all(
			"Employee Onboarding Document",
			filters=table_filters,
			fields=["document_type", "document"],
		)
	}
	idx = frappe.db.count("Employee Onboarding Document", table_filters)

	for row in src_rows:
		key = (row.document_type, row.document)
		if key in existing:
			continue
		idx += 1
		frappe.get_doc(
			{
				"doctype": "Employee Onboarding Document",
				"parenttype": "Employee",
				"parent": employee,
				"parentfield": "employee_documents",
				"idx": idx,
				"document_type": row.document_type,
				"document": row.document,
				"notes": row.get("notes"),
			}
		).insert(ignore_permissions=True)
		existing.add(key)


def _record_dpdp_consent(app, employee: str):
	"""Write a Data Consent row for STATUTORY_PAYROLL purpose — the lawful basis
	under which we will hold this person's PAN, UAN, bank details, etc. The
	consent submission timestamp + source IP are carried into the audit notes.
	Best-effort: a failure here does NOT block the conversion (logged only)."""
	if not frappe.db.exists("Data Consent Purpose", "STATUTORY_PAYROLL"):
		return  # DPDP layer not seeded on this site
	try:
		if frappe.db.exists(
			"Data Consent",
			{"employee": employee, "purpose": "STATUTORY_PAYROLL", "consent_status": "Granted"},
		):
			return
		consent = frappe.get_doc(
			{
				"doctype": "Data Consent",
				"employee": employee,
				"purpose": "STATUTORY_PAYROLL",
				"consent_version": app.consent_text_version or "1.0",
				"granted_on": (app.consent_timestamp and getdate(app.consent_timestamp)) or getdate(),
				"consent_method": "Web Form",
				"consent_status": "Granted",
				"notes": _("Captured at onboarding intake {0}. Source IP: {1}. Submitted at {2}.").format(
					app.name, app.consent_ip or _("not captured"), app.consent_timestamp or app.submitted_on or "?"
				),
			}
		)
		consent.insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(
			title="Onboarding: Data Consent write failed",
			message=frappe.get_traceback(),
		)


# --------------------------------------------------------------- guest hooks
GUEST_LIMIT_PER_EMAIL_PER_DAY = 1
GUEST_LIMIT_PER_IP_PER_DAY = 5
GUEST_RATE_WINDOW_SECONDS = 24 * 60 * 60


def before_guest_insert(doc, method=None):
	"""Hook target for the public Web Form. Applies the rate limit BEFORE the
	doc-level validate() runs so a bot can't burn cycles on validation.
	Wired via hooks.py doc_events."""
	if frappe.session.user != "Guest":
		return
	_rate_limit_guest_submission(doc)


def _is_invited_submission(doc) -> bool:
	"""True when the submission carries a live HR-issued draft token whose
	email matches the submitted email. An invite is explicit authorization —
	the public per-email throttle must not apply to it (a failed validation
	retry or an HR re-invite on the same day are both legitimate). True
	duplicates are still blocked by _check_duplicates, and the per-IP limit
	below still curbs abuse."""
	if not doc.invite_token:
		return False
	try:
		draft = _resolve_invite_draft(doc.invite_token)
	except Exception:
		return False
	if not draft:
		return False
	draft_email = (draft.personal_email or draft.invite_email or "").strip().lower()
	return bool(draft_email) and draft_email == (doc.personal_email or "").strip().lower()


def _rate_limit_guest_submission(doc):
	"""CHECK-ONLY throttle: one successful submission per email per day, five
	per source IP per day (Redis-backed, 24h TTL). The counters are
	incremented in after_insert (_count_guest_submission) so a submission
	that FAILS validation never burns the candidate's daily allowance —
	that asymmetry is what previously locked out candidates who fixed a
	form error and retried."""
	cache = frappe.cache
	invited = _is_invited_submission(doc)

	email_key = (doc.personal_email or "").strip().lower()
	if email_key and not invited:
		ckey = f"onboarding-rl:email:{email_key}"
		if cint(cache.get_value(ckey, expires=True)) >= GUEST_LIMIT_PER_EMAIL_PER_DAY:
			frappe.throw(
				_("An application from this email was already submitted today. Please reach out to HR if you need to update it."),
				title=_("Already Submitted"),
			)

	ip = getattr(frappe.local, "request_ip", None) or ""
	if ip:
		ikey = f"onboarding-rl:ip:{ip}"
		if cint(cache.get_value(ikey, expires=True)) >= GUEST_LIMIT_PER_IP_PER_DAY:
			frappe.throw(
				_("Too many submissions from this network in a short time. Please try again later."),
				title=_("Rate Limited"),
			)


def _count_guest_submission(doc):
	"""Record a SUCCESSFUL guest submission against the daily limits. Called
	from after_insert — by then every validator has passed and the row is in."""
	if frappe.session.user != "Guest":
		return
	cache = frappe.cache
	email_key = (doc.personal_email or "").strip().lower()
	if email_key:
		ckey = f"onboarding-rl:email:{email_key}"
		cache.set_value(
			ckey, cint(cache.get_value(ckey, expires=True)) + 1, expires_in_sec=GUEST_RATE_WINDOW_SECONDS
		)
	ip = getattr(frappe.local, "request_ip", None) or ""
	if ip:
		ikey = f"onboarding-rl:ip:{ip}"
		cache.set_value(
			ikey, cint(cache.get_value(ikey, expires=True)) + 1, expires_in_sec=GUEST_RATE_WINDOW_SECONDS
		)
