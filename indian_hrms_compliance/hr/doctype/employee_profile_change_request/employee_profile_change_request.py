# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Employee Profile Change Request — ESS self-service profile updates with HR
approval gate.

Flow:
  1. Employee opens Profile in the PWA and taps "Request Update".
  2. EditProfile.vue pre-fills current values for editable fields; sensitive
     IDs (PAN, Aadhaar, bank A/c) are shown masked. Empty = no change.
  3. On submit, the PWA calls `submit_profile_change_request(changes)` which
     creates a record here in status 'Submitted'. Consent is captured per DPDP.
  4. The request shows up in HR's Approvals inbox (PWA + Desk).
  5. HR approves → fields write to Employee; a Data Consent row is created;
     each row's `applied` flag is set; status flips to 'Approved'.
  6. HR rejects → review_notes mandatory; status = 'Rejected'.
  7. Employee withdraws (only while 'Submitted') → status = 'Withdrawn'.

The list of editable fields is governed by HR Settings.self_editable_employee_fields
so HR can tighten / loosen the surface without code changes.
"""

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime

HR_ROLES = ("HR Manager", "HR User", "System Manager")

# Default surface — overridable via HR Settings.self_editable_employee_fields
# (one fieldname per line). Curated to "fields the employee knows best
# themselves" — excludes pay/role/reporting fields.
DEFAULT_EDITABLE_FIELDS = (
	"cell_number",
	"personal_email",
	"current_address",
	"current_accommodation_type",
	"permanent_address",
	"permanent_accommodation_type",
	"marital_status",
	"blood_group",
	"emergency_phone_number",
	"person_to_be_contacted",
	"relation",
	# Statutory IDs — sensitive; masked in get_my_profile_editable_fields.
	"pan_number",
	"aadhaar_number",
	"uan_number",
	"esic_ip_number",
	"provident_fund_account",
	"nps_pran",
	"bank_name",
	"bank_ac_no",
	"ifsc_code",
	"image",
)

# Fields whose CURRENT value we never expose verbatim to the PWA prefill —
# only a masked indicator. Empty submission = no change.
SENSITIVE_FIELDS = frozenset({
	"pan_number",
	"aadhaar_number",
	"bank_ac_no",
	"esic_ip_number",
})


class EmployeeProfileChangeRequest(Document):
	def before_insert(self):
		if not self.submitted_at:
			self.submitted_at = now_datetime()
		if self.dpdp_consent and not self.consent_timestamp:
			self.consent_timestamp = now_datetime()
			self.consent_ip = getattr(frappe.local, "request_ip", None) or ""
		# Snapshot the active consent text version at submission time.
		if not self.consent_text_version:
			self.consent_text_version = (
				frappe.db.get_single_value("HR Settings", "employee_consent_text_version")
				or "1.0"
			)

	def validate(self):
		if not self.changes:
			frappe.throw(_("At least one field change is required."))

		allowed = set(get_editable_fieldnames())
		for ch in self.changes:
			if not ch.fieldname:
				frappe.throw(_("Each change row must specify the field name."))
			if ch.fieldname not in allowed:
				frappe.throw(
					_("Field {0} is not on the self-editable list — request rejected.").format(ch.fieldname)
				)
			_validate_field_value(ch.fieldname, ch.new_value)

		if self.status == "Rejected" and not self.review_notes:
			frappe.throw(_("Add a Review Note before rejecting — the employee will see it."))


# ---------------------------------------------------------------------------
# Field surface + validation
# ---------------------------------------------------------------------------


def get_editable_fieldnames() -> list[str]:
	"""Resolve the active editable fieldname list from HR Settings, falling back
	to DEFAULT_EDITABLE_FIELDS. One fieldname per line, blank lines / # comments
	ignored. Filters to fields that actually exist on Employee."""
	# §1 guard: get_single_value RAISES (not None) if the field is absent from the
	# meta — e.g. on a site that hasn't migrated the field yet. Degrade to defaults.
	raw = ""
	if frappe.get_meta("HR Settings").has_field("self_editable_employee_fields"):
		raw = frappe.db.get_single_value("HR Settings", "self_editable_employee_fields") or ""
	configured = [
		line.strip()
		for line in raw.splitlines()
		if line.strip() and not line.strip().startswith("#")
	]
	candidates = configured or list(DEFAULT_EDITABLE_FIELDS)

	emp_meta = frappe.get_meta("Employee")
	have = {df.fieldname for df in emp_meta.fields}
	return [f for f in candidates if f in have]


def _validate_field_value(fieldname: str, value):
	"""Reuse the canonical validators that the Employee master enforces — we
	want the same hard locks here so an HR approval can't sneak bad data in."""
	if value in (None, ""):
		# Blank = "no change" — caller decides whether to drop it on apply.
		return

	from indian_hrms_compliance.overrides.employee_master import (
		AADHAAR_FULL_RE,
		IFSC_RE,
		PAN_RE,
		UAN_RE,
		verhoeff_check_aadhaar,
	)

	if fieldname == "pan_number":
		v = str(value).strip().upper()
		if not PAN_RE.match(v):
			frappe.throw(_("PAN must match ABCDE1234F."))
	elif fieldname == "aadhaar_number":
		v = re.sub(r"\D", "", str(value))
		if not AADHAAR_FULL_RE.match(v):
			frappe.throw(_("Aadhaar must be exactly 12 digits and start with 2-9."))
		if not verhoeff_check_aadhaar(v):
			frappe.throw(_("Aadhaar checksum failed — please re-check the number."))
	elif fieldname == "uan_number":
		v = re.sub(r"\D", "", str(value))
		if not UAN_RE.match(v):
			frappe.throw(_("UAN must be exactly 12 digits."))
	elif fieldname == "ifsc_code":
		v = str(value).strip().upper()
		if not IFSC_RE.match(v):
			frappe.throw(_("IFSC must be 4 letters + '0' + 6 alphanumeric (e.g., HDFC0001234)."))
	elif fieldname == "cell_number":
		v = re.sub(r"[^\d+]", "", str(value))
		if not re.match(r"^(\+?91)?[6-9]\d{9}$", v):
			frappe.throw(_("Mobile must be a 10-digit Indian number (starting 6/7/8/9), optionally prefixed +91."))
	elif fieldname == "personal_email":
		if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", str(value)):
			frappe.throw(_("Email format looks invalid."))


