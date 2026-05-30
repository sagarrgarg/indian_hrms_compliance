# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""DPDP Access Logger — Phase 6D.

Records who accessed which sensitive PII field. Never logs the VALUE —
only the field NAME + record reference + access metadata.

Two integration surfaces:

  log_field_access(...)             — direct programmatic call, used by
                                       reports / exports / API endpoints.
  log_form_load_access(doc, method) — doc_event 'on_load' wrapper. For
                                       each sensitive field defined for
                                       this doctype, logs a Read.

Throttle: at most 1 log per (user × doctype × record × field) per
HR Settings.dpdp_access_log_throttle_seconds (default 3600 = 1 hour).
This prevents log floods when a user refreshes a form repeatedly.

Kill switch: HR Settings.dpdp_enable_access_logging — when 0, all calls
silently no-op.
"""

import frappe
from frappe.utils import now_datetime


# Registry of sensitive fields per doctype. Keep ordered by sensitivity
# so an HR audit produces a stable, reviewable trace.
SENSITIVE_FIELDS_BY_DOCTYPE = {
	"Employee": [
		"pan_number",
		"aadhaar_last_4",
		"bank_ac_no",
		"uan_number",
		"esic_ip_number",
		"nps_pran",
		"ifsc_code",
	],
	"Salary Slip": [
		"gross_pay",
		"net_pay",
		"total_deduction",
	],
	"Form 16": [
		"employee_pan",
		"gross_salary",
		"tds_deducted",
		"taxable_income",
	],
	"Salary Structure Assignment": [
		"base",
		"variable",
	],
	"Employee Tax Exemption Declaration": [
		"total_declared_amount",
	],
	"Employee Tax Exemption Proof Submission": [
		"house_rent_payment_amount",
	],
	"POSH Complaint": [
		"incident_description",
		"complainant",
		"accused",
	],
}


def _hr_setting(field, default=None):
	"""Safe HR Settings read — returns default if field doesn't exist."""
	try:
		meta = frappe.get_meta("HR Settings")
		if not meta.get_field(field):
			return default
		val = frappe.db.get_single_value("HR Settings", field)
		return default if val in (None, "") else val
	except Exception:
		return default


def _is_logging_enabled():
	"""Check the kill switch."""
	val = _hr_setting("dpdp_enable_access_logging", 1)
	try:
		return bool(int(val))
	except Exception:
		return True


def _throttle_seconds():
	val = _hr_setting("dpdp_access_log_throttle_seconds", 3600)
	try:
		return int(val)
	except Exception:
		return 3600


def _request_metadata():
	"""Pull IP + user-agent from the current request, gracefully."""
	ip = None
	ua = None
	ctx = None
	try:
		ip = getattr(frappe.local, "request_ip", None)
	except Exception:
		pass
	try:
		if hasattr(frappe, "get_request_header"):
			ua = frappe.get_request_header("User-Agent")
	except Exception:
		pass
	try:
		if hasattr(frappe.local, "request") and frappe.local.request is not None:
			ctx = getattr(frappe.local.request, "path", None) or getattr(
				frappe.local.request, "url", None
			)
	except Exception:
		pass
	return ip, ua, ctx


def _throttle_key(user, doctype, record, field):
	# frappe.cache key — short prefix to namespace; readability over compactness.
	return f"dpal:{user}:{doctype}:{record}:{field}"


def _is_throttled(user, doctype, record, field):
	try:
		ts = frappe.cache().get_value(_throttle_key(user, doctype, record, field))
		return bool(ts)
	except Exception:
		return False


def _set_throttle(user, doctype, record, field):
	try:
		ttl = _throttle_seconds()
		frappe.cache().set_value(
			_throttle_key(user, doctype, record, field),
			now_datetime().isoformat(),
			expires_in_sec=ttl,
		)
	except Exception:
		pass


def log_field_access(
	subject_doctype,
	subject_record,
	subject_employee,
	field_accessed,
	access_type="Read",
	purpose_code=None,
	request_context=None,
):
	"""Insert a Data Access Log row. Errors are caught + logged — must
	never block the underlying read.

	subject_doctype : str  — e.g. "Salary Slip"
	subject_record  : str  — the document name
	subject_employee: str  — Employee whose data this is
	field_accessed  : str  — field NAME only (NEVER the value)
	access_type     : str  — Read / Export / Print / Email
	purpose_code    : str  — optional Data Consent Purpose code
	request_context : str  — optional URL/report identifier
	"""
	try:
		if not _is_logging_enabled():
			return
		user = frappe.session.user
		if not user or user == "Guest":
			return

		# Throttle per (user × doctype × record × field).
		if _is_throttled(user, subject_doctype, subject_record, field_accessed):
			return

		ip, ua, ctx_from_request = _request_metadata()
		if not request_context:
			request_context = ctx_from_request

		doc = frappe.get_doc(
			{
				"doctype": "Data Access Log",
				"accessed_on": now_datetime(),
				"accessed_by": user,
				"subject_employee": subject_employee,
				"subject_doctype": subject_doctype,
				"subject_record": subject_record,
				"field_accessed": field_accessed,
				"access_type": access_type,
				"ip_address": ip,
				"user_agent": ua,
				"purpose_code": purpose_code,
				"request_context": (request_context or "")[:140] if request_context else None,
			}
		)
		doc.insert(ignore_permissions=True)
		_set_throttle(user, subject_doctype, subject_record, field_accessed)
	except Exception:
		# Audit-log writes must NEVER break the underlying read. Eat all errors.
		try:
			frappe.log_error(
				title=f"DPDP access log failed: {subject_doctype}/{field_accessed}",
				message=frappe.get_traceback(),
			)
		except Exception:
			pass


def log_form_load_access(doc, method=None):
	"""doc_event on_load hook — log each sensitive field defined for this
	doctype as a Read.

	Skip rules:
	  - Skip if user is Administrator (otherwise logs flood with admin reads).
	  - Skip if user is the doc's owner AND we're on Employee.pan_number
	    (employees viewing own PII is OK; logged separately at Export).
	  - Skip if logging disabled via kill switch.
	  - Skip if throttled (handled inside log_field_access).
	"""
	try:
		if not _is_logging_enabled():
			return
		user = frappe.session.user
		if not user or user in ("Guest", "Administrator"):
			return

		doctype = doc.doctype
		fields = SENSITIVE_FIELDS_BY_DOCTYPE.get(doctype)
		if not fields:
			return

		# Best-effort: find the subject_employee on the doc.
		subject_employee = _resolve_subject_employee(doc)

		for fn in fields:
			# Employee.pan_number: skip if owner viewing self.
			if doctype == "Employee" and fn == "pan_number" and doc.owner == user:
				continue
			# Skip if the field isn't actually present on this record
			# (Custom Fields / fetch_from delays / etc.).
			try:
				if not hasattr(doc, fn):
					continue
			except Exception:
				pass
			log_field_access(
				subject_doctype=doctype,
				subject_record=doc.name,
				subject_employee=subject_employee or doc.name,
				field_accessed=fn,
				access_type="Read",
			)
	except Exception:
		try:
			frappe.log_error(
				title=f"DPDP form-load access logger failed: {doc.doctype}/{doc.name}",
				message=frappe.get_traceback(),
			)
		except Exception:
			pass


def _resolve_subject_employee(doc):
	"""Best-effort: which Employee is this doc about?"""
	if doc.doctype == "Employee":
		return doc.name
	# Common fieldnames where the subject Employee lives.
	for fn in ("employee", "complainant", "applicant", "subject_employee"):
		if hasattr(doc, fn):
			val = doc.get(fn)
			if val:
				return val
	return None
