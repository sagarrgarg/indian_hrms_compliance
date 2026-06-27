# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Tests for the employment-window date guard. No transaction may be dated
before the employee's joining date or after their relieving date; on-boundary
dates (the joining day and the relieving day) are allowed. Covers the shared
helper plus its wiring into Attendance, Leave Application, Shift Request and
Shift Assignment."""

import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext.setup.doctype.employee.test_employee import make_employee

from indian_hrms_compliance.hr.utils import validate_employment_dates
from indian_hrms_compliance.tests.test_utils import create_company

DOJ = "2026-01-01"
REL = "2026-06-30"


class TestEmploymentWindowGuard(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		create_company()
		cls.emp = make_employee(
			"empwindow_guard_test@example.com", company="_Test Company", employment_type=None
		)
		# Seed the window directly so status stays Active — the exact gap the
		# guard plugs (a future relieving date while the employee is still Active).
		frappe.db.set_value("Employee", cls.emp, "date_of_joining", DOJ)
		frappe.db.set_value("Employee", cls.emp, "relieving_date", REL)

	def setUp(self):
		frappe.set_user("Administrator")

	# ---- shared helper ----
	def test_helper_rejects_before_joining(self):
		with self.assertRaisesRegex(frappe.ValidationError, "joining date"):
			validate_employment_dates(self.emp, "2025-12-31")

	def test_helper_rejects_after_relieving(self):
		with self.assertRaisesRegex(frappe.ValidationError, "relieving date"):
			validate_employment_dates(self.emp, "2026-07-01")

	def test_helper_allows_boundaries_and_interior(self):
		# None of these may raise.
		validate_employment_dates(self.emp, DOJ)
		validate_employment_dates(self.emp, REL)
		validate_employment_dates(self.emp, "2026-03-15")
		validate_employment_dates(self.emp, "2026-02-01", "2026-03-01")

	def test_helper_open_ended_start_after_relieving_rejected(self):
		# No end date → the start date is checked against the relieving date.
		with self.assertRaisesRegex(frappe.ValidationError, "relieving date"):
			validate_employment_dates(self.emp, "2026-07-02", None)

	def test_helper_ignores_missing_or_broken_employee(self):
		# Must be a silent no-op, never an unpack/lookup crash.
		validate_employment_dates(None, "2026-03-15")
		validate_employment_dates("NONEXISTENT-EMP-XYZ", "2026-03-15")

	# ---- Attendance ----
	def _attendance(self, date):
		d = frappe.new_doc("Attendance")
		d.employee = self.emp
		d.attendance_date = date
		d.status = "Present"
		d.company = "_Test Company"
		d.validate_attendance_date()

	def test_attendance_before_joining_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "joining date"):
			self._attendance("2025-12-31")

	def test_attendance_after_relieving_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "relieving date"):
			self._attendance("2026-07-01")

	def test_attendance_within_window_allowed(self):
		self._attendance("2026-03-15")
		self._attendance(REL)

	# ---- Leave Application (validate_dates runs the guard before allocation checks) ----
	def _leave_dates(self, fr, to):
		d = frappe.new_doc("Leave Application")
		d.employee = self.emp
		d.from_date = fr
		d.to_date = to
		d.validate_dates()

	def test_leave_from_before_joining_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "joining date"):
			self._leave_dates("2025-12-20", "2026-02-01")

	def test_leave_to_after_relieving_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "relieving date"):
			self._leave_dates("2026-06-01", "2026-07-10")

	# ---- Shift Request (guard runs before approver / overlap checks) ----
	def _shift_request(self, fr, to):
		d = frappe.new_doc("Shift Request")
		d.employee = self.emp
		d.from_date = fr
		d.to_date = to
		d.company = "_Test Company"
		d.validate()

	def test_shift_request_from_before_joining_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "joining date"):
			self._shift_request("2025-12-15", "2026-02-01")

	def test_shift_request_to_after_relieving_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "relieving date"):
			self._shift_request("2026-06-10", "2026-07-15")

	# ---- Shift Assignment (guard runs before overlap checks) ----
	def _shift_assignment(self, start, end):
		d = frappe.new_doc("Shift Assignment")
		d.employee = self.emp
		d.start_date = start
		d.end_date = end
		d.company = "_Test Company"
		d.validate()

	def test_shift_assignment_start_before_joining_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "joining date"):
			self._shift_assignment("2025-12-15", "2026-02-01")

	def test_shift_assignment_end_after_relieving_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "relieving date"):
			self._shift_assignment("2026-06-10", "2026-07-15")

	def test_shift_assignment_open_ended_start_after_relieving_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "relieving date"):
			self._shift_assignment("2026-07-05", None)