def _normalised(fieldname: str, value):
	"""Mirror the same normalisation Employee.validate would apply, so what we
	store on Employee matches what we'd have stored if HR set it directly."""
	if value in (None, ""):
		return value
	if fieldname == "pan_number":
		return str(value).strip().upper()
	if fieldname == "aadhaar_number":
		return re.sub(r"\D", "", str(value))
	if fieldname == "uan_number":
		return re.sub(r"\D", "", str(value))
	if fieldname == "ifsc_code":
		return str(value).strip().upper()
	if fieldname == "cell_number":
		return re.sub(r"[^\d+]", "", str(value))
	if fieldname == "personal_email":
		return str(value).strip().lower()
	return value


def mask_value(fieldname: str, value):
	"""Return a user-safe display of a sensitive field. Non-sensitive fields
	pass through unchanged."""
	if not value:
		return ""
	if fieldname not in SENSITIVE_FIELDS:
		return value
	s = str(value)
	if fieldname == "aadhaar_number":
		return f"XXXX XXXX {s[-4:]}" if len(s) >= 4 else "XXXX"
	if fieldname == "pan_number":
		return f"XXXXX{s[-4:]}" if len(s) >= 4 else "XXXXX"
	# bank_ac_no / esic_ip_number etc.
	return f"...{s[-4:]}" if len(s) >= 4 else "***"


# ---------------------------------------------------------------------------
# Workflow actions
# ---------------------------------------------------------------------------


def apply_changes(req: "EmployeeProfileChangeRequest"):
	"""Push each non-empty new_value to the Employee record and stamp `applied`.
	Called from approve_profile_change_request and the inbox approve hook.

	Atomic per-request: if any single field fails, we don't half-apply — the
	parent caller wraps this in a savepoint.
	"""
	emp = frappe.get_doc("Employee", req.employee)
	changed_fields = []

	for ch in req.changes:
		raw = ch.new_value
		if raw is None or str(raw).strip() == "":
			# Empty = "no change" for this field. Don't override existing values.
			continue
		value = _normalised(ch.fieldname, raw)
		# Skip if value is already the same — avoids spurious history rows.
		if emp.get(ch.fieldname) == value:
			ch.applied = 1
			continue
		emp.set(ch.fieldname, value)
		ch.applied = 1
		changed_fields.append(ch.fieldname)

	if not changed_fields:
		return []

	# Employee.validate (the canonical hook chain — statutory ID formats,
	# person consistency, etc.) will still run and can throw. We catch the
	# person-consistency error specifically and reword it; everything else
	# bubbles up unchanged so HR sees the real reason.
	try:
		emp.save(ignore_permissions=True)
	except frappe.exceptions.ValidationError as e:
		msg = str(e)
		if "Person-level fields must match" in msg or "Statutory ID Mismatch" in msg:
			frappe.throw(
				_(
					"Cannot apply this update — another Employee record linked to the same User has different values for one of: PAN, UAN, ESIC, Aadhaar, NPS PRAN, DOB, or gender. Reconcile those Employee records first, then re-approve."
				),
				title=_("Person-level Mismatch"),
			)
		raise
	return changed_fields


