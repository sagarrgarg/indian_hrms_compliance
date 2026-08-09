# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import (
	add_days,
	cint,
	create_batch,
	cstr,
	format_date,
	get_datetime,
	get_link_to_form,
	getdate,
	nowdate,
)
from frappe.utils.background_jobs import get_job

import indian_hrms_compliance
from indian_hrms_compliance.hr.doctype.shift_assignment.shift_assignment import has_overlapping_timings
from indian_hrms_compliance.hr.utils import (
	get_holiday_dates_for_employee,
	get_holidays_for_employee,
	validate_active_employee,
	validate_employment_dates,
)


class DuplicateAttendanceError(frappe.ValidationError):
	pass


class OverlappingShiftAttendanceError(frappe.ValidationError):
	pass


class Attendance(Document):
	def autoname(self):
		# {FY2}/{employee}/{MM}/#### by attendance date; any failure falls back to
		# the doctype's naming_series so a record can always be created.
		try:
			from indian_hrms_compliance.utils.naming import employee_series_name

			self.name = employee_series_name(self, "attendance_date")
		except Exception:
			frappe.log_error(title="Attendance autoname fallback", message=frappe.get_traceback())

	def before_insert(self):
		if self.half_day_status == "":
			self.half_day_status = None

	def validate(self):
		from erpnext.controllers.status_updater import validate_status

		validate_status(self.status, ["Present", "Absent", "On Leave", "Half Day", "Work From Home"])
		validate_active_employee(self.employee)
		self.validate_attendance_date()
		self.validate_duplicate_record()
		self.validate_overlapping_shift_attendance()
		self.validate_employee_status()
		self.check_leave_record()

	def on_cancel(self):
		self.unlink_attendance_from_checkins()

	def validate_attendance_date(self):
		validate_employment_dates(self.employee, self.attendance_date)

	def validate_duplicate_record(self):
		duplicate = self.get_duplicate_attendance_record()

		if duplicate:
			frappe.throw(
				_("Attendance for employee {0} is already marked for the date {1}: {2}").format(
					frappe.bold(self.employee),
					frappe.bold(format_date(self.attendance_date)),
					get_link_to_form("Attendance", duplicate),
				),
				title=_("Duplicate Attendance"),
				exc=DuplicateAttendanceError,
			)

	def get_duplicate_attendance_record(self) -> str | None:
		Attendance = frappe.qb.DocType("Attendance")
		query = (
			frappe.qb.from_(Attendance)
			.select(Attendance.name)
			.where(
				(Attendance.employee == self.employee)
				& (Attendance.docstatus < 2)
				& (Attendance.attendance_date == self.attendance_date)
				& (Attendance.name != self.name)
				& (
					Attendance.half_day_status.isnull()
					| (Attendance.half_day_status == "")
					| (Attendance.modify_half_day_status == 0)
				)
			)
			.for_update()
		)

		if self.shift:
			query = query.where(
				((Attendance.shift.isnull()) | (Attendance.shift == ""))
				| (
					((Attendance.shift.isnotnull()) | (Attendance.shift != ""))
					& (Attendance.shift == self.shift)
				)
			)

		duplicate = query.run(pluck=True)

		return duplicate[0] if duplicate else None

	def validate_overlapping_shift_attendance(self):
		attendance = self.get_overlapping_shift_attendance()

		if attendance:
			frappe.throw(
				_("Attendance for employee {0} is already marked for an overlapping shift {1}: {2}").format(
					frappe.bold(self.employee),
					frappe.bold(attendance.shift),
					get_link_to_form("Attendance", attendance.name),
				),
				title=_("Overlapping Shift Attendance"),
				exc=OverlappingShiftAttendanceError,
			)

	def get_overlapping_shift_attendance(self) -> dict:
		if not self.shift:
			return {}

		Attendance = frappe.qb.DocType("Attendance")
		same_date_attendance = (
			frappe.qb.from_(Attendance)
			.select(Attendance.name, Attendance.shift)
			.where(
				(Attendance.employee == self.employee)
				& (Attendance.docstatus < 2)
				& (Attendance.attendance_date == self.attendance_date)
				& (Attendance.shift != self.shift)
				& (Attendance.name != self.name)
			)
		).run(as_dict=True)

		for d in same_date_attendance:
			if has_overlapping_timings(self.shift, d.shift):
				return d

		return {}

	def validate_employee_status(self):
		if frappe.db.get_value("Employee", self.employee, "status") == "Inactive":
			frappe.throw(_("Cannot mark attendance for an Inactive employee {0}").format(self.employee))

	def check_leave_record(self):
		LeaveApplication = frappe.qb.DocType("Leave Application")
		leave_record = (
			frappe.qb.from_(LeaveApplication)
			.select(
				LeaveApplication.leave_type,
				LeaveApplication.half_day,
				LeaveApplication.half_day_date,
				LeaveApplication.name,
			)
			.where(
				(LeaveApplication.employee == self.employee)
				& (self.attendance_date >= LeaveApplication.from_date)
				& (self.attendance_date <= LeaveApplication.to_date)
				& (LeaveApplication.status == "Approved")
				& (LeaveApplication.docstatus == 1)
			)
		).run(as_dict=True)

		if leave_record:
			for d in leave_record:
				self.leave_type = d.leave_type
				self.leave_application = d.name
				if d.half_day_date == getdate(self.attendance_date):
					self.status = "Half Day"
					frappe.msgprint(
						_("Employee {0} on Half day on {1}").format(
							self.employee, format_date(self.attendance_date)
						)
					)
				else:
					self.status = "On Leave"
					frappe.msgprint(
						_("Employee {0} is on Leave on {1}").format(
							self.employee, format_date(self.attendance_date)
						)
					)

		if self.status in ("On Leave", "Half Day"):
			if not leave_record:
				self.modify_half_day_status = 0
				self.half_day_status = "Absent"
				frappe.msgprint(
					_("No leave record found for employee {0} on {1}").format(
						self.employee, format_date(self.attendance_date)
					),
					alert=1,
				)
		elif self.leave_type:
			self.leave_type = None
			self.leave_application = None

	def validate_employee(self):
		emp = frappe.db.sql(
			"select name from `tabEmployee` where name = %s and status = 'Active'", self.employee
		)
		if not emp:
			frappe.throw(_("Employee {0} is not active or does not exist").format(self.employee))

	def unlink_attendance_from_checkins(self):
		EmployeeCheckin = frappe.qb.DocType("Employee Checkin")
		linked_logs = (
			frappe.qb.from_(EmployeeCheckin)
			.select(EmployeeCheckin.name)
			.where(EmployeeCheckin.attendance == self.name)
			.for_update()
			.run(as_dict=True)
		)

		if linked_logs:
			(
				frappe.qb.update(EmployeeCheckin)
				.set("attendance", "")
				.where(EmployeeCheckin.attendance == self.name)
			).run()

			frappe.msgprint(
				msg=_("Unlinked Attendance record from Employee Checkins: {}").format(
					", ".join(get_link_to_form("Employee Checkin", log.name) for log in linked_logs)
				),
				title=_("Unlinked logs"),
				indicator="blue",
				is_minimizable=True,
				wide=True,
			)

	def on_update(self):
		self.publish_update()

	def after_delete(self):
		self.publish_update()

	def publish_update(self):
		employee_user = frappe.db.get_value("Employee", self.employee, "user_id", cache=True)
		indian_hrms_compliance.refetch_resource("indian_hrms_compliance:attendance_calendar_events", employee_user)


