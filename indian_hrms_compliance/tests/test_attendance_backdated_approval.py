# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Back-dated attendance master-approval gate.

Contract:
  * Attendance dated within the HR-Settings months window submits normally.
  * Attendance dated beyond the window throws for an ordinary user...
  * ...but a holder of the configured approval role (default HRMS Master
    Manager; Administrator implicitly) may push it through.
  * A threshold of 0 disables the gate entirely.
"""

from types import SimpleNamespace

import frappe
from frappe.exceptions import ValidationError
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_months, getdate

from indian_hrms_compliance.overrides.attendance_backdated import (
	enforce_master_approval,
	guard_attendance,
	guard_attendance_request,
	is_backdated_beyond_threshold,
)

ROLE = "HRMS Master Manager"
PLAIN_USER = "backdate.gate@example.com"


class TestBackdatedAttendanceApproval(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		if not frappe.db.exists("Role", ROLE):
			frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert(
				ignore_permissions=True
			)
		frappe.db.set_single_value("HR Settings", "backdated_attendance_approval_months", 2)
		frappe.db.set_single_value("HR Settings", "role_allowed_to_approve_backdated_attendance", ROLE)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _old(self):
		return add_months(getdate(), -3)

	def _recent(self):
		return add_months(getdate(), -1)

	def _plain_user(self):
		if not frappe.db.exists("User", PLAIN_USER):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": PLAIN_USER,
					"first_name": "Backdate",
					"send_welcome_email": 0,
					"roles": [{"role": "Employee"}],
				}
			).insert(ignore_permissions=True)
		return PLAIN_USER

	# ----- threshold logic -------------------------------------------------

	def test_threshold_logic(self):
		self.assertTrue(is_backdated_beyond_threshold(self._old()))
		self.assertFalse(is_backdated_beyond_threshold(self._recent()))

	def test_threshold_zero_disables(self):
		frappe.db.set_single_value("HR Settings", "backdated_attendance_approval_months", 0)
		self.assertFalse(is_backdated_beyond_threshold(self._old()))

	# ----- role gate -------------------------------------------------------

	def test_ordinary_user_blocked_on_old_date(self):
		frappe.set_user(self._plain_user())
		self.assertNotIn(ROLE, frappe.get_roles())
		with self.assertRaises(ValidationError):
			enforce_master_approval(self._old(), "attendance change")

	def test_ordinary_user_allowed_within_window(self):
		frappe.set_user(self._plain_user())
		enforce_master_approval(self._recent(), "attendance change")  # must not raise

	def test_master_manager_allowed_on_old_date(self):
		user = self._plain_user()
		frappe.get_doc("User", user).add_roles(ROLE)
		frappe.set_user(user)
		self.assertIn(ROLE, frappe.get_roles())
		enforce_master_approval(self._old(), "attendance change")  # must not raise

	def test_administrator_bypasses(self):
		frappe.set_user("Administrator")
		enforce_master_approval(self._old(), "attendance change")  # must not raise

	# ----- hook entrypoints (what doc_events actually call) ----------------

	def test_guard_entrypoints(self):
		frappe.set_user(self._plain_user())
		with self.assertRaises(ValidationError):
			guard_attendance_request(SimpleNamespace(from_date=self._old()))
		with self.assertRaises(ValidationError):
			guard_attendance(SimpleNamespace(attendance_date=self._old()))
		# within window passes through both guards
		guard_attendance_request(SimpleNamespace(from_date=self._recent()))
		guard_attendance(SimpleNamespace(attendance_date=self._recent()))