def record_consent_for_request(req: "EmployeeProfileChangeRequest"):
	"""Write a Data Consent row tied to the profile update — the employee
	re-consented to fresh processing when they submitted the change."""
	if not frappe.db.exists("Data Consent Purpose", "STATUTORY_PAYROLL"):
		return
	try:
		frappe.get_doc(
			{
				"doctype": "Data Consent",
				"employee": req.employee,
				"purpose": "STATUTORY_PAYROLL",
				"consent_version": req.consent_text_version or "1.0",
				"granted_on": (req.consent_timestamp and getdate(req.consent_timestamp)) or getdate(),
				"consent_method": "Web Form",
				"consent_status": "Granted",
				"notes": _("Captured at profile change request {0}. Source IP: {1}.").format(
					req.name, req.consent_ip or _("not captured")
				),
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(
			title="Profile Change: Data Consent write failed",
			message=frappe.get_traceback(),
		)


# ---------------------------------------------------------------------------
# Whitelisted endpoints
# ---------------------------------------------------------------------------


def _get_current_employee_for_user() -> str:
	"""Resolve the current session user → Employee.name. Throws if missing.

	Uses the same active-employee resolution as the PWA context
	(``get_active_employee_name`` — honours the multi-employment switcher /
	Primary Employer), so ESS profile actions target the employer the user is
	actually viewing rather than an arbitrary first Active row.
	"""
	from indian_hrms_compliance.api import get_active_employee_name

	emp = get_active_employee_name()
	if not emp:
		frappe.throw(_("No active Employee record is linked to your User."))
	return emp


@frappe.whitelist()
def get_my_profile_editable_fields() -> list[dict]:
	"""Return [{fieldname, label, fieldtype, options, current, sensitive}] for
	every editable field, with `current` MASKED for sensitive fields."""
	employee = _get_current_employee_for_user()
	emp_meta = frappe.get_meta("Employee")
	df_map = {df.fieldname: df for df in emp_meta.fields}
	fields = [fn for fn in get_editable_fieldnames() if fn in df_map]
	# Direct SQL read — avoid putting a Document instance in doc_cache that
	# could shadow the live state in a later approve flow.
	emp_values = frappe.db.get_value("Employee", employee, fields, as_dict=True) or {}

	out = []
	for fn in fields:
		df = df_map.get(fn)
		if not df:
			continue
		current = emp_values.get(fn)
		out.append(
			{
				"fieldname": fn,
				"label": _(df.label) if df.label else fn,
				"fieldtype": df.fieldtype,
				"options": df.options or "",
				"description": _(df.description) if df.description else "",
				"current": mask_value(fn, current) if fn in SENSITIVE_FIELDS else (current or ""),
				"sensitive": 1 if fn in SENSITIVE_FIELDS else 0,
			}
		)
	return out


@frappe.whitelist()
def submit_profile_change_request(changes: list | str, dpdp_consent: int = 1) -> dict:
	"""Employee endpoint. `changes` = [{fieldname, new_value}, ...]. Skips
	rows with empty new_value (= "no change requested for this field")."""
	import json

	employee = _get_current_employee_for_user()
	if isinstance(changes, str):
		changes = json.loads(changes)
	if not changes:
		frappe.throw(_("Submit at least one field change."))

	if not int(dpdp_consent or 0):
		frappe.throw(_("Please tick the consent box to submit your changes."))

	allowed = set(get_editable_fieldnames())
	emp_meta = frappe.get_meta("Employee")
	label_map = {df.fieldname: df.label for df in emp_meta.fields}
	# Read the Employee row via direct SQL — avoid frappe.get_doc here so we
	# don't park a Document instance in frappe.local.doc_cache that the later
	# apply_changes call would then reuse with a stale _doc_before_save baseline.
	emp_values = frappe.db.get_value(
		"Employee", employee, list({f for f in allowed if f in label_map}), as_dict=True
	) or {}

	rows = []
	for ch in changes:
		fn = (ch.get("fieldname") or "").strip()
		new_val = ch.get("new_value")
		if new_val is None or str(new_val).strip() == "":
			continue  # blank = no change
		if fn not in allowed:
			frappe.throw(_("Field {0} is not editable.").format(fn))
		_validate_field_value(fn, new_val)
		old_val = emp_values.get(fn)
		# Sensitive fields: do NOT persist any form of the old value on the
		# request row. HR sees the LIVE current value via get_profile_change_old_values
		# at review time. This keeps the audit trail free of historical raw
		# sensitive data while still giving HR a comparison surface.
		if fn in SENSITIVE_FIELDS:
			old_safe = ""
		else:
			old_safe = str(old_val) if old_val is not None else ""
		rows.append(
			{
				"fieldname": fn,
				"label": label_map.get(fn) or fn,
				"old_value": old_safe,
				"new_value": str(new_val),
				"applied": 0,
			}
		)

	if not rows:
		frappe.throw(_("No actual changes detected — all submitted values were blank."))

	doc = frappe.get_doc(
		{
			"doctype": "Employee Profile Change Request",
			"employee": employee,
			"status": "Submitted",
			"dpdp_consent": 1,
			"changes": rows,
		}
	).insert(ignore_permissions=True)

	# PWA-notify HR Users in this Company.
	_notify_hr_of_new_request(doc)

	return {"name": doc.name, "status": doc.status, "count": len(rows)}


@frappe.whitelist()
def approve_profile_change_request(name: str, comment: str | None = None) -> dict:
	"""HR approves: apply changes to Employee + write Data Consent + stamp."""
	frappe.only_for(HR_ROLES)
	doc = frappe.get_doc("Employee Profile Change Request", name)
	if doc.status != "Submitted":
		frappe.throw(_("Only Submitted requests can be approved (currently {0}).").format(doc.status))

	sp = "profile_change_approve"
	frappe.db.savepoint(sp)
	try:
		applied = apply_changes(doc)
		doc.status = "Approved"
		doc.reviewed_by = frappe.session.user
		doc.reviewed_at = now_datetime()
		if comment:
			doc.review_notes = comment
		doc.save(ignore_permissions=True)
		record_consent_for_request(doc)
	except Exception:
		try:
			frappe.db.rollback(save_point=sp)
		except Exception:
			pass
		raise

	_notify_employee_of_decision(doc, applied)
	return {"name": doc.name, "status": doc.status, "applied_fields": applied}


@frappe.whitelist()
def reject_profile_change_request(name: str, comment: str) -> dict:
	"""HR rejects with mandatory reason."""
	frappe.only_for(HR_ROLES)
	if not (comment and comment.strip()):
		frappe.throw(_("A rejection reason is required."))
	doc = frappe.get_doc("Employee Profile Change Request", name)
	if doc.status != "Submitted":
		frappe.throw(_("Only Submitted requests can be rejected (currently {0}).").format(doc.status))
	doc.status = "Rejected"
	doc.reviewed_by = frappe.session.user
	doc.reviewed_at = now_datetime()
	doc.review_notes = comment
	doc.save(ignore_permissions=True)
	_notify_employee_of_decision(doc, [])
	return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def get_my_profile_change_requests(limit: int = 20) -> list[dict]:
	"""Return the current employee's last N profile change requests with the
	count of fields changed and a short status indicator. Powers the PWA
	'My Profile Updates' history view."""
	employee = _get_current_employee_for_user()
	rows = frappe.get_all(
		"Employee Profile Change Request",
		filters={"employee": employee},
		fields=[
			"name",
			"status",
			"submitted_at",
			"reviewed_at",
			"reviewed_by",
			"review_notes",
		],
		order_by="submitted_at desc",
		limit=int(limit) or 20,
	)
	# Annotate each with the number of changes (separate query keeps it small).
	for r in rows:
		r["change_count"] = frappe.db.count("Employee Profile Change Item", {"parent": r["name"]})
	return rows


@frappe.whitelist()
def get_profile_change_old_values(name: str) -> list[dict]:
	"""HR-only: return the LIVE current value (masked for sensitive fields) of
	each field referenced by this change request. Lets HR review without us
	having stored the raw historical value on the request row.

	Returns [{fieldname, label, current_display, sensitive, requested}].
	"""
	frappe.only_for(HR_ROLES)
	doc = frappe.get_doc("Employee Profile Change Request", name)
	emp = frappe.get_doc("Employee", doc.employee)
	emp_meta = frappe.get_meta("Employee")
	label_map = {df.fieldname: df.label for df in emp_meta.fields}

	out = []
	for ch in doc.changes:
		raw = emp.get(ch.fieldname)
		display = mask_value(ch.fieldname, raw) if ch.fieldname in SENSITIVE_FIELDS else (str(raw) if raw is not None else "")
		out.append(
			{
				"fieldname": ch.fieldname,
				"label": label_map.get(ch.fieldname) or ch.label or ch.fieldname,
				"current_display": display,
				"sensitive": 1 if ch.fieldname in SENSITIVE_FIELDS else 0,
				"requested": ch.new_value,
				"applied": int(ch.applied or 0),
			}
		)
	return out


@frappe.whitelist()
def withdraw_profile_change_request(name: str) -> dict:
	"""Employee withdraws their own submitted request."""
	employee = _get_current_employee_for_user()
	doc = frappe.get_doc("Employee Profile Change Request", name)
	if doc.employee != employee:
		frappe.throw(_("You can only withdraw your own request."), frappe.PermissionError)
	if doc.status != "Submitted":
		frappe.throw(_("Only Submitted requests can be withdrawn."))
	doc.status = "Withdrawn"
	doc.save(ignore_permissions=True)

	# Refresh both sides: the employee's history + every HR user's inbox.
	try:
		from indian_hrms_compliance.api import _broadcast_hr_inbox_refresh, _pwa_refetch

		emp_user = frappe.db.get_value("Employee", employee, "user_id")
		if emp_user:
			_pwa_refetch(
				"indian_hrms_compliance:my_profile_change_requests", user=emp_user
			)
		_broadcast_hr_inbox_refresh()
	except Exception:
		pass

	return {"name": doc.name, "status": doc.status}


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


def _notify_hr_of_new_request(doc):
	try:
		from indian_hrms_compliance.api import _broadcast_hr_inbox_refresh
		from indian_hrms_compliance.hr.doctype.hrms_task.hrms_task import _safe_pwa_notification
	except Exception:
		return
	hr_users = frappe.get_all(
		"Has Role",
		filters={"role": ("in", ("HR Manager", "HR User"))},
		pluck="parent",
	)
	hr_users = [u for u in set(hr_users) if u and u not in ("Administrator", "Guest")]
	for u in hr_users:
		_safe_pwa_notification(
			to_user=u,
			message=_("{0} requested {1} profile change(s) — review pending.").format(
				doc.employee_name or doc.employee, len(doc.changes)
			),
			ref_type="Employee Profile Change Request",
			ref_name=doc.name,
		)
	# Live-bump every HR user's Approvals inbox so the new row appears without refresh.
	_broadcast_hr_inbox_refresh()


def _notify_employee_of_decision(doc, applied_fields):
	"""Notify the employee of the HR decision. We do NOT broadcast an inbox
	refresh from here — the outer `approve_request` / `reject_request` already
	pushes the approver's inbox, and Frappe's native list_update fires for
	Employee Profile Change Request (all HR Inbox.vue clients subscribe to it),
	so other HR users see the resolved row drop off without an extra push.
	"""
	try:
		from indian_hrms_compliance.hr.doctype.hrms_task.hrms_task import _safe_pwa_notification
	except Exception:
		return
	emp_user = frappe.db.get_value("Employee", doc.employee, "user_id")
	if not emp_user:
		return
	if doc.status == "Approved":
		msg = _("Your profile change request {0} was approved. Fields updated: {1}.").format(
			doc.name, ", ".join(applied_fields) or _("none")
		)
	else:
		msg = _("Your profile change request {0} was rejected. {1}").format(
			doc.name, doc.review_notes or ""
		)
	_safe_pwa_notification(
		to_user=emp_user,
		message=msg,
		ref_type="Employee Profile Change Request",
		ref_name=doc.name,
	)
	# Push a refresh for the employee's "My Profile Updates" history view too.
	try:
		from indian_hrms_compliance.api import _pwa_refetch

		_pwa_refetch("indian_hrms_compliance:my_profile_change_requests", user=emp_user)
	except Exception:
		pass
