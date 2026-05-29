# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate


class ProbationReview(Document):
	def validate(self):
		self._validate_period_dates()
		self._validate_extension_days()
		self._validate_employee_status()
		self._compute_new_scheduled_date()

	def _validate_period_dates(self):
		if self.period_evaluated_from and self.period_evaluated_to:
			if getdate(self.period_evaluated_to) < getdate(self.period_evaluated_from):
				frappe.throw(_("Period 'To' date cannot be before 'From' date."))

	def _validate_extension_days(self):
		if self.recommendation == "Extend Probation":
			if not self.extension_days or self.extension_days <= 0:
				frappe.throw(_("Extension Days must be a positive number when extending probation."))

	def _validate_employee_status(self):
		# Only meaningful for Active employees on probation (or about to be).
		emp_status = frappe.db.get_value("Employee", self.employee, "status")
		if emp_status not in ("Active",):
			frappe.throw(
				_("Probation Review can only be filed for Active Employees. {0} is currently {1}.").format(
					self.employee, emp_status
				)
			)

	def _compute_new_scheduled_date(self):
		if self.recommendation == "Extend Probation" and self.extension_days:
			current = frappe.db.get_value("Employee", self.employee, "scheduled_confirmation_date")
			base = getdate(current) if current else getdate(self.review_date)
			self.new_scheduled_confirmation_date = add_days(base, self.extension_days)
		else:
			self.new_scheduled_confirmation_date = None

	def on_submit(self):
		if self.recommendation == "Confirm":
			self._apply_confirm()
		elif self.recommendation == "Extend Probation":
			self._apply_extend()
		elif self.recommendation == "Release":
			self._apply_release()

		if self.generate_confirmation_letter and self.recommendation in (
			"Confirm",
			"Extend Probation",
			"Release",
		):
			self._create_letter()

	def on_cancel(self):
		# Best-effort: cancel any linked Appointment Letter draft we generated.
		if self.confirmation_letter and frappe.db.exists("Appointment Letter", self.confirmation_letter):
			letter = frappe.get_doc("Appointment Letter", self.confirmation_letter)
			# If it's still draft and was auto-generated, delete it.
			if getattr(letter, "probation_review", None) == self.name:
				frappe.delete_doc(
					"Appointment Letter", letter.name, force=1, ignore_permissions=True
				)
				self.db_set("confirmation_letter", None, update_modified=False)

	def _apply_confirm(self):
		frappe.db.set_value(
			"Employee",
			self.employee,
			{
				"confirmation_status": "Confirmed",
				"final_confirmation_date": self.review_date,
			},
			update_modified=True,
		)

	def _apply_extend(self):
		frappe.db.set_value(
			"Employee",
			self.employee,
			{
				"confirmation_status": "Extended",
				"scheduled_confirmation_date": self.new_scheduled_confirmation_date,
			},
			update_modified=True,
		)

	def _apply_release(self):
		# Mark the Employee. The actual Separation workflow is HR-initiated;
		# we don't auto-create a Separation record here.
		frappe.db.set_value(
			"Employee",
			self.employee,
			"confirmation_status",
			"Released",
			update_modified=True,
		)

	def _create_letter(self):
		"""Create a Draft Appointment Letter typed to the recommendation.
		HR picks the template and finalises content."""
		letter_type_map = {
			"Confirm": "Confirmation",
			"Extend Probation": "Probation Extension",
			"Release": "Release",
		}
		letter_type = letter_type_map[self.recommendation]
		applicant_name = self.employee_name or self.employee
		letter = frappe.get_doc(
			{
				"doctype": "Appointment Letter",
				"job_applicant": "",
				"applicant_name": applicant_name,
				"appointment_date": self.review_date,
				"company": self.company,
				"letter_type": letter_type,
				"probation_review": self.name,
			}
		)
		letter.insert(ignore_permissions=True, ignore_mandatory=True)
		self.db_set("confirmation_letter", letter.name, update_modified=False)
		frappe.msgprint(
			_("Created Draft {0} Letter: {1}. HR should now pick a template and finalise content.").format(
				letter_type, frappe.utils.get_link_to_form("Appointment Letter", letter.name)
			)
		)


def create_probation_review_reminders():
	"""Scheduler (daily): for Employees in Probation whose
	scheduled_confirmation_date falls within the lookahead window from today,
	create a ToDo for the reports_to manager + HR users, unless a submitted
	Probation Review already exists or a reminder ToDo is already open.

	The lookahead window is HR Settings.probation_review_reminder_window_days
	(default 30)."""
	from frappe.utils import today

	today_d = getdate(today())
	window = int(
		frappe.db.get_single_value("HR Settings", "probation_review_reminder_window_days") or 30
	)
	if window <= 0:
		window = 30
	cutoff = add_days(today_d, window)

	employees = frappe.get_all(
		"Employee",
		filters={
			"status": "Active",
			"confirmation_status": "Probation",
			"scheduled_confirmation_date": ("between", [today_d, cutoff]),
		},
		fields=["name", "employee_name", "scheduled_confirmation_date", "reports_to"],
	)

	for emp in employees:
		if frappe.db.exists("Probation Review", {"employee": emp.name, "docstatus": 1}):
			continue
		# Skip if an open reminder ToDo already exists for this employee.
		existing = frappe.db.exists(
			"ToDo",
			{
				"reference_type": "Employee",
				"reference_name": emp.name,
				"status": "Open",
				"description": ("like", "%Probation review%"),
			},
		)
		if existing:
			continue

		recipients = set()
		if emp.reports_to:
			manager_user = frappe.db.get_value("Employee", emp.reports_to, "user_id")
			if manager_user:
				recipients.add(manager_user)
		hr_users = frappe.get_all("Has Role", filters={"role": "HR Manager"}, pluck="parent")
		recipients.update(filter(lambda u: u and u != "Administrator", hr_users))

		description = _(
			"Probation review due for <a href='/app/employee/{0}'>{1}</a> by {2}. "
			"Please file a Probation Review."
		).format(emp.name, emp.employee_name or emp.name, emp.scheduled_confirmation_date)

		for user in recipients:
			try:
				frappe.get_doc(
					{
						"doctype": "ToDo",
						"allocated_to": user,
						"description": description,
						"reference_type": "Employee",
						"reference_name": emp.name,
						"date": emp.scheduled_confirmation_date,
						"priority": "Medium",
					}
				).insert(ignore_permissions=True)
			except Exception:
				frappe.log_error(
					title=f"Probation reminder ToDo failed for {emp.name}",
					message=frappe.get_traceback(),
				)