@frappe.whitelist()
def get_events(start, end, filters=None):
	employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user})
	if not employee:
		return []
	if isinstance(filters, str):
		import json

		filters = json.loads(filters)
	if not filters:
		filters = []
	filters.append(["attendance_date", "between", [get_datetime(start).date(), get_datetime(end).date()]])
	attendance_records = add_attendance(filters)
	add_holidays(attendance_records, start, end, employee)
	return attendance_records


def add_attendance(filters):
	attendance = frappe.get_list(
		"Attendance",
		fields=[
			"name",
			"'Attendance' as doctype",
			"attendance_date",
			"employee_name",
			"status",
			"docstatus",
		],
		filters=filters,
	)
	for record in attendance:
		record["title"] = f"{record.employee_name} : {record.status}"
	return attendance


def add_holidays(events, start, end, employee=None):
	holidays = get_holidays_for_employee(employee, start, end)
	if not holidays:
		return

	for holiday in holidays:
		events.append(
			{
				"doctype": "Holiday",
				"attendance_date": holiday.holiday_date,
				"title": _("Holiday") + ": " + cstr(holiday.description),
				"name": holiday.name,
				"allDay": 1,
			}
		)


def mark_attendance(
	employee,
	attendance_date,
	status,
	shift=None,
	leave_type=None,
	late_entry=False,
	early_exit=False,
	half_day_status=None,
):
	savepoint = "attendance_creation"

	try:
		frappe.db.savepoint(savepoint)
		attendance = frappe.new_doc("Attendance")
		attendance.update(
			{
				"doctype": "Attendance",
				"employee": employee,
				"attendance_date": attendance_date,
				"status": status,
				"shift": shift,
				"leave_type": leave_type,
				"late_entry": late_entry,
				"early_exit": early_exit,
				"half_day_status": half_day_status,
			}
		)
		attendance.insert()
		attendance.submit()
	except (DuplicateAttendanceError, OverlappingShiftAttendanceError):
		frappe.db.rollback(save_point=savepoint)
		return

	return attendance.name


