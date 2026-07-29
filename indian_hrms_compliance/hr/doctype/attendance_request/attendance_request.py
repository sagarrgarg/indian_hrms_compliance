# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, date_diff, format_date, get_link_to_form, getdate

from erpnext.setup.doctype.employee.employee import is_holiday

import indian_hrms_compliance
from indian_hrms_compliance.hr.utils import validate_active_employee, validate_dates


class OverlappingAttendanceRequestError(frappe.ValidationError):
	pass


class AttendanceRequest(Document):
	def validate(self):
		validate_active_employee(self.employee)
		validate_dates(self, self.from_date, self.to_date, False)
		self.validate_shifts()
		self.validate_half_day()
		self.validate_request_overlap()
		self.validate_no_attendance_to_create()

	def validate_half_day(self):
		if self.half_day:
			if not getdate(self.from_date) <= getdate(self.half_day_date) <= getdate(self.to_date):
				frappe.throw(_("Half day date should be in between from date and to date"))

	def validate_no_attendance_to_create(self):
		# When a manager APPROVES the request, this guard must not block the
		# submission just because the target state already exists (e.g. the day's
		# attendance is already in the requested status, or it's a holiday / the
		# employee is on leave). Approval is an acknowledgement; create_attendance_
		# records() safely skips days with nothing to do. The guard still applies
		# at creation time so pointless drafts are discouraged up front.
		if self.flags.get("ignore_no_attendance_to_create"):
			return
		attendance_warnings = self.get_attendance_warnings()
		attendance_request_days = date_diff(self.to_date, self.from_date) + 1
		if len(attendance_warnings) == attendance_request_days and not any(
			warning["action"] == "Overwrite" for warning in attendance_warnings
		):
			message_table = [[_("Date"), _("Reason"), _("Action")]]
			for warning in attendance_warnings:
				message_table.append(
					[
						format_date(warning["date"]),
						_(warning["reason"]),
						_(warning["action"]),
					]
				)
			frappe.msgprint(
				title=_("No attendance records to create due to following reasons"),
				msg=message_table,
				as_table=True,
				raise_exception=True,
			)

	def validate_shifts(self):
		# Auto-resolve the shift; never ask the employee for it. The self-service
		# request form has no shift field, so throwing "please mention the shift"
		# made it impossible for anyone with more than one active Shift Assignment
		# to file a request at all. Default to the most recent assignment's shift —
		# HR can change it on the Desk form if the attendance belongs elsewhere.
		if not self.shift:
			shifts = self.get_active_shifts()
			if shifts:
				self.shift = shifts[0]

	def get_active_shifts(self):
		"""Shift types assigned for the whole request period, most recent
		assignment first. Order is deterministic (the previous list(set(...))
		returned an arbitrary order, so the auto-picked shift could vary)."""
		shifts = frappe.get_all(
			"Shift Assignment",
			filters={
				"docstatus": 1,
				"status": "Active",
				"employee": self.employee,
				"start_date": ("<=", self.from_date),
				"end_date": (">=", self.to_date),
			},
			pluck="shift_type",
			order_by="start_date desc, creation desc",
		)

		seen = []
		for s in shifts:
			if s and s not in seen:
				seen.append(s)
		return seen

	def validate_request_overlap(self):
		if not self.name:
			self.name = "New Attendance Request"

		Request = frappe.qb.DocType("Attendance Request")
		query = (
			frappe.qb.from_(Request)
			.select(Request.name)
			.where(
				(Request.employee == self.employee)
				& (Request.docstatus < 2)
				& (Request.name != self.name)
				& (self.to_date >= Request.from_date)
				& (self.from_date <= Request.to_date)
			)
		)

		# A Rejected or Cancelled request is dead — it must NOT block the
		# employee from filing a corrected one for the same dates. (Legacy rows
		# with a NULL status pre-date the field and are still considered active.)
		if self.meta.has_field("status"):
			query = query.where(
				Request.status.isnull() | Request.status.notin(["Rejected", "Cancelled"])
			)

		if self.shift:
			query = query.where(Request.shift == self.shift)

		overlapping_request = query.run(as_dict=True)

		if overlapping_request:
			self.throw_overlap_error(overlapping_request[0].name)

	def throw_overlap_error(self, overlapping_request: str):
		msg = _("Employee {0} already has an Attendance Request {1} that overlaps with this period").format(
			frappe.bold(self.employee),
			get_link_to_form("Attendance Request", overlapping_request),
		)

		frappe.throw(msg, title=_("Overlapping Attendance Request"), exc=OverlappingAttendanceRequestError)

	def before_submit(self):
		# A rejected request must never be approved into attendance records.
		if self.meta.has_field("status") and self.status == "Rejected":
			frappe.throw(
				_(
					"This Attendance Request was rejected and cannot be approved. "
					"Ask the employee to raise a new request."
				)
			)

	def on_submit(self):
		self.create_attendance_records()
		# Submission = approval. Stamp it so the Desk-direct path (not just the
		# PWA approve action) reflects the correct status.
		if self.meta.has_field("status") and self.status != "Approved":
			self.db_set("status", "Approved", update_modified=False)
		self.log_skipped_days()

	def log_skipped_days(self):
		"""Leave an audit note listing days that were NOT marked, so the approver
		can see exactly what the approval did and did not do."""
		skipped = getattr(self, "_skipped_days", None)
		if not skipped:
			return
		lines = "<br>".join(
			f"{format_date(s['date'])} &mdash; {s['reason']}" for s in skipped
		)
		try:
			self.add_comment(
				"Comment",
				_("Approved. These days were skipped:<br>{0}").format(lines),
			)
		except Exception:
			frappe.log_error(title="Attendance Request skip note failed", message=frappe.get_traceback())

	def on_cancel(self):
		attendance_list = frappe.get_all(
			"Attendance", {"employee": self.employee, "attendance_request": self.name, "docstatus": 1}
		)
		if attendance_list:
			for attendance in attendance_list:
				attendance_obj = frappe.get_doc("Attendance", attendance["name"])
				attendance_obj.cancel()
		if self.meta.has_field("status"):
			self.db_set("status", "Cancelled", update_modified=False)

	def _note_skip(self, attendance_date, reason):
		"""Record a day that could not be marked, so approval can report it."""
		if not hasattr(self, "_skipped_days") or self._skipped_days is None:
			self._skipped_days = []
		self._skipped_days.append({"date": attendance_date, "reason": reason})

	def get_conflicting_shift_attendance(self, attendance_date) -> dict | None:
		"""Existing attendance on the same date for a DIFFERENT but time-overlapping
		shift.

		Attendance.validate_overlapping_shift_attendance hard-throws on insert, so
		without this pre-check one clashing day aborts an entire multi-day request
		(rolling back the days that already succeeded)."""
		if not self.shift:
			return None

		from indian_hrms_compliance.hr.doctype.shift_assignment.shift_assignment import (
			has_overlapping_timings,
		)

		rows = frappe.get_all(
			"Attendance",
			filters={
				"employee": self.employee,
				"attendance_date": attendance_date,
				"docstatus": ("<", 2),
				"shift": ("!=", self.shift),
			},
			fields=["name", "shift"],
		)
		for d in rows:
			if d.shift and has_overlapping_timings(self.shift, d.shift):
				return d
		return None

	def create_attendance_records(self):
		request_days = date_diff(self.to_date, self.from_date) + 1
		self._skipped_days = []
		for day in range(request_days):
			attendance_date = add_days(self.from_date, day)
			if not self.should_mark_attendance(attendance_date):
				continue
			# Belt-and-braces: a single unmarkable day must never abort the whole
			# request. Each day gets its own savepoint so a failure rolls back only
			# that day, leaving the rest of the approval intact.
			savepoint = f"attendance_request_day_{day}"
			try:
				frappe.db.savepoint(savepoint)
				self.create_or_update_attendance(attendance_date)
			except frappe.ValidationError as e:
				frappe.db.rollback(save_point=savepoint)
				self._note_skip(attendance_date, str(e))
				# Drop the message Frappe queued for this now-handled error so it
				# doesn't surface as a scary red toast.
				try:
					frappe.clear_last_message()
				except Exception:
					pass

	def create_or_update_attendance(self, date: str):
		doc = self.get_attendance_doc(date)
		status = self.get_attendance_status(date)

		if doc:
			# update existing attendance, change the status
			old_status = doc.status

			if old_status != status:
				doc.db_set({"status": status, "attendance_request": self.name})
				if status == "Half Day":
					doc.db_set("half_day_status", "Absent")
					text = _(
						"Changed the status from {0} to {1} and Status for Other Half to {2} via Attendance Request"
					).format(frappe.bold(old_status), frappe.bold(status), frappe.bold("Absent"))
				else:
					text = _("Changed the status from {0} to {1} via Attendance Request").format(
						frappe.bold(old_status), frappe.bold(status)
					)
				doc.add_comment(comment_type="Info", text=text)

				frappe.msgprint(
					_("Updated status from {0} to {1} for date {2} in the attendance record {3}").format(
						frappe.bold(old_status),
						frappe.bold(status),
						frappe.bold(format_date(date)),
						get_link_to_form("Attendance", doc.name),
					),
					title=_("Attendance Updated"),
				)
		else:
			# submit a new attendance record
			doc = frappe.new_doc("Attendance")
			doc.employee = self.employee
			doc.attendance_date = date
			doc.shift = self.shift
			doc.company = self.company
			doc.attendance_request = self.name
			doc.status = status
			doc.half_day_status = "Absent" if status == "Half Day" else None
			doc.insert(ignore_permissions=True)
			doc.submit()

	def should_mark_attendance(self, attendance_date: str) -> bool:
		# Check if attendance_date is a holiday
		if not self.include_holidays and is_holiday(self.employee, attendance_date):
			self._note_skip(attendance_date, _("Holiday"))
			frappe.msgprint(
				_("Attendance not submitted for {0} as it is a Holiday.").format(
					frappe.bold(format_date(attendance_date))
				)
			)
			return False

		# Check if employee is on leave. An APPROVED (submitted) Leave Application
		# wins over an attendance request for that day — the day is skipped until
		# that leave is cancelled, at which point a re-approval will mark it.
		if self.has_leave_record(attendance_date):
			self._note_skip(attendance_date, _("On approved leave"))
			frappe.msgprint(
				_("Attendance not submitted for {0} as {1} is on leave.").format(
					frappe.bold(format_date(attendance_date)), frappe.bold(self.employee)
				)
			)
			return False

		# Attendance already exists for an overlapping shift — inserting would
		# hard-throw and abort the whole request, so skip this day instead.
		conflict = self.get_conflicting_shift_attendance(attendance_date)
		if conflict:
			self._note_skip(
				attendance_date,
				_("Already marked on overlapping shift {0} ({1})").format(conflict.shift, conflict.name),
			)
			frappe.msgprint(
				_("Attendance not submitted for {0} as it is already marked on overlapping shift {1}.").format(
					frappe.bold(format_date(attendance_date)), frappe.bold(conflict.shift)
				)
			)
			return False

		return True

	def has_leave_record(self, attendance_date: str) -> str | None:
		return frappe.db.exists(
			"Leave Application",
			{
				"employee": self.employee,
				"docstatus": 1,
				"from_date": ("<=", attendance_date),
				"to_date": (">=", attendance_date),
				"status": "Approved",
			},
		)

	def get_attendance_doc(self, attendance_date: str) -> str | None:
		attendance = frappe.db.exists(
			"Attendance",
			{
				"employee": self.employee,
				"attendance_date": attendance_date,
				"docstatus": ("!=", 2),
				"shift": self.shift,
			},
		)
		return frappe.get_doc("Attendance", attendance) if attendance else None

	def get_attendance_status(self, attendance_date: str) -> str:
		if self.half_day and date_diff(getdate(self.half_day_date), getdate(attendance_date)) == 0:
			return "Half Day"
		elif self.reason == "Work From Home":
			return "Work From Home"
		else:
			return "Present"

	def status_unchanged(self, attendance_date):
		new_status = self.get_attendance_status(attendance_date)
		attendance_doc = self.get_attendance_doc(attendance_date)
		if attendance_doc and attendance_doc.status == new_status:
			return True
		return False

	def on_update(self):
		self.publish_update()

	def after_delete(self):
		self.publish_update()

	def publish_update(self):
		employee_user = frappe.db.get_value("Employee", self.employee, "user_id", cache=True)
		indian_hrms_compliance.refetch_resource("indian_hrms_compliance:my_attendance_requests", employee_user)
		indian_hrms_compliance.refetch_resource("indian_hrms_compliance:team_attendance_requests")

	@frappe.whitelist()
	def get_attendance_warnings(self) -> list:
		attendance_warnings = []
		request_days = date_diff(self.to_date, self.from_date) + 1

		for day in range(request_days):
			attendance_date = add_days(self.from_date, day)

			if not self.include_holidays and is_holiday(self.employee, attendance_date):
				attendance_warnings.append({"date": attendance_date, "reason": "Holiday", "action": "Skip"})
			elif self.has_leave_record(attendance_date):
				attendance_warnings.append({"date": attendance_date, "reason": "On Leave", "action": "Skip"})
			elif conflict := self.get_conflicting_shift_attendance(attendance_date):
				attendance_warnings.append(
					{
						"date": attendance_date,
						"reason": f"Already marked on overlapping shift {conflict.shift}",
						"record": conflict.name,
						"action": "Skip",
					}
				)
			elif self.status_unchanged(attendance_date):
				attendance_warnings.append(
					{"date": attendance_date, "reason": "Attendance status unchanged", "action": "Skip"}
				)
			else:
				attendance = self.get_attendance_doc(attendance_date)
				if attendance:
					attendance_warnings.append(
						{
							"date": attendance_date,
							"reason": "Attendance already marked",
							"record": attendance.name,
							"action": "Overwrite",
						}
					)

		return attendance_warnings
