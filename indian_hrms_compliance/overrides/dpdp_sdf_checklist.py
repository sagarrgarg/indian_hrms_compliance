# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""DPDP Significant Data Fiduciary (SDF) readiness checker — Phase 6D.

Sec 10 DPDP Act: SDFs designated by the government must
  (a) appoint a Data Protection Officer in India,
  (b) commission an independent data auditor,
  (c) carry out periodic Data Protection Impact Assessments (DPIA).

This module:
  - get_sdf_readiness_report() — whitelisted call, returns the checklist.
  - send_sdf_readiness_reminder() — monthly scheduler. PWA-notifies the
    DPO when a DPIA or audit is stale (> 11 months old) or missing.
"""

import frappe
from frappe.utils import add_days, date_diff, getdate, today


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


def _profile():
	"""Return the DPDP Compliance Profile singleton as a dict-like."""
	try:
		return frappe.get_single("DPDP Compliance Profile")
	except Exception:
		return None


def _months_since(d):
	if not d:
		return None
	try:
		days = date_diff(today(), getdate(d))
		return round(days / 30.4)
	except Exception:
		return None


@frappe.whitelist()
def get_sdf_readiness_report():
	"""Return a dict-shaped readiness assessment.

	Score heuristic (0-100):
	  +25 if DPO designated
	  +25 if DPIA in last 12 months
	  +25 if Audit in last 12 months
	  +15 if Consent Managers integrated
	  +10 if Breach Notification process documented (contact email + log URL)

	When is_designated_sdf=0, the score is still reported but the
	relevant items are presented as 'Recommended' rather than 'Required'.
	"""
	prof = _profile()
	if prof is None:
		return {
			"is_designated_sdf": False,
			"dpo_designated": False,
			"dpia_current": False,
			"audit_current": False,
			"consent_managers_setup": False,
			"breach_process_documented": False,
			"risk_score": 0,
			"messages": ["DPDP Compliance Profile is not initialised."],
		}

	is_sdf = bool(int(prof.is_designated_sdf or 0))

	dpo_designated = bool(prof.data_protection_officer)
	dpia_months = _months_since(prof.last_dpia_date)
	dpia_current = dpia_months is not None and dpia_months <= 12
	audit_months = _months_since(prof.last_audit_date)
	audit_current = audit_months is not None and audit_months <= 12
	consent_managers_setup = bool(int(prof.consent_managers_setup or 0))
	breach_process_documented = bool(
		prof.breach_notification_contact_email and prof.breach_notification_log_url
	)

	score = 0
	if dpo_designated:
		score += 25
	if dpia_current:
		score += 25
	if audit_current:
		score += 25
	if consent_managers_setup:
		score += 15
	if breach_process_documented:
		score += 10

	messages = []
	severity = "Required" if is_sdf else "Recommended"
	if not dpo_designated:
		messages.append(f"[{severity}] Designate a Data Protection Officer (DPDP Sec 10(2)(a)).")
	if not dpia_current:
		messages.append(
			f"[{severity}] Conduct a Data Protection Impact Assessment "
			f"(last: {prof.last_dpia_date or 'never'})."
		)
	if not audit_current:
		messages.append(
			f"[{severity}] Commission an independent data audit "
			f"(last: {prof.last_audit_date or 'never'})."
		)
	if not consent_managers_setup:
		messages.append(
			"[Forward-looking] Integrate with a Consent Manager (DPDP Rules — 13 Nov 2026)."
		)
	if not breach_process_documented:
		messages.append("[Required] Document a breach-notification process (72-hour DPB rule).")

	return {
		"is_designated_sdf": is_sdf,
		"dpo_designated": dpo_designated,
		"dpo_user": prof.data_protection_officer or None,
		"dpia_current": dpia_current,
		"dpia_months_since": dpia_months,
		"audit_current": audit_current,
		"audit_months_since": audit_months,
		"consent_managers_setup": consent_managers_setup,
		"breach_process_documented": breach_process_documented,
		"risk_score": score,
		"messages": messages,
	}


def send_sdf_readiness_reminder():
	"""Monthly scheduler — PWA-notify the DPO when DPIA or audit is stale.

	Silent no-op if:
	  - DPDP Compliance Profile.is_designated_sdf is 0
	  - data_protection_officer is unset
	"""
	try:
		prof = _profile()
		if prof is None:
			return
		if not int(prof.is_designated_sdf or 0):
			return
		dpo = prof.data_protection_officer
		if not dpo:
			return

		report = get_sdf_readiness_report()
		messages = []
		if not report["dpia_current"]:
			months = report.get("dpia_months_since")
			messages.append(
				f"DPIA is stale (last: {prof.last_dpia_date or 'never'}, "
				f"{months or '?'} months ago). Sec 10(2)(c) requires periodic DPIA."
			)
		if not report["audit_current"]:
			months = report.get("audit_months_since")
			messages.append(
				f"Independent data audit is stale (last: {prof.last_audit_date or 'never'}, "
				f"{months or '?'} months ago). Sec 10(2)(b) requires annual audit."
			)
		if not messages:
			return

		full_message = (
			f"SDF readiness reminder — risk score {report['risk_score']}/100.\n\n"
			+ "\n".join(f"• {m}" for m in messages)
		)
		_safe_pwa_notification(
			to_user=dpo,
			message=full_message,
			ref_type="DPDP Compliance Profile",
			ref_name="DPDP Compliance Profile",
		)
	except Exception:
		frappe.log_error(
			title="DPDP SDF readiness reminder failed",
			message=frappe.get_traceback(),
		)


def _safe_pwa_notification(to_user, message, ref_type, ref_name):
	"""Mirror of overrides/grievance_workflow._safe_pwa_notification."""
	msg_count_before = len(getattr(frappe.local, "message_log", []) or [])
	try:
		frappe.get_doc(
			{
				"doctype": "PWA Notification",
				"to_user": to_user,
				"from_user": frappe.session.user or "Administrator",
				"message": message,
				"reference_document_type": ref_type,
				"reference_document_name": ref_name,
			}
		).insert(ignore_permissions=True)
	except Exception:
		try:
			if hasattr(frappe.local, "message_log") and frappe.local.message_log:
				frappe.local.message_log = frappe.local.message_log[:msg_count_before]
		except Exception:
			pass
		frappe.log_error(
			title="DPDP SDF PWA notification failed", message=frappe.get_traceback()
		)