@frappe.whitelist()
def mark_bulk_attendance(data: str | dict):
	import json

	if isinstance(data, str):
		data = json.loads(data)
	data = frappe._dict(data)
	if not data.unmarked_days:
		frappe.throw(_("Please select a date."))
		return
	if len(data.unmarked_days) > 10 or frappe.flags.test_bg_job:
		job_id = f"process_bulk_attendance_for_employee_{data.employee}"
		job = frappe.enqueue(
			process_bulk_attendance_in_batches, data=data, job_id=job_id, timeout=600, deduplicate=True
		)
		if job:
			message = _(
				"Bulk attendance marking is queued with a background job. It may take a while. You can monitor the job status {0}"
			).format(get_link_to_form("RQ Job", job.id, label="here"))
		else:
			message = _(
				"Bulk attendance marking is already in progress for employee {0}. You can monitor the job status {1}"
			).format(frappe.bold(data.employee), get_link_to_form("RQ Job", get_job(job_id).id, label="here"))
		frappe.msgprint(message)
	else:
		process_bulk_attendance_in_batches(data)
		frappe.msgprint(_("Attendance marked successfully."), alert=True)

	for date in data.unmarked_days:
		doc_dict = {
			"doctype": "Attendance",
			"employee": data.employee,
			"attendance_date": get_datetime(date),
			"status": data.status,
			"half_day_status": "Absent" if data.status == "Half Day" else None,
		}
		attendance = frappe.get_doc(doc_dict).insert()
		attendance.submit()


def process_bulk_attendance_in_batches(data, chunk_size=20):
	savepoint = "mark_bulk_attendance"
	for days in create_batch(data.unmarked_days, chunk_size):
		for attendance_date in days:
			try:
				frappe.db.savepoint(savepoint)
				doc_dict = {
					"doctype": "Attendance",
					"employee": data.employee,
					"attendance_date": getdate(attendance_date),
					"status": data.status,
					"half_day_status": "Absent" if data.status == "Half Day" else None,
					"shift": data.shift,
				}
				attendance = frappe.get_doc(doc_dict).insert()
				attendance.submit()
			except (DuplicateAttendanceError, OverlappingShiftAttendanceError, Exception):
				if not frappe.flags.in_test:
					frappe.db.rollback(save_point=savepoint)
				continue

		if not frappe.flags.in_test:
			frappe.db.commit()  # nosemgrep


