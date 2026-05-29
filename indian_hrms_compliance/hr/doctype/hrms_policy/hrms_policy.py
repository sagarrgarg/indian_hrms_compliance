# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days


class HRMSPolicy(Document):
	def validate(self):
		if self.status == "Active" and not self.effective_date:
			frappe.throw(_("Effective Date is required when publishing the policy (status = Active)."))
		if self.superseded_by and self.superseded_by == self.name:
			frappe.throw(_("A policy cannot supersede itself."))
		if self.acknowledgement_due_days is not None and self.acknowledgement_due_days < 0:
			frappe.throw(_("Acknowledgement Due (days) cannot be negative."))

	def on_update(self):
		if self._just_activated() and self.requires_acknowledgement:
			self.create_acknowledgements()

	def _just_activated(self):
		if self.status != "Active":
			return False
		before = self.get_doc_before_save()
		# Fresh insert with status=Active counts as just-activated.
		if not before:
			return True
		return before.status != "Active"

	def create_acknowledgements(self):
		"""For each applicable Active Employee without an existing acknowledgement
		for this policy version, create a Pending record and notify."""
		employees = self._get_applicable_employees()
		due = add_days(self.effective_date, self.acknowledgement_due_days or 0)
		signed_text = _(
			"I acknowledge that I have read and understood the policy '{0}' version {1} "
			"effective {2}, and agree to abide by it."
		).format(self.policy_name, self.version, self.effective_date)

		created = 0
		for emp in employees:
			if frappe.db.exists(
				"Employee Policy Acknowledgement",
				{"employee": emp.name, "policy": self.name},
			):
				continue
			ack = frappe.get_doc(
				{
					"doctype": "Employee Policy Acknowledgement",
					"employee": emp.name,
					"policy": self.name,
					"due_date": due,
					"signed_text": signed_text,
					"status": "Pending",
				}
			)
			ack.insert(ignore_permissions=True)
			created += 1
			self._notify_employee(emp, ack)

		if created:
			frappe.msgprint(
				_("Created {0} pending acknowledgement(s) for this policy.").format(created)
			)

	def _get_applicable_employees(self):
		filters = {"status": "Active"}
		if not self.applicable_to_all:
			companies = [row.company for row in (self.applicable_companies or [])]
			if not companies:
				return []
			filters["company"] = ("in", companies)
		return frappe.get_all(
			"Employee",
			filters=filters,
			fields=["name", "employee_name", "company", "user_id"],
		)

	def _notify_employee(self, employee, ack_doc):
		if not employee.get("user_id"):
			return

		# Snapshot the message buffer so we can roll back anything downstream emits
		# (e.g., Push Notification decryption errors, mail dispatch warnings).
		# Without this, a broken site config in a sibling doctype bleeds into our
		# Policy save and surfaces to the user as confusing popups.
		msg_count_before = len(getattr(frappe.local, "message_log", []) or [])

		try:
			frappe.get_doc(
				{
					"doctype": "PWA Notification",
					"to_user": employee.user_id,
					"from_user": frappe.session.user or "Administrator",
					"message": _(
						"New HR Policy '{0}' (v{1}): please review and acknowledge by {2}."
					).format(self.policy_name, self.version, ack_doc.due_date),
					"reference_document_type": "Employee Policy Acknowledgement",
					"reference_document_name": ack_doc.name,
				}
			).insert(ignore_permissions=True)
		except Exception:
			# Don't block on notification failure — the Acknowledgement record is the source of truth.
			# Suppress any messages our downstream chain may have buffered.
			try:
				if hasattr(frappe.local, "message_log") and frappe.local.message_log:
					frappe.local.message_log = frappe.local.message_log[:msg_count_before]
			except Exception:
				pass
			frappe.log_error(
				title=f"HRMS Policy notification failed for {employee.name}",
				message=frappe.get_traceback(),
			)
