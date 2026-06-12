# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""End-to-end tests for Employee Profile Change Request.

Covers: submit/validate/approve/reject/withdraw, sensitive-field masking and
non-persistence of raw sensitive values on the change item rows, and the
on-demand current-value fetch endpoint.
"""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from indian_hrms_compliance.hr.doctype.employee_profile_change_request.employee_profile_change_request import (
	SENSITIVE_FIELDS,
	approve_profile_change_request,
	get_my_profile_change_requests,
	get_profile_change_old_values,
	mask_value,
	reject_profile_change_request,
	submit_profile_change_request,
	withdraw_profile_change_request,
)


def _pick_employee():
	"""Pick the first active Employee that has a User. Tests skip if there's none."""
	return frappe.db.sql(
		"""
		SELECT name, user_id, cell_number, pan_number
		FROM `tabEmployee`
		WHERE status='Active' AND user_id != ''
		LIMIT 1
		""",
		as_dict=True,
	)


class TestProfileChangeRequestSubmit(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		rows = _pick_employee()
		if not rows:
			raise unittest.SkipTest("No active employee with a user — cannot test ESS flow.")
		cls.emp = rows[0]
		frappe.set_user(cls.emp.user_id)
		frappe.local.request_ip = "203.0.113.50"

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		super().tearDownClass()

	def test_submit_with_blank_changes_throws(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			submit_profile_change_request(changes=[{"fieldname": "cell_number", "new_value": "  "}])

	def test_submit_disallowed_field_throws(self):
		# salary_mode isn't in DEFAULT_EDITABLE_FIELDS — should be rejected.
		with self.assertRaises(frappe.exceptions.ValidationError):
			submit_profile_change_request(
				changes=[{"fieldname": "salary_mode", "new_value": "Cash"}]
			)

	def test_submit_missing_consent_throws(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			submit_profile_change_request(
				changes=[{"fieldname": "cell_number", "new_value": "9876543210"}],
				dpdp_consent=0,
			)

	def test_sensitive_old_value_not_persisted(self):
		"""When the request includes a PAN change, the change_item old_value
		must be empty — we do NOT store the historical raw PAN."""
		res = submit_profile_change_request(
			changes=[{"fieldname": "pan_number", "new_value": "ABCDE1234F"}],
			dpdp_consent=1,
		)
		doc = frappe.get_doc("Employee Profile Change Request", res["name"])
		self.assertEqual(doc.changes[0].fieldname, "pan_number")
		self.assertEqual(doc.changes[0].old_value, "")
		# new_value IS stored — HR needs to see what the employee proposed.
		self.assertEqual(doc.changes[0].new_value, "ABCDE1234F")


class TestProfileChangeRequestApproval(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		rows = _pick_employee()
		if not rows:
			raise unittest.SkipTest("No active employee with a user — cannot test approve flow.")
		cls.emp = rows[0]
		cls.original_cell = cls.emp.cell_number

	def setUp(self):
		# Each test submits as the employee, then switches to admin for HR action.
		frappe.set_user(self.emp.user_id)
		frappe.local.request_ip = "203.0.113.51"
		self.res = submit_profile_change_request(
			changes=[
				{"fieldname": "cell_number", "new_value": "9999988888"},
				{"fieldname": "blood_group", "new_value": "B+"},
			],
			dpdp_consent=1,
		)
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_approve_applies_changes_to_employee(self):
		out = approve_profile_change_request(self.res["name"])
		self.assertEqual(out["status"], "Approved")
		self.assertIn("cell_number", out["applied_fields"])
		# Resolve the actual Employee the submit targeted — users with multiple
		# Employee records (multi_employee_architecture) get the first match
		# from _get_current_employee_for_user, not necessarily the test's snapshot.
		actual_emp = frappe.db.get_value(
			"Employee Profile Change Request", self.res["name"], "employee"
		)
		emp = frappe.db.get_value(
			"Employee", actual_emp, ["cell_number", "blood_group"], as_dict=True
		)
		self.assertEqual(emp.cell_number, "9999988888")
		self.assertEqual(emp.blood_group, "B+")

	def test_reject_without_comment_throws(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			reject_profile_change_request(self.res["name"], comment="")

	def test_reject_persists_review_notes(self):
		reject_profile_change_request(self.res["name"], comment="Mobile doesn't match KYC.")
		doc = frappe.get_doc("Employee Profile Change Request", self.res["name"])
		self.assertEqual(doc.status, "Rejected")
		self.assertEqual(doc.review_notes, "Mobile doesn't match KYC.")

	def test_double_approve_throws(self):
		approve_profile_change_request(self.res["name"])
		with self.assertRaises(frappe.exceptions.ValidationError):
			approve_profile_change_request(self.res["name"])


class TestProfileChangeRequestWithdraw(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		rows = _pick_employee()
		if not rows:
			raise unittest.SkipTest("No active employee with a user — cannot test withdraw.")
		cls.emp = rows[0]

	def setUp(self):
		frappe.set_user(self.emp.user_id)
		frappe.local.request_ip = "203.0.113.52"
		self.res = submit_profile_change_request(
			changes=[{"fieldname": "blood_group", "new_value": "A+"}], dpdp_consent=1
		)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_withdraw_own_request(self):
		out = withdraw_profile_change_request(self.res["name"])
		self.assertEqual(out["status"], "Withdrawn")

	def test_withdraw_other_users_request_throws(self):
		# Approve as admin first so we can switch user, then try to withdraw.
		other_user = frappe.db.get_value(
			"User",
			{"enabled": 1, "name": ("not in", ["Administrator", "Guest", self.emp.user_id])},
			"name",
		)
		if not other_user:
			self.skipTest("No second user available.")
		frappe.set_user(other_user)
		with self.assertRaises(frappe.PermissionError):
			withdraw_profile_change_request(self.res["name"])


class TestMaskAndCurrentValueEndpoint(FrappeTestCase):
	def test_mask_aadhaar(self):
		self.assertEqual(mask_value("aadhaar_number", "999999990019"), "XXXX XXXX 0019")

	def test_mask_pan(self):
		self.assertEqual(mask_value("pan_number", "ABCDE1234F"), "XXXXX234F")

	def test_mask_passthrough_non_sensitive(self):
		self.assertEqual(mask_value("cell_number", "9876543210"), "9876543210")

	def test_sensitive_set_is_non_empty(self):
		self.assertIn("pan_number", SENSITIVE_FIELDS)
		self.assertIn("aadhaar_number", SENSITIVE_FIELDS)


class TestHistoryEndpoint(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		rows = _pick_employee()
		if not rows:
			raise unittest.SkipTest("No active employee with a user.")
		cls.emp = rows[0]

	def tearDown(self):
		frappe.db.rollback()

	def test_history_returns_my_requests_in_order(self):
		frappe.set_user(self.emp.user_id)
		frappe.local.request_ip = "203.0.113.53"
		r1 = submit_profile_change_request(
			changes=[{"fieldname": "blood_group", "new_value": "A+"}], dpdp_consent=1
		)
		r2 = submit_profile_change_request(
			changes=[{"fieldname": "blood_group", "new_value": "O+"}], dpdp_consent=1
		)
		hist = get_my_profile_change_requests()
		names = [h["name"] for h in hist]
		# Most recent first.
		self.assertIn(r1["name"], names)
		self.assertIn(r2["name"], names)
		self.assertGreaterEqual(names.index(r1["name"]), names.index(r2["name"]))

	def test_get_old_values_runs_for_hr(self):
		frappe.set_user(self.emp.user_id)
		frappe.local.request_ip = "203.0.113.54"
		res = submit_profile_change_request(
			changes=[{"fieldname": "pan_number", "new_value": "ABCDE9999K"}], dpdp_consent=1
		)
		frappe.set_user("Administrator")
		rows = get_profile_change_old_values(res["name"])
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["fieldname"], "pan_number")
		self.assertEqual(rows[0]["sensitive"], 1)
		self.assertEqual(rows[0]["requested"], "ABCDE9999K")