@frappe.whitelist()
def get_unmarked_days(employee, from_date, to_date, exclude_holidays=0):
	joining_date, relieving_date = frappe.get_cached_value(
		"Employee", employee, ["date_of_joining", "relieving_date"]
	)

	from_date = max(getdate(from_date), joining_date or getdate(from_date))
	to_date = min(getdate(to_date), relieving_date or getdate(to_date))

	records = frappe.get_all(
		"Attendance",
		fields=["attendance_date", "employee"],
		filters=[
			["attendance_date", ">=", from_date],
			["attendance_date", "<=", to_date],
			["employee", "=", employee],
			["docstatus", "!=", 2],
		],
	)

	marked_days = [getdate(record.attendance_date) for record in records]

	if cint(exclude_holidays):
		holiday_dates = get_holiday_dates_for_employee(employee, from_date, to_date)
		holidays = [getdate(record) for record in holiday_dates]
		marked_days.extend(holidays)

	unmarked_days = []

	while from_date <= to_date:
		if from_date not in marked_days:
			unmarked_days.append(from_date)

		from_date = add_days(from_date, 1)

	return unmarked_days


def repost_attendance(
	employee,
	attendance_date,
	shift,
	status,
	working_hours=None,
	late_entry=False,
	early_exit=False,
	in_time=None,
	out_time=None,
	logs=None,
):
	"""Upsert attendance for a recomputed shift-day, overwriting a stale Absent.

	The duplicate-attendance guard makes the normal auto-attendance path unable to
	correct a day that is already marked — a late check-in just gets skipped. This
	is the deliberate overwrite primitive for the heal/backfill flows: it creates
	attendance when none exists, and otherwise upgrades an existing **auto-marked
	Absent** record in place (the same ``db_set`` overwrite used by Attendance
	Request). It never disturbs a record that is already present, or one backed by a
	leave application or attendance request.

	Returns the attendance name it created/updated, or ``None`` if it declined to
	touch an existing record.
	"""
	existing = frappe.db.get_value(
		"Attendance",
		{"employee": employee, "attendance_date": attendance_date, "docstatus": ("!=", 2)},
		["name", "status", "leave_application", "attendance_request"],
		as_dict=True,
	)
	log_names = [log.get("name") for log in logs] if logs else []
	attendance_name = None

	if existing:
		# Only ever rewrite a plain auto-marked Absent. Leave/attendance-request-backed
		# days and already-present days are authoritative and must not be overwritten.
		if existing.status != "Absent" or existing.leave_application or existing.attendance_request:
			return None

		if existing.status == status:
			attendance_name = existing.name
		else:
			doc = frappe.get_doc("Attendance", existing.name)
			doc.db_set(
				{
					"status": status,
					"working_hours": working_hours,
					"shift": shift,
					"late_entry": late_entry,
					"early_exit": early_exit,
					"in_time": in_time,
					"out_time": out_time,
					"half_day_status": "Absent" if status == "Half Day" else None,
				}
			)
			doc.add_comment(
				"Info",
				_("Status changed from Absent to {0} after late check-in sync.").format(_(status)),
			)
			attendance_name = existing.name
	else:
		attendance_name = mark_attendance(
			employee,
			attendance_date,
			status,
			shift,
			late_entry=late_entry,
			early_exit=early_exit,
			half_day_status="Absent" if status == "Half Day" else None,
		)
		if attendance_name:
			frappe.db.set_value(
				"Attendance",
				attendance_name,
				{"working_hours": working_hours, "in_time": in_time, "out_time": out_time},
				update_modified=False,
			)

	if attendance_name and log_names:
		EmployeeCheckin = frappe.qb.DocType("Employee Checkin")
		(
			frappe.qb.update(EmployeeCheckin)
			.set(EmployeeCheckin.attendance, attendance_name)
			.set(EmployeeCheckin.skip_auto_attendance, 0)
			.where(EmployeeCheckin.name.isin(log_names))
		).run()

	return attendance_name


