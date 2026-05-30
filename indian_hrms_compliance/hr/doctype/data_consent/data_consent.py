# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Data Consent — record of consent given by an Employee for a Purpose.

Phase 6D. One row per (Employee × Purpose × consent_version).

Withdrawal does NOT delete the row — audit trail per Sec 13 DPDP Act.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, today


def _hr_setting(field, default=None):
	"""Safe HR Settings read — returns default if field doesn't exist."""
	meta = frappe.get_meta("HR Settings")
	if not meta.get_field(field):
		return default
	val = frappe.db.get_single_value("HR Settings", field)
	return default if val in (None, "") else val


class DataConsent(Document):
	def validate(self):
		self._set_expires_on()
		self._snapshot_notice()
		self._stamp_withdrawal_date()

	def _set_expires_on(self):
		if self.expires_on:
			return
		years = None
		if self.purpose:
			years = frappe.db.get_value(
				"Data Consent Purpose", self.purpose, "retention_period_years"
			)
		if not years:
			years = _hr_setting("dpdp_data_retention_years", 8)
		try:
			years = int(years or 8)
		except Exception:
			years = 8
		if self.granted_on and years > 0:
			# years × 365 — approximate, sufficient for retention windowing
			self.expires_on = add_days(self.granted_on, years * 365)

	def _snapshot_notice(self):
		if self.notice_shown_html:
			return  # don't overwrite once snapshotted
		if not self.purpose:
			return
		template = frappe.db.get_value(
			"Data Consent Purpose", self.purpose, "notice_template"
		)
		if not template:
			return
		try:
			rendered = frappe.render_template(
				template,
				{
					"employee_name": self.employee_name or self.employee or "",
					"company": self.company or "",
					"purpose_name": frappe.db.get_value(
						"Data Consent Purpose", self.purpose, "purpose_name"
					)
					or self.purpose,
				},
			)
			self.notice_shown_html = rendered
		except Exception:
			# Template rendering should never block consent capture.
			self.notice_shown_html = template
			frappe.log_error(
				title=f"Data Consent notice render failed: {self.name or '(new)'}",
				message=frappe.get_traceback(),
			)

	def _stamp_withdrawal_date(self):
		if self.consent_status == "Withdrawn" and not self.withdrawn_on:
			self.withdrawn_on = today()


@frappe.whitelist()
def withdraw_consent(name, reason=None):
	"""Whitelisted helper called from the JS 'Withdraw Consent' button.

	Sets status=Withdrawn, withdrawn_on=today, withdrawal_reason=<reason>.
	"""
	doc = frappe.get_doc("Data Consent", name)
	# Permission: HR Manager / HR User / owner-Employee
	if not (
		frappe.has_permission("Data Consent", "write", doc=doc)
		or doc.owner == frappe.session.user
	):
		frappe.throw(_("You are not permitted to withdraw this consent."))
	if doc.consent_status == "Withdrawn":
		return doc.name
	doc.consent_status = "Withdrawn"
	doc.withdrawn_on = today()
	if reason:
		doc.withdrawal_reason = reason
	doc.save(ignore_permissions=True)
	frappe.msgprint(_("Consent withdrawn."))
	return doc.name
