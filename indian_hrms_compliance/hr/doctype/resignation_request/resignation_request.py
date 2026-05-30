# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, get_link_to_form, getdate, today


# When the workflow lands here, we materialise the Employee Separation +
# stamp Employee.resignation_letter_date. Mirrors Job Requisition pattern
# (workflow approval triggers downstream record creation).
APPROVED_STATE = "Approved"


class ResignationRequest(Document):
	def autoname(self):
		# Format embeds company + employee + date so multi-Co/repeat resignations
		# don't collide. Fallback when format fields not yet set.
		from frappe.model.naming import make_autoname

		if self.company and self.employee and self.submission_date:
			self.name = f"RES-{self.company}-{self.employee}-{self.submission_date}"
		else:
			self.name = make_autoname("RES-.YYYY.-.#####")

	def before_insert(self):
		self._derive_initiated_by()
		self._derive_intended_last_working_date()
		# Seed workflow state on first save so the form shows it.
		if not self.workflow_state:
			self.workflow_state = "Draft"

	def validate(self):
		self._derive_initiated_by()
		self._derive_intended_last_working_date()
		self._validate_dates()
		self._validate_notice_offered()
		self._validate_disposition_consistency()
		self._stamp_state_dates()

	def _derive_initiated_by(self):
		# Termination / Death / End of Contract / Retirement = Employer.
		# Resignation = Employee. Always wins over manual entry — it's derived.
		if self.request_type == "Resignation":
			self.initiated_by = "Employee"
		else:
			self.initiated_by = "Employer"

	def _derive_intended_last_working_date(self):
		if self.submission_date and self.notice_offered_days is not None:
			# Only auto-compute if not manually overridden, OR if the manual value
			# is still the auto-value from a previous notice_offered_days.
			computed = add_days(self.submission_date, int(self.notice_offered_days or 0))
			if not self.intended_last_working_date:
				self.intended_last_working_date = computed

	def _validate_dates(self):
		if self.submission_date and self.intended_last_working_date:
			if getdate(self.intended_last_working_date) < getdate(self.submission_date):
				frappe.throw(
					_("Intended Last Working Date cannot be earlier than Submission Date.")
				)

	def _validate_notice_offered(self):
		if self.notice_offered_days is not None and self.notice_offered_days < 0:
			frappe.throw(_("Notice Offered cannot be negative."))

	def _validate_disposition_consistency(self):
		# Short Notice only makes sense when offered < required.
		if (
			self.notice_disposition == "Short Notice (recovery)"
			and self.notice_required_days
			and self.notice_offered_days is not None
			and self.notice_offered_days >= self.notice_required_days
		):
			frappe.throw(
				_(
					"Notice Disposition is 'Short Notice (recovery)' but Notice Offered ({0}) "
					"is not less than Notice Required ({1}). Set disposition to 'Will Serve in Full' "
					"or reduce Notice Offered."
				).format(self.notice_offered_days, self.notice_required_days)
			)
		# Pay in Lieu only makes sense for Employer-initiated cases (employer waiving served notice).
		if (
			self.notice_disposition == "Pay in Lieu of Notice"
			and self.initiated_by == "Employee"
		):
			frappe.throw(
				_(
					"Pay in Lieu of Notice is for Employer-initiated cases (Termination / End of Contract). "
					"Employee-initiated resignations use 'Short Notice (recovery)' or 'Will Serve in Full'."
				)
			)

	def _stamp_state_dates(self):
		# Track the moments the workflow advanced — useful for SLAs and letters.
		before = self.get_doc_before_save()
		prev_state = getattr(before, "workflow_state", None) if before else None
		if self.workflow_state and self.workflow_state != prev_state:
			if self.workflow_state == "Pending HR Approval" and not self.manager_acknowledgement_date:
				self.manager_acknowledgement_date = today()
			if self.workflow_state == APPROVED_STATE and not self.hr_approval_date:
				self.hr_approval_date = today()

	def on_update(self):
		if _was_just_approved(self):
			self._apply_approval_side_effects()

	def _apply_approval_side_effects(self):
		"""Stamp the Employee and materialise the linked Employee Separation.
		Idempotent — skipped silently if the linkage is already set."""
		# 1. Stamp Employee.resignation_letter_date (preserve any earlier value
		# only if it's the same — otherwise the new request wins).
		frappe.db.set_value(
			"Employee",
			self.employee,
			"resignation_letter_date",
			self.submission_date,
			update_modified=True,
		)

		# 2. Create Employee Separation if not already linked.
		if not self.linked_employee_separation:
			sep = frappe.get_doc(
				{
					"doctype": "Employee Separation",
					"employee": self.employee,
					"company": self.company,
					"boarding_begins_on": self.submission_date,
					"resignation_letter_date": self.submission_date,
					"boarding_status": "Pending",
				}
			)
			sep.insert(ignore_permissions=True)
			self.db_set("linked_employee_separation", sep.name, update_modified=False)
			frappe.msgprint(
				_("Created Employee Separation {0} for this resignation.").format(
					get_link_to_form("Employee Separation", sep.name)
				)
			)

		# 3. Notify HR + Reports To
		_notify_separation_kickoff(self)


def _was_just_approved(doc):
	"""True iff workflow_state transitioned to APPROVED_STATE on this save."""
	if not getattr(doc, "workflow_state", None) or doc.workflow_state != APPROVED_STATE:
		return False
	before = doc.get_doc_before_save()
	if not before:
		# Fresh insert directly into Approved (HR backdating a record); count it.
		return True
	return getattr(before, "workflow_state", None) != APPROVED_STATE


def _notify_separation_kickoff(doc):
	"""Best-effort PWA Notification + email to Reports To + HR users."""
	recipients = set()
	reports_to_user = None
	if doc.employee:
		reports_to = frappe.db.get_value("Employee", doc.employee, "reports_to")
		if reports_to:
			reports_to_user = frappe.db.get_value("Employee", reports_to, "user_id")
			if reports_to_user:
				recipients.add(reports_to_user)
	hr_users = frappe.get_all("Has Role", filters={"role": "HR Manager"}, pluck="parent")
	recipients.update(u for u in hr_users if u and u not in ("Administrator", "Guest"))
	if not recipients:
		return

	msg = _(
		"{0} resignation/termination approved for {1} ({2}). Last working day: {3}."
	).format(
		doc.request_type,
		doc.employee_name or doc.employee,
		doc.company,
		doc.intended_last_working_date,
	)
	for user in recipients:
		_safe_pwa_notification(user, msg, "Resignation Request", doc.name)


def _safe_pwa_notification(to_user, message, ref_type, ref_name):
	"""Insert a PWA Notification suppressing any sibling-chain errors —
	the resignation record itself is the source of truth."""
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
			title="Resignation Request notification failed",
			message=frappe.get_traceback(),
		)