@frappe.whitelist()
def backfill_absent_gaps(company=None, from_date=None, to_date=None, shift_type=None, preview=1):
	"""Find auto-marked Absent days that check-ins now justify upgrading, and fix them.

	Across every shift type, recompute the status of historical Absent days from
	their actual check-ins and upgrade the ones that now clear the threshold. The
	hard guard rail: a day is **never** rewritten if it falls on or before the
	employee's last paid period (most recent submitted Salary Slip ``end_date``) —
	paid attendance is immutable here.

	``preview`` (default) only counts what would be touched. Apply (``preview=0``)
	does the recompute + repost, running inline for small batches and enqueuing a
	background job past 200 eligible days.
	"""
	if not ({"HR Manager", "System Manager"} & set(frappe.get_roles())):
		frappe.throw(_("Not permitted to backfill attendance."), frappe.PermissionError)

	preview = cint(preview)
	filters = [
		["status", "=", "Absent"],
		["docstatus", "<", 2],
		["shift", "is", "set"],
		["leave_application", "is", "not set"],
		["attendance_request", "is", "not set"],
	]
	if company:
		filters.append(["company", "=", company])
	if shift_type:
		filters.append(["shift", "=", shift_type])
	if from_date:
		filters.append(["attendance_date", ">=", getdate(from_date)])
	if to_date:
		filters.append(["attendance_date", "<=", getdate(to_date)])

	rows = frappe.get_all(
		"Attendance",
		filters=filters,
		fields=["name", "employee", "attendance_date", "shift"],
		order_by="employee asc, attendance_date asc",
	)

	# Never touch a day on or before the employee's last paid (submitted Salary Slip) period.
	last_paid = {}
	candidates = []
	for row in rows:
		emp = row.employee
		if emp not in last_paid:
			slip = frappe.get_all(
				"Salary Slip",
				filters={"employee": emp, "docstatus": 1},
				fields=["end_date"],
				order_by="end_date desc",
				limit=1,
			)
			last_paid[emp] = getdate(slip[0].end_date) if slip else None

		paid_end = last_paid[emp]
		if paid_end and getdate(row.attendance_date) <= paid_end:
			continue
		candidates.append(row)

	if preview:
		return {
			"preview": 1,
			"scanned": len(rows),
			"eligible": len(candidates),
			"skipped_paid": len(rows) - len(candidates),
		}

	if len(candidates) > 200:
		frappe.enqueue(
			"indian_hrms_compliance.hr.doctype.attendance.attendance._run_backfill_absent_gaps",
			queue="long",
			timeout=3600,
			job_id="backfill_absent_gaps",
			deduplicate=True,
			candidates=candidates,
			preview=0,
		)
		return {"preview": 0, "queued": 1, "eligible": len(candidates)}

	return _run_backfill_absent_gaps(candidates, preview=0)


def _run_backfill_absent_gaps(candidates, preview=0):
	"""Recompute + repost each candidate Absent day. Shared by the inline and queued paths."""
	from indian_hrms_compliance.hr.doctype.employee_checkin.employee_checkin import (
		recompute_status_for_date,
	)

	scanned = upgraded = skipped = 0
	details = []
	for row in candidates:
		scanned += 1
		employee = row.get("employee")
		attendance_date = row.get("attendance_date")
		shift = row.get("shift")

		result = recompute_status_for_date(employee, shift, attendance_date)
		if not result or result.status == "Absent":
			skipped += 1
			continue

		name = repost_attendance(
			employee,
			attendance_date,
			shift,
			result.status,
			working_hours=result.working_hours,
			late_entry=result.late_entry,
			early_exit=result.early_exit,
			in_time=result.in_time,
			out_time=result.out_time,
			logs=result.logs,
		)
		if name:
			upgraded += 1
			details.append(
				{"employee": employee, "attendance_date": str(attendance_date), "status": result.status}
			)
		else:
			skipped += 1

		frappe.db.commit()  # nosemgrep

	return {
		"preview": cint(preview),
		"scanned": scanned,
		"upgraded": upgraded,
		"skipped": skipped,
		"details": details[:200],
	}
